'use strict';
/* ==========================================================================
 *  wal.js —— 预写日志：三种持久化策略
 *  --------------------------------------------------------------------------
 *  核心矛盾：
 *
 *      状态箱在内存里 → 断电即失       （快，但会丢数据）
 *      每次脉冲都 fsync → 7ms 变 20ms  （可靠，但脉冲优势消失）
 *
 *  所以这不是"加不加 WAL"的问题，是"用哪种持久化等级"的问题。
 *
 *  三种策略，按代价从低到高：
 *
 *    ① none      不落盘，纯内存          最快，断电全丢
 *    ② os        写文件但不 fsync        快，断电丢最后几次（OS 页缓存会写盘）
 *    ③ fsync     每次 writeSync + fsync  慢，断电不丢已确认的
 *    ④ group     攒一批再 fsync          折中，牺牲 ≤N ms 的数据
 *
 *  ★ 关键设计：WAL 记录的是【操作】，不是【状态】
 *     重放时再执行一遍，所以日志比状态小，而且天然支持审计。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const crypto = require('crypto');

const MAGIC = 0x57414c31;   // 'WAL1'

/* ---------------------------- 单条记录 ---------------------------- */
/* 格式：[len:u32][crc:u32][payload]
   payload = zlib(JSON{ seq, op, args, ts, stateHash }) */
function encodeRecord(rec) {
  const raw = Buffer.from(JSON.stringify(rec), 'utf8');
  const packed = zlib.deflateRawSync(raw, { level: 1 });   // 日志用 level 1，快
  const crc = crc32(packed);
  const head = Buffer.alloc(12);
  head.writeUInt32BE(packed.length, 0);
  head.writeUInt32BE(crc >>> 0, 4);
  head.writeUInt32BE(MAGIC, 8);
  return Buffer.concat([head, packed]);
}

function decodeRecord(buf, off) {
  if (off + 12 > buf.length) return null;
  const len = buf.readUInt32BE(off);
  const crc = buf.readUInt32BE(off + 4);
  const magic = buf.readUInt32BE(off + 8);
  if (magic !== MAGIC) return null;
  if (off + 12 + len > buf.length) return null;
  const packed = buf.subarray(off + 12, off + 12 + len);
  if ((crc32(packed) >>> 0) !== crc) return null;     // CRC 不符 = 截断或损坏
  try {
    return { rec: JSON.parse(zlib.inflateRawSync(packed).toString('utf8')), next: off + 12 + len };
  } catch (e) { return null; }
}

/* CRC32（表驱动，够快） */
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

/* ==========================================================================
 *  WriteAheadLog
 * ========================================================================== */
class WriteAheadLog {
  /* opts: { dir, name, mode: 'none'|'os'|'fsync'|'group', groupMs, maxBytes } */
  constructor(opts) {
    this.dir = opts.dir;
    this.name = opts.name;
    this.mode = opts.mode || 'os';
    this.groupMs = opts.groupMs || 10;
    this.maxBytes = opts.maxBytes || 4 * 1024 * 1024;

    fs.mkdirSync(this.dir, { recursive: true });
    this.file = path.join(this.dir, this.name + '.wal');
    this.fd = null;
    this.seq = 0;
    this.bytes = 0;
    this.pending = [];           // group 模式：待 fsync 的 seq

    this.stats = { appends: 0, fsyncs: 0, groups: 0, truncations: 0, replays: 0, recovered: 0 };

    this._open();
    if (this.mode === 'group') this._startGroupTimer();
  }

  _open() {
    const exists = fs.existsSync(this.file);
    this.fd = fs.openSync(this.file, exists ? 'r+' : 'w+');
    if (exists) {
      const st = fs.fstatSync(this.fd);
      this.bytes = st.size;
    }
  }

  /* ---------------- 追加 ---------------- */
  /* rec = { op, args, stateHash } */
  append(rec) {
    if (this.mode === 'none') {
      this.seq++;
      return this.seq;
    }

    const full = Object.assign({ seq: this.seq + 1, ts: Date.now() }, rec);
    const buf = encodeRecord(full);

    fs.writeSync(this.fd, buf, 0, buf.length, this.bytes);
    this.bytes += buf.length;
    this.seq = full.seq;
    this.stats.appends++;

    if (this.mode === 'fsync') {
      fs.fsyncSync(this.fd);
      this.stats.fsyncs++;
    } else if (this.mode === 'group') {
      this.pending.push(this.seq);
      /* ★ 不能只靠 setInterval —— 同步循环会让它永远不触发。
         所以在 append 里同步检查时间，两个机制互为兜底。 */
      const now = Date.now();
      if (now - (this._lastFlush || 0) >= this.groupMs) {
        try { fs.fsyncSync(this.fd); this.stats.fsyncs++; this.stats.groups++; } catch (e) {}
        this.pending = [];
        this._lastFlush = now;
      }
    }
    /* mode 'os'：不 fsync，交给 OS 页缓存 */

    /* 自动轮转 */
    if (this.bytes > this.maxBytes) this.rotate();
    return this.seq;
  }

  _startGroupTimer() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      if (this.pending.length) {
        try { fs.fsyncSync(this.fd); this.stats.fsyncs++; this.stats.groups++; this._lastFlush = Date.now(); }
        catch (e) {}
        this.pending = [];
      }
    }, this.groupMs);
    if (this._timer.unref) this._timer.unref();
  }

  /* 显式冲刷（关闭前 / 需要强一致时） */
  flush() {
    if (this.mode === 'none') return;
    if (this.mode === 'fsync') return;    // 已经每次都 fsync
    try { fs.fsyncSync(this.fd); this.stats.fsyncs++; } catch (e) {}
    this.pending = [];
  }

  /* ---------------- 重放 ---------------- */
  /* 返回所有能读出来的记录（遇到损坏就停，视为日志尾部被截断） */
  replay() {
    const out = [];
    if (!fs.existsSync(this.file)) return out;
    const buf = fs.readFileSync(this.file);
    let off = 0;
    while (off < buf.length) {
      const r = decodeRecord(buf, off);
      if (!r) { this.stats.truncations++; break; }   // 截断/损坏，到此为止
      out.push(r.rec);
      off = r.next;
    }
    this.stats.replays++;
    this.stats.recovered = out.length;
    if (out.length) this.seq = out[out.length - 1].seq;
    return out;
  }

  /* ---------------- 轮转 ---------------- */
  rotate() {
    try {
      fs.closeSync(this.fd);
      const bak = this.file + '.' + Date.now();
      fs.renameSync(this.file, bak);
      this.fd = fs.openSync(this.file, 'w+');
      this.bytes = 0;
    } catch (e) {}
  }

  close() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    this.flush();
    if (this.fd !== null) { try { fs.closeSync(this.fd); this.fd = null; } catch (e) {} }
  }

  info() {
    return { mode: this.mode, seq: this.seq, bytes: this.bytes, ...this.stats };
  }
}

module.exports = { WriteAheadLog, encodeRecord, decodeRecord, crc32 };
