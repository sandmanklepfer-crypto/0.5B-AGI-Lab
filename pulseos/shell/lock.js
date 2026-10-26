'use strict';
/* ==========================================================================
 *  lock.js —— 多进程独占锁（零依赖）
 *  --------------------------------------------------------------------------
 *  Node 没有内置 fcntl，但有三种可用的原生手段：
 *
 *    ① fs.openSync(path, 'wx')      O_EXCL 创建，原子
 *    ② fs.mkdirSync(path)           目录创建，原子
 *    ③ fs.linkSync(tmp, path)       硬链接，原子
 *
 *  我选 ①，因为：
 *    · 比 mkdir 少一层目录开销
 *    · 文件里能写 PID/时间戳/主机名（用于诊断"谁锁着"）
 *    · 配合 O_EXCL 的原子性由内核保证
 *
 *  ★ 但 ① 有个致命问题：进程被 kill -9 时不会清理锁文件。
 *    所以必须解决「僵尸锁」：
 *
 *      · 锁文件里写 PID
 *      · 抢锁失败时，读 PID，用 kill(pid, 0) 探测进程是否还活着
 *      · 进程已死 → 判定为僵尸锁 → 强夺（但要防两个进程同时强夺）
 *
 *  ★ 强夺本身也有竞态：A 和 B 同时发现锁是僵尸，都去删，都去建。
 *    解法：删除前先 rename 成唯一名字，谁 rename 成功谁负责清理。
 *    rename 在同一文件系统内是原子的，只有一个能成功。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const os = require('os');

const STALE_MS = 30000;      // 超过 30 秒没心跳，视为可疑（配合 PID 探测）

class FileLock {
  /* opts: { dir, name, retries, retryMs, staleMs } */
  constructor(opts = {}) {
    this.dir = opts.dir;
    this.name = opts.name || 'wal';
    this.retries = opts.retries === undefined ? 50 : opts.retries;
    this.retryMs = opts.retryMs || 100;
    this.staleMs = opts.staleMs || STALE_MS;

    fs.mkdirSync(this.dir, { recursive: true });
    this.path = path.join(this.dir, this.name + '.lock');
    this.held = false;
    this.meta = null;
  }

  /* ---------------- 抢锁 ---------------- */
  acquire() {
    for (let i = 0; i <= this.retries; i++) {
      const r = this._tryOnce();
      if (r.ok) return { ok: true, attempts: i + 1, stole: r.stole || false };
      if (r.fatal) return r;
      /* 等一下再试，带抖动避免活锁 */
      const jitter = Math.floor(Math.random() * this.retryMs / 2);
      const until = Date.now() + this.retryMs + jitter;
      while (Date.now() < until) { /* 忙等，避免 async 依赖 */ }
    }
    return { ok: false, error: '抢锁超时（' + this.retries + ' 次）', holder: this._read() };
  }

  _tryOnce() {
    let fd = null;
    try {
      fd = fs.openSync(this.path, 'wx');          // ★ O_EXCL：原子创建
    } catch (e) {
      if (e.code !== 'EEXIST') {
        return { ok: false, fatal: true, error: '无法创建锁文件: ' + e.code };
      }
      /* 锁已存在 → 判断是不是僵尸 */
      const holder = this._read();
      if (!holder) {
        /* 读不出来（可能是刚创建还没写完）→ 当作活锁 */
        return { ok: false, reason: 'lock exists but unreadable' };
      }
      if (!this._isAlive(holder)) {
        const stole = this._steal();
        return stole ? { ok: true, stole: true } : { ok: false, reason: 'steal failed' };
      }
      return { ok: false, reason: 'held by ' + holder.pid + '@' + holder.host };
    }

    /* 抢到了：写元信息 */
    const meta = {
      pid: process.pid,
      host: os.hostname(),
      at: Date.now(),
      hb: Date.now(),
    };
    try {
      fs.writeSync(fd, JSON.stringify(meta));
      fs.closeSync(fd);
    } catch (e) {
      try { fs.closeSync(fd); } catch (e2) {}
      try { fs.unlinkSync(this.path); } catch (e2) {}
      return { ok: false, fatal: true, error: '写锁元信息失败: ' + e.code };
    }

    this.held = true;
    this.meta = meta;
    return { ok: true };
  }

  _read() {
    try {
      const t = fs.readFileSync(this.path, 'utf8');
      if (!t.trim()) return null;
      return JSON.parse(t);
    } catch (e) { return null; }
  }

  /* 判断持有者是否还活着 */
  _isAlive(meta) {
    if (!meta || !meta.pid) return false;

    /* 不同主机：只能靠心跳超时判断 */
    if (meta.host !== os.hostname()) {
      return (Date.now() - (meta.hb || meta.at || 0)) < this.staleMs;
    }

    /* 同主机：直接探 PID */
    try {
      process.kill(meta.pid, 0);        // 不发信号，只检查存在
      return true;                       // 活着
    } catch (e) {
      if (e.code === 'EPERM') return true;   // 存在但没权限（也是活着）
      return false;                            // ESRCH：不存在
    }
  }

  /* 强夺：用 rename 保证只有一个进程能成功清理 */
  _steal() {
    const tmp = this.path + '.stale.' + process.pid + '.' + Date.now();
    try {
      fs.renameSync(this.path, tmp);     // ★ 原子：只有一个进程能 rename 成功
    } catch (e) {
      return false;                       // 别人先抢了
    }
    try { fs.unlinkSync(tmp); } catch (e) {}
    return this._tryOnce().ok;            // 重新抢（现在应该能成）
  }

  /* ---------------- 心跳 ---------------- */
  /* 长任务要定期调，否则别的进程会以为你死了 */
  heartbeat() {
    if (!this.held) return { ok: false, error: '没有持有锁' };
    this.meta.hb = Date.now();
    try {
      fs.writeFileSync(this.path, JSON.stringify(this.meta));
      return { ok: true };
    } catch (e) {
      return { ok: false, error: e.code };
    }
  }

  /* ---------------- 释放 ---------------- */
  release() {
    if (!this.held) return { ok: true, already: true };
    const cur = this._read();
    /* ★ 只释放自己持有的（防止误删别人的锁） */
    if (cur && cur.pid !== process.pid) {
      this.held = false;
      return { ok: false, error: '锁已被别人持有，不释放' };
    }
    try { fs.unlinkSync(this.path); }
    catch (e) { if (e.code !== 'ENOENT') return { ok: false, error: e.code }; }
    this.held = false;
    this.meta = null;
    return { ok: true, released: true };
  }

  /* 查询（不抢，只看） */
  inspect() {
    const meta = this._read();
    return {
      path: this.path,
      exists: meta !== null,
      holder: meta,
      alive: meta ? this._isAlive(meta) : null,
      ageMs: meta ? Date.now() - (meta.at || 0) : null,
    };
  }
}

/* ==========================================================================
 *  LockedStore —— WAL + 独占锁的组合
 * ========================================================================== */
class LockedStore {
  constructor(opts) {
    const { WalStore } = require('./wal');
    this.dir = opts.dir;
    this.lock = new FileLock({ dir: opts.dir, name: opts.name || 'wal' });

    const r = this.lock.acquire();
    if (!r.ok) {
      const e = new Error('无法获得独占锁: ' + (r.error || JSON.stringify(r.holder || {})));
      e.lockFailed = true;
      e.holder = r.holder;
      throw e;
    }

    this.store = new WalStore(opts);
    this.hbTimer = null;
    if (opts.heartbeatMs !== 0) {
      const ms = opts.heartbeatMs || 5000;
      this.hbTimer = setInterval(() => this.lock.heartbeat(), ms);
      if (this.hbTimer.unref) this.hbTimer.unref();
    }
  }

  append(op, args, h) { return this.store.append(op, args, h); }
  setState(s) { this.store.setState(s); }
  recover(fn) { return this.store.recover(fn); }
  compact() { return this.store.compact(); }
  maybeCompact() { return this.store.maybeCompact(); }
  flush() { return this.store.flush(); }
  get degraded() { return this.store.degraded; }
  info() { return Object.assign(this.store.info(), { lock: this.lock.inspect() }); }

  close() {
    if (this.hbTimer) { clearInterval(this.hbTimer); this.hbTimer = null; }
    try { this.store.close(); } catch (e) {}
    return this.lock.release();
  }
}

module.exports = { FileLock, LockedStore };
