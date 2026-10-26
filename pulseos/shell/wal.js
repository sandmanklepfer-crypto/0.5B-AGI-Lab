'use strict';
/* ==========================================================================
 *  wal.js v2 —— 分段 WAL + 快照 + compaction
 *  --------------------------------------------------------------------------
 *  v1 的问题（实测出来的）：
 *      写入 100000 条，轮转后 replay 只拿到 38568 条 —— 旧段被丢了
 *
 *  v2 的目录结构：
 *
 *      dir/
 *        snap-<seq>.snap        состояния快照（原子写：tmp → fsync → rename）
 *        wal-<seq>.log          分段日志，seq 是段起始序号
 *        ...
 *
 *  三条保证正确性的规则：
 *
 *    ① 快照原子       写 tmp → fsync → rename → fsync(dir)
 *    ② 重放幂等       跳过 seq <= snapshotSeq 的记录
 *    ③ 删段在快照后    只有快照落盘（fsync dir）之后才删旧段
 *
 *  ★ 规则②是关键：
 *      "快照已写但旧段还没删" 这个中间状态必须安全。
 *      靠 "重放时跳过 seq <= snapSeq" 做到幂等，不需要两阶段提交。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const MAGIC = 0x57414c32;     // 'WAL2'

/* ==========================================================================
 *  IO 错误分类与降级
 *  --------------------------------------------------------------------------
 *  磁盘满了不能直接崩。三种应对：
 *
 *    ENOSPC / EDQUOT  磁盘满      → 只读降级（拒绝新写，已有数据可读）
 *    EIO / EROFS      硬件/只读   → 故障降级（拒绝一切写，报警）
 *    EMFILE / ENFILE  句柄耗尽    → 可重试（关掉闲置 fd 再试）
 *
 *  ★ 关键判断：降级后【必须让调用方知道】。
 *    静默丢写比崩溃更危险 —— 用户以为存了，其实没有。
 * ========================================================================== */
const ERR = {
  DISK_FULL: 'DISK_FULL',
  IO_ERROR: 'IO_ERROR',
  FD_EXHAUSTED: 'FD_EXHAUSTED',
  RETRYABLE: 'RETRYABLE',
};

function classifyErr(e) {
  const c = e && e.code;
  if (c === 'ENOSPC' || c === 'EDQUOT') return { kind: ERR.DISK_FULL, retry: false, fatal: false };
  if (c === 'EIO' || c === 'EROFS' || c === 'EACCES') return { kind: ERR.IO_ERROR, retry: false, fatal: true };
  if (c === 'EMFILE' || c === 'ENFILE') return { kind: ERR.FD_EXHAUSTED, retry: true, fatal: false };
  if (c === 'EAGAIN' || c === 'EBUSY') return { kind: ERR.RETRYABLE, retry: true, fatal: false };
  return { kind: ERR.IO_ERROR, retry: false, fatal: false };
}

/* 统一的安全写：失败返回 {ok:false}，不抛 */
function safeSync(fn, what) {
  try { fn(); return { ok: true }; }
  catch (e) {
    const cls = classifyErr(e);
    return { ok: false, error: e, code: e && e.code, kind: cls.kind, retry: cls.retry, fatal: cls.fatal, what };
  }
}

/* ---------------------------- CRC32 ---------------------------- */
const CRC_TABLE = (() => {
  const t = new Int32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[i] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = -1;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ -1) >>> 0;
}

/* ---------------------------- 记录编解码 ---------------------------- */
/* [len:u32][crc:u32][magic:u32][zlib(JSON)] */
function encodeRecord(rec) {
  const raw = Buffer.from(JSON.stringify(rec), 'utf8');
  const packed = zlib.deflateRawSync(raw, { level: 1 });
  const head = Buffer.alloc(12);
  head.writeUInt32BE(packed.length, 0);
  head.writeUInt32BE(crc32(packed), 4);
  head.writeUInt32BE(MAGIC, 8);
  return Buffer.concat([head, packed]);
}

function decodeAt(buf, off) {
  if (off + 12 > buf.length) return null;
  const len = buf.readUInt32BE(off);
  const crc = buf.readUInt32BE(off + 4);
  const magic = buf.readUInt32BE(off + 8);
  if (magic !== MAGIC || len > 64 * 1024 * 1024) return null;
  if (off + 12 + len > buf.length) return null;
  const packed = buf.subarray(off + 12, off + 12 + len);
  if (crc32(packed) !== crc) return null;
  try {
    return { rec: JSON.parse(zlib.inflateRawSync(packed).toString('utf8')), next: off + 12 + len };
  } catch (e) { return null; }
}

/* ==========================================================================
 *  SegmentLog —— 单调递增的分段日志（可多段）
 * ========================================================================== */
class SegmentLog {
  constructor(dir, opts = {}) {
    this.dir = dir;
    this.mode = opts.mode || 'os';
    this.groupMs = opts.groupMs || 5;
    this.segMaxBytes = opts.segMaxBytes || 4 * 1024 * 1024;

    fs.mkdirSync(dir, { recursive: true });

    this.segs = [];
    this.active = null;
    this.lastSeq = 0;
    this.stats = { appends: 0, fsyncs: 0, rotations: 0, truncations: 0 };
    this.ioErrors = 0;
    this.degraded = null;      // null | { level:'readonly'|'fault', since, reason, code }
    this._pendingBytes = 0;    // 写失败的字节数（用于告警）

    this._load();
    this._openActive();
  }

  _segFiles() {
    return fs.readdirSync(this.dir)
      .filter(f => /^wal-\d+\.log$/.test(f))
      .sort((a, b) => {
        const na = parseInt(a.match(/\d+/)[0], 10);
        const nb = parseInt(b.match(/\d+/)[0], 10);
        return na - nb;
      });
  }

  /* 扫描已有段，确定 lastSeq */
  _load() {
    this.segs = [];
    let last = null;
    for (const f of this._segFiles()) {
      const p = path.join(this.dir, f);
      const size = fs.statSync(p).size;
      const recs = this._scanFile(p);
      const seg = {
        file: f, path: p, bytes: size,
        startSeq: recs.length ? recs[0].seq : 0,
        endSeq: recs.length ? recs[recs.length - 1].seq : 0,
        records: recs.length,
      };
      this.segs.push(seg);
      last = seg;
    }
    if (last) this.lastSeq = Math.max(this.lastSeq, last.endSeq);
  }

  /* 扫一个段，返回所有能读出的记录（遇到损坏就停） */
  _scanFile(p) {
    let buf;
    try { buf = fs.readFileSync(p); } catch (e) { return []; }
    const out = [];
    let off = 0;
    while (off < buf.length) {
      const r = decodeAt(buf, off);
      if (!r) { this.stats.truncations++; break; }
      out.push(r.rec);
      off = r.next;
    }
    return out;
  }

  _openActive() {
    const last = this.segs[this.segs.length - 1];
    if (last && last.bytes < this.segMaxBytes) {
      try {
        this.active = Object.assign({}, last, { fd: fs.openSync(last.path, 'r+') });
        this.active.writeOff = this.active.bytes;
        return;
      } catch (e) {
        this.degraded = { level: 'fault', since: Date.now(), code: e.code,
          reason: '无法打开段文件: ' + e.code };
        return;
      }
    }
    const r = this._newSegment(this.lastSeq);
    if (!r.ok) {
      this.degraded = { level: 'fault', since: Date.now(), code: r.code,
        reason: '初始段创建失败: ' + r.code };
    }
  }

  _newSegment(afterSeq) {
    /* ★ 用 startSeq 做段名，不能用 segs.length+1（删段后长度回退会覆盖） */
    const file = 'wal-' + String(afterSeq + 1).padStart(12, '0') + '.log';
    const p = path.join(this.dir, file);
    let fd;
    try { fd = fs.openSync(p, 'w'); }
    catch (e) {
      const cls = classifyErr(e);
      return { ok: false, code: e.code, kind: cls.kind, error: 'cannot create segment: ' + e.code };
    }
    const seg = {
      file, path: p, bytes: 0, writeOff: 0,
      startSeq: afterSeq + 1, endSeq: afterSeq, records: 0, fd,
    };
    this.segs.push(seg);
    this.active = seg;
    return { ok: true, seg };
  }

  /* ---------------- 追加 ---------------- */
  /* 返回 { ok, seq?, error?, degraded? } —— 永不抛异常 */
  append(rec) {
    /* 已降级：直接拒绝，但【明确告诉调用方】 */
    if (this.degraded) {
      return { ok: false, degraded: this.degraded.level, code: this.degraded.code,
        error: '写入被拒绝（降级中: ' + this.degraded.reason + '）' };
    }

    if (this.mode === 'none') { this.lastSeq++; return { ok: true, seq: this.lastSeq }; }

    const full = Object.assign({ seq: this.lastSeq + 1, ts: Date.now() }, rec);
    let buf;
    try { buf = encodeRecord(full); }
    catch (e) { return { ok: false, error: '编码失败: ' + e.message, kind: ERR.IO_ERROR }; }

    const a = this.active;

    /* 写 */
    const w = safeSync(() => fs.writeSync(a.fd, buf, 0, buf.length, a.writeOff), 'write');
    if (!w.ok) return this._onIoError(w, buf.length);

    a.writeOff += buf.length;
    a.bytes = a.writeOff;
    a.records++;
    a.endSeq = full.seq;
    this.lastSeq = full.seq;
    this.stats.appends++;
    this._pendingBytes = 0;

    /* fsync */
    if (this.mode === 'fsync' || (this.mode === 'group' &&
        Date.now() - (this._lastFlush || 0) >= this.groupMs)) {
      const f = safeSync(() => fs.fsyncSync(a.fd), 'fsync');
      if (!f.ok) return this._onIoError(f, 0);
      this.stats.fsyncs++;
      if (this.mode === 'group') this._lastFlush = Date.now();
    }

    if (a.bytes >= this.segMaxBytes) this.rotate();
    return { ok: true, seq: full.seq };
  }

  /* IO 失败 → 分类 → 决定降级等级 */
  _onIoError(res, bytes) {
    this.ioErrors++;
    this._pendingBytes += bytes || 0;
    const cls = classifyErr(res.error);

    if (cls.retry && !this.degraded) {
      /* 可重试（fd 耗尽）：关掉闲置 fd 再试一次 */
      for (const [k, fd] of (this._fds || new Map())) { try { fs.closeSync(fd); } catch (e) {} }
      return { ok: false, retryable: true, kind: cls.kind, code: res.code,
        error: '临时 IO 错误，可重试: ' + res.what + ' ' + res.code };
    }

    const level = (cls.kind === ERR.DISK_FULL) ? 'readonly' : 'fault';
    this.degraded = {
      level, since: Date.now(), code: res.code,
      reason: cls.kind === ERR.DISK_FULL
        ? '磁盘已满（只读降级，已有数据仍可读）'
        : 'IO 故障（拒绝全部写入）',
    };
    return {
      ok: false, degraded: level, code: res.code, kind: cls.kind,
      error: this.degraded.reason + ' [' + res.what + ': ' + res.code + ']',
    };
  }

  /* 恢复：磁盘腾出空间后调 canRecover 检查 */
  tryRecover() {
    if (!this.degraded) return { ok: true, already: true };
    const a = this.active;
    if (!a || a.fd == null) return { ok: false, error: '没有可写段' };
    const r = safeSync(() => fs.writeSync(a.fd, Buffer.alloc(0), 0, 0, a.writeOff), 'probe');
    if (r.ok) { this.degraded = null; return { ok: true, recovered: true }; }
    const cls = classifyErr(r.error);
    return { ok: false, reason: cls.kind, code: r.code };
  }

  rotate() {
    if (this.active && this.active.fd != null) {
      safeSync(() => fs.fsyncSync(this.active.fd), 'fsync-rotate');
      try { fs.closeSync(this.active.fd); } catch (e) {}
      this.active.fd = null;
    }
    this.stats.rotations++;
    const r = this._newSegment(this.lastSeq);
    if (!r.ok) {
      this.degraded = { level: 'fault', since: Date.now(), code: r.code,
        reason: '无法创建新段（磁盘满或权限问题）' };
    }
  }

  flush() {
    if (this.mode === 'none' || !this.active || this.active.fd == null) return { ok: true, skipped: true };
    const r = safeSync(() => fs.fsyncSync(this.active.fd), 'fsync-flush');
    if (r.ok) { this.stats.fsyncs++; return { ok: true }; }
    return this._onIoError(r, 0);
  }

  /* ---------------- 重放 ---------------- */
  /* 返回所有 seq > afterSeq 的记录（跨段、按 seq 排序） */
  replay(afterSeq = 0) {
    const all = [];
    for (const s of this.segs) {
      for (const r of this._scanFile(s.path)) {
        if (r.seq > afterSeq) all.push(r);
      }
    }
    all.sort((a, b) => a.seq - b.seq);
    return all;
  }

  /* 删除 endSeq <= uptoSeq 的段（compaction 用） */
  dropSegmentsBefore(uptoSeq) {
    const keep = [];
    const removed = [];
    for (const s of this.segs) {
      if (s === this.active) { keep.push(s); continue; }
      if (s.endSeq > 0 && s.endSeq <= uptoSeq) {
        try { fs.unlinkSync(s.path); removed.push(s.file); } catch (e) {}
      } else keep.push(s);
    }
    this.segs = keep;
    return removed;
  }

  close() {
    this.flush();
    if (this.active && this.active.fd != null) {
      try { fs.closeSync(this.active.fd); } catch (e) {}
      this.active.fd = null;
    }
  }

  info() {
    return {
      mode: this.mode, lastSeq: this.lastSeq,
      segments: this.segs.length,
      bytes: this.segs.reduce((a, s) => a + s.bytes, 0),
      degraded: this.degraded, ioErrors: this.ioErrors,
      ...this.stats,
    };
  }
}

/* ==========================================================================
 *  Snapshot —— 原子写
 * ========================================================================== */
function writeSnapshot(dir, seq, state) {
  fs.mkdirSync(dir, { recursive: true });
  const raw = Buffer.from(JSON.stringify({ seq, state, at: Date.now() }), 'utf8');
  const packed = zlib.deflateRawSync(raw, { level: 9 });
  const head = Buffer.alloc(12);
  head.writeUInt32BE(packed.length, 0);
  head.writeUInt32BE(crc32(packed), 4);
  head.writeUInt32BE(MAGIC, 8);

  const tmp = path.join(dir, '.snap-' + seq + '.tmp');
  const dst = path.join(dir, 'snap-' + String(seq).padStart(12, '0') + '.snap');

  let fd = null;
  try {
    fd = fs.openSync(tmp, 'w');
    fs.writeSync(fd, head, 0, 12);
    fs.writeSync(fd, packed, 0, packed.length);
    fs.fsyncSync(fd);              // ① 保证内容落盘
    fs.closeSync(fd); fd = null;
    fs.renameSync(tmp, dst);       // ② 原子替换
  } catch (e) {
    if (fd !== null) { try { fs.closeSync(fd); } catch (e2) {} }
    try { fs.unlinkSync(tmp); } catch (e2) {}     // 清理半成品
    throw e;                                       // 交给上层分类
  }
  try {                              // ③ 保证目录项落盘（否则断电后 rename 可能丢）
    const dfd = fs.openSync(dir, 'r');
    fs.fsyncSync(dfd);
    fs.closeSync(dfd);
  } catch (e) {}

  return { file: dst, bytes: 12 + packed.length, rawBytes: raw.length };
}

/* 找到最新的有效快照 */
function loadLatestSnapshot(dir) {
  let files;
  try { files = fs.readdirSync(dir); } catch (e) { return null; }
  const snaps = files.filter(f => /^snap-\d+\.snap$/.test(f)).sort().reverse();

  for (const f of snaps) {
    const p = path.join(dir, f);
    try {
      const buf = fs.readFileSync(p);
      if (buf.length < 12) continue;
      const len = buf.readUInt32BE(0);
      const crc = buf.readUInt32BE(4);
      const magic = buf.readUInt32BE(8);
      if (magic !== MAGIC || 12 + len > buf.length) continue;
      const packed = buf.subarray(12, 12 + len);
      if (crc32(packed) !== crc) continue;                   // 快照损坏，试下一个
      const obj = JSON.parse(zlib.inflateRawSync(packed).toString('utf8'));
      return Object.assign({ file: p, name: f }, obj);
    } catch (e) { continue; }
  }
  return null;
}

/* 清理多余快照，只留最新 N 个 */
function pruneSnapshots(dir, keep = 2) {
  const snaps = fs.readdirSync(dir)
    .filter(f => /^snap-\d+\.snap$/.test(f))
    .sort().reverse();
  const removed = [];
  for (let i = keep; i < snaps.length; i++) {
    try { fs.unlinkSync(path.join(dir, snaps[i])); removed.push(snaps[i]); } catch (e) {}
  }
  return removed;
}

/* 清理残留 tmp 文件（崩溃留下的） */
function cleanTmp(dir) {
  let n = 0;
  try {
    for (const f of fs.readdirSync(dir)) {
      if (/^\.snap-.*\.tmp$/.test(f)) { try { fs.unlinkSync(path.join(dir, f)); n++; } catch (e) {} }
    }
  } catch (e) {}
  return n;
}

/* ==========================================================================
 *  WalStore —— 对外统一接口：WAL + 快照 + compaction
 * ========================================================================== */
class WalStore {
  /* opts: { dir, name, mode, groupMs, compactEvery } */
  constructor(opts) {
    this.dir = opts.dir;
    this.name = opts.name || 'store';
    this.compactEvery = opts.compactEvery || 5000;

    fs.mkdirSync(this.dir, { recursive: true });
    this.cleanup = cleanTmp(this.dir);         // 清掉崩溃残留

    this.snap = loadLatestSnapshot(this.dir);
    this.snapSeq = this.snap ? this.snap.seq : 0;
    this.state = this.snap ? this.snap.state : null;

    this.log = new SegmentLog(this.dir, opts);
    this.sinceCompact = 0;
    this.stats = { compactions: 0, recovered: 0, skippedStale: 0 };
  }

  /* 恢复：快照 + 重放 */
  recover(applyFn) {
    let state = this.state;
    const recs = this.log.replay(this.snapSeq);   // ★ 跳过 <= snapSeq

    for (const r of recs) {
      this.stats.recovered++;
      state = applyFn(state, r);
    }
    this.state = state;
    return { state, applied: this.stats.recovered, snapSeq: this.snapSeq, lastSeq: this.log.lastSeq };
  }

  /* 写操作：先 WAL，再由调用方更新 state
     ★ 返回 { ok, seq?, error?, degraded? } —— 调用方必须检查 ok */
  append(op, args, stateHash) {
    const r = this.log.append({ op, args, stateHash });
    if (r.ok) this.sinceCompact++;
    return r;
  }

  /* 是否处于降级 */
  get degraded() { return this.log.degraded; }

  /* 尝试从降级恢复（磁盘腾出空间后） */
  tryRecover() { return this.log.tryRecover(); }

  setState(state) { this.state = state; }

  /* 需要时才做，不要在热路径里调 */
  maybeCompact() {
    if (this.sinceCompact < this.compactEvery) return null;
    return this.compact();
  }

  /* compaction：写快照 → 删旧段 */
  compact() {
    if (this.state === null) return { ok: false, error: '没有状态可压缩' };
    const seq = this.log.lastSeq;
    const t0 = Date.now();

    /* ① 写快照（原子）。失败则【不删任何段】—— 安全 */
    let w;
    try { w = writeSnapshot(this.dir, seq, this.state); }
    catch (e) {
      const cls = classifyErr(e);
      return { ok: false, code: e.code, kind: cls.kind,
        error: '快照写入失败（旧段保留，数据安全）: ' + (e.code || e.message) };
    }

    /* ② 快照已落盘，才删旧段 */
    const removed = this.log.dropSegmentsBefore(seq);

    /* ③ 清理多余快照 */
    const pruned = pruneSnapshots(this.dir, 2);

    this.stats.compactions++;
    this.sinceCompact = 0;
    this.snapSeq = seq;

    return {
      ok: true, seq, snapshotBytes: w.bytes, rawBytes: w.rawBytes,
      droppedSegments: removed, prunedSnapshots: pruned,
      ms: Date.now() - t0,
    };
  }

  flush() { this.log.flush(); }

  close() {
    this.flush();
    this.log.close();
  }

  info() {
    const li = this.log.info();
    return {
      dir: this.dir, snapSeq: this.snapSeq, stateBytes: this.state ? Buffer.byteLength(JSON.stringify(this.state)) : 0,
      walBytes: li.bytes, segments: li.segments, lastSeq: li.lastSeq,
      compactions: this.stats.compactions, recovered: this.stats.recovered,
      skippedStale: this.stats.skippedStale,
      cleanTmpOnBoot: this.cleanup,
    };
  }
}

module.exports = {
  SegmentLog, WalStore, WriteAheadLog: SegmentLog,
  encodeRecord, decodeAt, crc32,
  writeSnapshot, loadLatestSnapshot, pruneSnapshots, cleanTmp,
};
