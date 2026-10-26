'use strict';
/* ==========================================================================
 *  snapshot_delta.js —— 增量快照
 *  --------------------------------------------------------------------------
 *  问题：全量快照在 13MB 状态上要 323ms，7ms 脉冲优势彻底失效。
 *
 *  解法：先写一份全量（base），之后的快照只记【变化】。
 *
 *      snap-1.snap        全量 base（seq=1000）
 *      snap-1000.delta    增量（相对 base）
 *      snap-2000.delta    增量（相对上一份）
 *      ...
 *      snap-5000.snap     新的全量 base（每 N 份增量落一次全量）
 *
 *  还原：找最新的全量 base → 依次 apply 所有 delta。
 *
 *  ★ 核心问题：怎么判断"什么变了"
 *
 *    方案 A：diff 两个状态      —— 通用但要遍历整个状态，10MB 也是 O(n)
 *    方案 B：记录脏字段         —— PulseScript 的 set/append 本来就知道改了什么
 *
 *    我选 B 为主（快、精确），A 只用于测试校验。
 *
 *  ★ 列表的增量优化
 *
 *    `append(items, x)` 之后 items 变成 N+1 个元素。
 *    如果每次快照都写整个列表，10 万元素的列表还是慢。
 *
 *    关键洞察：PulseScript 的 append 只改尾部，前面元素的【引用不变】。
 *    所以用 `old[i] === new[i]` 做引用比较，O(n) 但零深度遍历 —— 很快。
 *    确认是纯追加后，只写新增的尾部元素。
 * ========================================================================== */
const zlib = require('zlib');

const DELTA_MAGIC = 0x444C5431;    // 'DLT1'

/* ============================ 差值计算 ============================ */

/* 判断 old 是否是 next 的严格前缀（用引用/原始值比较，不做深比较） */
function isPrefix(oldArr, newArr) {
  if (!Array.isArray(oldArr) || !Array.isArray(newArr)) return false;
  if (newArr.length < oldArr.length) return false;
  for (let i = 0; i < oldArr.length; i++) {
    if (oldArr[i] !== newArr[i]) return false;   // 引用不同就不算前缀
  }
  return true;
}

/* 标量/对象深比较（只在需要时用，不用于大数组） */
function deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== typeof b) return false;
  if (typeof a !== 'object') return false;

  const aArr = Array.isArray(a), bArr = Array.isArray(b);
  if (aArr !== bArr) return false;

  if (aArr) {
    if (a.length !== b.length) return false;
    for (let i = 0; i < a.length; i++) if (!deepEqual(a[i], b[i])) return false;
    return true;
  }

  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) {
    if (!Object.prototype.hasOwnProperty.call(b, k)) return false;
    if (!deepEqual(a[k], b[k])) return false;
  }
  return true;
}

/* 计算 delta
   opts: { baseSeq, seq, dirty? }  dirty = Set of field names（省略则全量 diff） */
function makeDelta(oldState, nextState, opts = {}) {
  const oldS = oldState || {};
  const newS = nextState || {};
  const delta = {
    v: 1,
    baseSeq: opts.baseSeq || 0,
    seq: opts.seq || 0,
    set: {},        // 整字段替换
    append: {},     // 列表尾部追加（只存新增元素）
    removed: [],    // 被删的字段
  };

  /* 决定要检查哪些字段 */
  let keys;
  if (opts.dirty && opts.dirty.size) {
    keys = new Set([...opts.dirty]);
    /* 脏集合里可能有已删除的字段，也要覆盖 */
  } else {
    keys = new Set([...Object.keys(oldS), ...Object.keys(newS)]);
  }

  for (const k of keys) {
    const hasOld = Object.prototype.hasOwnProperty.call(oldS, k);
    const hasNew = Object.prototype.hasOwnProperty.call(newS, k);
    const ov = oldS[k], nv = newS[k];

    if (!hasNew) {
      if (hasOld) delta.removed.push(k);
      continue;
    }
    if (!hasOld) { delta.set[k] = nv; continue; }

    /* 未变则跳过（省字节） */
    if (ov === nv) continue;

    /* 列表纯追加 → 只存尾部 */
    if (Array.isArray(ov) && Array.isArray(nv) && isPrefix(ov, nv)) {
      if (nv.length > ov.length) {
        delta.append[k] = nv.slice(ov.length);
        continue;
      }
      /* 长度相同但 isPrefix 为真 → 就是没变 */
      if (nv.length === ov.length) continue;
    }

    /* 其它情况：整字段替换 */
    if (!deepEqual(ov, nv)) delta.set[k] = nv;
  }

  return delta;
}

/* 应用 delta */
function applyDelta(state, delta) {
  const s = Object.assign({}, state || {});
  if (!delta) return s;
  if (delta.set) for (const k of Object.keys(delta.set)) s[k] = delta.set[k];
  if (delta.append) {
    for (const k of Object.keys(delta.append)) {
      s[k] = (Array.isArray(s[k]) ? s[k] : []).concat(delta.append[k]);
    }
  }
  if (delta.removed) for (const k of delta.removed) delete s[k];
  return s;
}

/* delta 的"大小"（估算，用于统计写入了多少） */
function deltaCost(delta) {
  if (!delta) return 0;
  let n = 0;
  for (const k of Object.keys(delta.set || {})) n += JSON.stringify(delta.set[k]).length + k.length;
  for (const k of Object.keys(delta.append || {})) n += JSON.stringify(delta.append[k]).length + k.length;
  n += (delta.removed || []).reduce((a, k) => a + k.length, 0);
  return n;
}

/* ============================ 编码 ============================ */
/* [magic:u32][clen:u32][crc:u32][zlib(JSON delta)] */
const { crc32 } = require('./wal');

function encodeDelta(delta) {
  const raw = Buffer.from(JSON.stringify(delta), 'utf8');
  const packed = zlib.deflateRawSync(raw, { level: 6 });
  const head = Buffer.alloc(12);
  head.writeUInt32BE(DELTA_MAGIC, 0);
  head.writeUInt32BE(packed.length, 4);
  head.writeUInt32BE(crc32(packed), 8);
  return { buf: Buffer.concat([head, packed]), raw: raw.length, packed: packed.length };
}

function decodeDelta(buf) {
  if (!buf || buf.length < 12) return null;
  if (buf.readUInt32BE(0) !== DELTA_MAGIC) return null;
  const clen = buf.readUInt32BE(4);
  const crc = buf.readUInt32BE(8);
  if (12 + clen > buf.length) return null;
  const packed = buf.subarray(12, 12 + clen);
  if (crc32(packed) !== crc) return null;
  try { return JSON.parse(zlib.inflateRawSync(packed).toString('utf8')); }
  catch (e) { return null; }
}

/* ============================ 快照链 ============================ */
class SnapshotChain {
  /* opts: { dir, fullEvery }  fullEvery = 多少份 delta 后落一次全量 base */
  constructor(opts = {}) {
    this.dir = opts.dir;
    this.fullEvery = opts.fullEvery || 10;
    this.stats = {
      fullWrites: 0, deltaWrites: 0,
      fullBytes: 0, deltaBytes: 0,
      loads: 0, deltasApplied: 0,
    };
  }

  /* 从磁盘读回整条链，还原出状态 */
  load() {
    const fs = require('fs');
    const path = require('path');
    let files;
    try { files = fs.readdirSync(this.dir); } catch (e) { return { state: null, seq: 0, chain: [] }; }

    const bases = files.filter(f => /^snap-(\d+)\.snap$/.test(f))
      .map(f => ({ f, seq: parseInt(f.match(/\d+/)[0], 10) }))
      .sort((a, b) => b.seq - a.seq);              // 新→旧

    const deltas = files.filter(f => /^snap-(\d+)\.delta$/.test(f))
      .map(f => ({ f, seq: parseInt(f.match(/\d+/)[0], 10) }))
      .sort((a, b) => a.seq - b.seq);              // 旧→新

    /* ① 找最新的有效全量 base */
    let base = null, baseSeq = 0;
    for (const b of bases) {
      try {
        const { loadLatestSnapshotFile } = require('./wal');
        const r = loadLatestSnapshotFile(path.join(this.dir, b.f));
        if (r && r.state !== undefined) { base = r.state; baseSeq = r.seq; break; }
      } catch (e) { continue; }
    }

    /* ② 依次 apply 所有 seq > baseSeq 的 delta */
    const chain = [];
    let st = base;
    for (const d of deltas) {
      if (d.seq <= baseSeq) continue;              // 已经包含在 base 里
      let delta = null;
      try { delta = decodeDelta(fs.readFileSync(path.join(this.dir, d.f))); } catch (e) {}
      if (!delta) continue;                        // 损坏就跳过（宁可少应用也不要崩）
      st = applyDelta(st, delta);
      chain.push(d.seq);
      this.stats.deltasApplied++;
    }

    this.stats.loads++;
    return { state: st, seq: deltas.length ? deltas[deltas.length - 1].seq : baseSeq, chain };
  }

  /* 写一份（自动决定全量 or 增量） */
  save(seq, state, prevState, dirty) {
    const fs = require('fs');
    const path = require('path');
    const { writeSnapshot, pruneSnapshots, loadLatestSnapshot } = require('./wal');

    fs.mkdirSync(this.dir, { recursive: true });

    const lastBase = loadLatestSnapshot(this.dir);
    const lastBaseSeq = lastBase ? lastBase.seq : 0;

    /* 数一下 base 之后有多少 delta */
    let deltaCount = 0;
    try {
      deltaCount = fs.readdirSync(this.dir)
        .filter(f => /^snap-(\d+)\.delta$/.test(f))
        .filter(f => parseInt(f.match(/\d+/)[0], 10) > lastBaseSeq).length;
    } catch (e) {}

    const needFull = (!lastBase) || (deltaCount >= this.fullEvery);

    if (needFull) {
      const w = writeSnapshot(this.dir, seq, state);
      pruneSnapshots(this.dir, 2);
      /* 全量落盘后，旧的 delta 就没用了 */
      try {
        for (const f of fs.readdirSync(this.dir)) {
          if (!/^snap-(\d+)\.delta$/.test(f)) continue;
          const s = parseInt(f.match(/\d+/)[0], 10);
          if (s <= seq) { try { fs.unlinkSync(path.join(this.dir, f)); } catch (e) {} }
        }
      } catch (e) {}
      this.stats.fullWrites++;
      this.stats.fullBytes += w.bytes;
      return { kind: 'full', bytes: w.bytes, rawBytes: w.rawBytes, seq };
    }

    /* 增量 */
    const delta = makeDelta(prevState, state, { baseSeq: lastBaseSeq, seq, dirty });
    const enc = encodeDelta(delta);
    const file = path.join(this.dir, 'snap-' + String(seq).padStart(12, '0') + '.delta');
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, enc.buf);
    fs.renameSync(tmp, file);
    this.stats.deltaWrites++;
    this.stats.deltaBytes += enc.buf.length;
    return { kind: 'delta', bytes: enc.buf.length, rawBytes: enc.raw, cost: deltaCost(delta), seq };
  }

  info() {
    return {
      fullEvery: this.fullEvery,
      ...this.stats,
      avgFullBytes: this.stats.fullWrites ? Math.round(this.stats.fullBytes / this.stats.fullWrites) : 0,
      avgDeltaBytes: this.stats.deltaWrites ? Math.round(this.stats.deltaBytes / this.stats.deltaWrites) : 0,
    };
  }
}

module.exports = {
  makeDelta, applyDelta, deltaCost, isPrefix, deepEqual,
  encodeDelta, decodeDelta, SnapshotChain,
};
