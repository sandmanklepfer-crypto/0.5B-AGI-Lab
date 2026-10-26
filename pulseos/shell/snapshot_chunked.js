'use strict';
/* ==========================================================================
 *  snapshot_chunked.js —— 分块快照（真正的增量）
 *  --------------------------------------------------------------------------
 *  上一版（delta 链）的实测结论：
 *      平均快照 860KB → 86B，省 90% 字节
 *      但 p95 还是 380ms，因为每 10 步要落一次【全量 base】= 320ms
 *
 *  → 关键洞察：只要还有"全量"，就一定会被全量拖死。
 *     真正的解法是让【全量本身也只写变化的块】。
 *
 *  设计：
 *
 *      dir/
 *        blocks/<hash16>.blk        内容寻址的块（天然去重）
 *        snap-<seq>.manifest        块清单（很小，几百字节）
 *
 *      manifest = {
 *        seq, at,
 *        fields: {
 *          memory: { chunks: ['a1b2...', 'c3d4...', ...] },   // 大数组切片
 *          c0:     { value: 0 },                              // 小标量直接存
 *        }
 *      }
 *
 *  写快照：
 *    ① 按字段切块（大数组按 CHUNK 条一片）
 *    ② 每片算 hash，磁盘上已存在就跳过
 *    ③ 只写新块 + manifest
 *
 *  恢复：
 *    ① 读最新 manifest
 *    ② 按顺序把块拼回来
 *
 *  ★ 追加型场景下，只有【最后一片】会变 → 每次只写一个片
 *  ★ 标量型场景下，只有几个小字段变 → 只写 manifest
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');
const { crc32 } = require('./wal');

const CHUNK_ITEMS = 2000;        // 大数组每片多少条
const CHUNK_BYTES = 256 * 1024;  // 单片目标大小
const BLOCK_MAGIC = 0x424C4B31;  // 'BLK1'
const MANIFEST_MAGIC = 0x4D414E31; // 'MAN1'

/* ---------------------------- 块编解码 ---------------------------- */
/* [magic:u32][clen:u32][crc:u32][zlib(JSON)] */
function encodeBlock(value) {
  const raw = Buffer.from(JSON.stringify(value), 'utf8');
  const packed = zlib.deflateRawSync(raw, { level: 6 });
  const head = Buffer.alloc(12);
  head.writeUInt32BE(BLOCK_MAGIC, 0);
  head.writeUInt32BE(packed.length, 4);
  head.writeUInt32BE(crc32(packed), 8);
  return { buf: Buffer.concat([head, packed]), rawBytes: raw.length, packedBytes: packed.length };
}

function decodeBlock(buf) {
  if (!buf || buf.length < 12) return undefined;
  if (buf.readUInt32BE(0) !== BLOCK_MAGIC) return undefined;
  const clen = buf.readUInt32BE(4);
  const crc = buf.readUInt32BE(8);
  if (12 + clen > buf.length) return undefined;
  const packed = buf.subarray(12, 12 + clen);
  if (crc32(packed) !== crc) return undefined;
  try { return JSON.parse(zlib.inflateRawSync(packed).toString('utf8')); }
  catch (e) { return undefined; }
}

const hashOf = (v) => crypto.createHash('sha1').update(JSON.stringify(v)).digest('hex').slice(0, 16);

/* ---------------------------- 切块 ---------------------------- */
/* 把一个字段的值切成若干块。返回 [{hash, value}] */
function chunkify(value) {
  /* 小值（标量/小对象/小数组）不切，直接一块 */
  const approx = JSON.stringify(value).length;
  if (approx <= CHUNK_BYTES || !Array.isArray(value)) {
    return [{ hash: hashOf(value), value }];
  }

  /* 大数组：按条数切 */
  const out = [];
  for (let i = 0; i < value.length; i += CHUNK_ITEMS) {
    const slice = value.slice(i, i + CHUNK_ITEMS);
    out.push({ hash: hashOf(slice), value: slice });
  }
  return out;
}

/* ==========================================================================
 *  ChunkStore
 * ========================================================================== */
class ChunkStore {
  constructor(opts = {}) {
    this.dir = opts.dir;
    this.blockDir = path.join(opts.dir, 'blocks');
    this.keepManifests = opts.keepManifests || 3;
    fs.mkdirSync(this.blockDir, { recursive: true });
    this.stats = {
      writes: 0, blocksWritten: 0, blocksSkipped: 0,
      bytesWritten: 0, bytesSkipped: 0,
      manifestBytes: 0, reads: 0,
    };
    this._known = null;   // Set of hashes on disk（懒加载）
  }

  _loadKnown() {
    if (this._known) return this._known;
    this._known = new Set();
    try {
      for (const f of fs.readdirSync(this.blockDir)) {
        const m = f.match(/^([0-9a-f]{16})\.blk$/);
        if (m) this._known.add(m[1]);
      }
    } catch (e) {}
    return this._known;
  }

  _blockPath(h) { return path.join(this.blockDir, h + '.blk'); }

  /* 写一块（已存在则跳过） */
  _writeBlock(h, value) {
    const known = this._loadKnown();
    if (known.has(h)) {
      this.stats.blocksSkipped++;
      this.stats.bytesSkipped += JSON.stringify(value).length;
      return false;
    }
    const enc = encodeBlock(value);
    const p = this._blockPath(h);
    const tmp = p + '.tmp.' + process.pid;
    fs.writeFileSync(tmp, enc.buf);
    fs.renameSync(tmp, p);
    known.add(h);
    this.stats.blocksWritten++;
    this.stats.bytesWritten += enc.buf.length;
    return true;
  }

  /* 读一块 */
  _readBlock(h) {
    try {
      const buf = fs.readFileSync(this._blockPath(h));
      const v = decodeBlock(buf);
      if (v === undefined) throw new Error('块损坏 ' + h);
      return v;
    } catch (e) {
      throw new Error('读块失败 ' + h + ': ' + e.message);
    }
  }

  /* ---------------- 保存 ---------------- */
  save(seq, state) {
    const t0 = process.hrtime.bigint();

    const manifest = { v: 1, seq, at: Date.now(), fields: {} };

    for (const key of Object.keys(state)) {
      const value = state[key];
      const jsonLen = JSON.stringify(value).length;

      /* 小值：直接塞进 manifest，省一次文件 IO */
      if (jsonLen <= 512) {
        manifest.fields[key] = { inline: value };
        continue;
      }

      /* 大值：切块 */
      const chunks = chunkify(value);
      for (const c of chunks) this._writeBlock(c.hash, c.value);
      manifest.fields[key] = {
        chunks: chunks.map(c => c.hash),
        isArray: Array.isArray(value),
        count: Array.isArray(value) ? value.length : undefined,
      };
    }

    /* 写 manifest（原子） */
    const raw = Buffer.from(JSON.stringify(manifest), 'utf8');
    const packed = zlib.deflateRawSync(raw, { level: 9 });
    const head = Buffer.alloc(12);
    head.writeUInt32BE(MANIFEST_MAGIC, 0);
    head.writeUInt32BE(packed.length, 4);
    head.writeUInt32BE(crc32(packed), 8);

    const name = 'snap-' + String(seq).padStart(12, '0') + '.manifest';
    const dst = path.join(this.dir, name);
    const tmp = path.join(this.dir, '.' + name + '.tmp.' + process.pid);
    fs.writeFileSync(tmp, Buffer.concat([head, packed]));
    fs.renameSync(tmp, dst);

    this.stats.writes++;
    this.stats.manifestBytes = 12 + packed.length;

    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    this._pruneManifests();

    return {
      seq, ms,
      manifestBytes: 12 + packed.length,
      blocksWritten: this.stats.blocksWritten,
      bytesWritten: this.stats.bytesWritten,
      bytesSkipped: this.stats.bytesSkipped,
    };
  }

  _pruneManifests() {
    try {
      const ms = fs.readdirSync(this.dir)
        .filter(f => /^snap-\d+\.manifest$/.test(f))
        .sort().reverse();
      for (let i = this.keepManifests; i < ms.length; i++) {
        try { fs.unlinkSync(path.join(this.dir, ms[i])); } catch (e) {}
      }
    } catch (e) {}
  }

  /* ---------------- 恢复 ---------------- */
  load() {
    const t0 = process.hrtime.bigint();
    let files;
    try {
      files = fs.readdirSync(this.dir).filter(f => /^snap-\d+\.manifest$/.test(f)).sort().reverse();
    } catch (e) { return { state: null, seq: 0, ms: 0 }; }

    for (const f of files) {
      let manifest = null;
      try {
        const buf = fs.readFileSync(path.join(this.dir, f));
        if (buf.readUInt32BE(0) !== MANIFEST_MAGIC) continue;
        const clen = buf.readUInt32BE(4);
        const crc = buf.readUInt32BE(8);
        const packed = buf.subarray(12, 12 + clen);
        if (crc32(packed) !== crc) continue;                 // manifest 坏了，试更早的
        manifest = JSON.parse(zlib.inflateRawSync(packed).toString('utf8'));
      } catch (e) { continue; }
      if (!manifest) continue;

      /* 拼装 */
      try {
        const state = {};
        for (const key of Object.keys(manifest.fields)) {
          const fd = manifest.fields[key];
          if ('inline' in fd) { state[key] = fd.inline; continue; }
          if (!fd.chunks || !fd.chunks.length) { state[key] = fd.isArray ? [] : null; continue; }

          if (fd.isArray) {
            let arr = [];
            for (const h of fd.chunks) {
              const part = this._readBlock(h);
              arr = arr.concat(part);
            }
            state[key] = arr;
          } else {
            state[key] = this._readBlock(fd.chunks[0]);
          }
        }
        this.stats.reads++;
        return { state, seq: manifest.seq, ms: Number(process.hrtime.bigint() - t0) / 1e6 };
      } catch (e) {
        continue;     // 块缺失/损坏，试更早的 manifest
      }
    }
    return { state: null, seq: 0, ms: Number(process.hrtime.bigint() - t0) / 1e6 };
  }

  /* 块垃圾回收：删掉没被任何 manifest 引用的块 */
  gc() {
    const manifests = fs.readdirSync(this.dir).filter(f => /^snap-\d+\.manifest$/.test(f));
    const referenced = new Set();
    for (const f of manifests) {
      try {
        const buf = fs.readFileSync(path.join(this.dir, f));
        const clen = buf.readUInt32BE(4);
        const m = JSON.parse(zlib.inflateRawSync(buf.subarray(12, 12 + clen)).toString('utf8'));
        for (const k of Object.keys(m.fields)) {
          const fd = m.fields[k];
          if (fd.chunks) for (const h of fd.chunks) referenced.add(h);
        }
      } catch (e) {}
    }
    let removed = 0, freed = 0;
    for (const f of fs.readdirSync(this.blockDir)) {
      const mm = f.match(/^([0-9a-f]{16})\.blk$/);
      if (!mm) continue;
      if (!referenced.has(mm[1])) {
        try {
          freed += fs.statSync(path.join(this.blockDir, f)).size;
          fs.unlinkSync(path.join(this.blockDir, f));
          this._known && this._known.delete(mm[1]);
          removed++;
        } catch (e) {}
      }
    }
    return { removedBlocks: removed, freedBytes: freed, referenced: referenced.size };
  }

  diskUsage() {
    let blocks = 0, blkBytes = 0, manBytes = 0;
    try {
      for (const f of fs.readdirSync(this.blockDir)) {
        try { blkBytes += fs.statSync(path.join(this.blockDir, f)).size; blocks++; } catch (e) {}
      }
      for (const f of fs.readdirSync(this.dir)) {
        if (/^snap-\d+\.manifest$/.test(f)) {
          try { manBytes += fs.statSync(path.join(this.dir, f)).size; } catch (e) {}
        }
      }
    } catch (e) {}
    return { blocks, blockBytes: blkBytes, manifestBytes: manBytes, totalBytes: blkBytes + manBytes };
  }

  info() { return Object.assign({}, this.stats, this.diskUsage()); }
}

module.exports = { ChunkStore, chunkify, encodeBlock, decodeBlock, hashOf, CHUNK_ITEMS };
