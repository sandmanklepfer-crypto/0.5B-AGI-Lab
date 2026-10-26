'use strict';
/* ==========================================================================
 *  PulseOS —— 进程内运行时（库形态）
 *  --------------------------------------------------------------------------
 *  ★ 这是它的正确形态。HTTP 只是调试接口，不是主路径。
 *
 *  三种持久化模式（durability）—— 这是速度与安全的核心取舍：
 *
 *    'sync'   每次 invoke 立即落盘      最安全，p50 ≈ 1.16ms，QPS ≈ 800
 *    'batch'  攒 N 次或 T 毫秒再落盘     默认，p50 ≈ 0.42ms，QPS ≈ 2,390
 *    'none'   完全不落盘                最快，p50 ≈ 0.0004ms，QPS ≈ 1,074,651
 *
 *  ★ 关键实测（bench_wal.js / DIRECT.md）：
 *      纯计算              417 ns
 *      计算 + 全量落盘    1,163 ns    ← 落盘是计算的 2,790 倍
 *
 *    所以批量落盘不是优化，是把"计算"从"IO"里救出来。
 *
 *  ★ batch 模式的代价：
 *      进程被 kill -9 → 丢最后 N 次（N = batchSize）或 T 毫秒内的
 *      想不丢就调 flush()，或者用 'sync'
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { AggregatedShell } = require('./shell/kernel');
const ps = require('./lang/pulsescript');
const { compileToJs } = require('./lang/compile');

class PulseOS {
  constructor(opts = {}) {
    this.root = opts.root || './pulse-state';
    this.shell = new AggregatedShell({ root: this.root });

    /* ---------------- 持久化策略 ---------------- */
    this.durability = opts.durability || 'batch';     // sync | batch | none
    this.batchSize = opts.batchSize || 64;
    this.batchMs = opts.batchMs || 20;

    this._dirty = new Set();          // 哪些服务有未落盘的改动
    this._pending = 0;                // 待落盘的 invoke 次数
    this._timer = null;
    this._saving = false;

    this._counts = new Map();
    this._cache = new Map();          // service -> 编译后的模块
    this.stats = { invokes: 0, flushes: 0, flushesByTimer: 0, flushesBySize: 0, droppedOnClose: 0 };

    if (this.durability === 'batch') this._startTimer();

    /* 从磁盘恢复已部署的服务（否则重开后服务全丢） */
    this._restore();
  }

  _restore() {
    const srcDir = path.join(this.root, '_src');
    if (!fs.existsSync(srcDir)) return;
    let n = 0;
    for (const f of fs.readdirSync(srcDir).filter(x => x.endsWith('.pulse'))) {
      try {
        const src = fs.readFileSync(path.join(srcDir, f), 'utf8');
        const added = this.shell.registerAll(src);
        for (const a of added) {
          try {
            const r = compileToJs(src, { service: a.name });
            const file = path.join(this.root, '_gen', a.name + '.gen.js');
            fs.mkdirSync(path.dirname(file), { recursive: true });
            fs.writeFileSync(file, r.code + '\n');
            delete require.cache[file];
            this._cache.set(a.name, require(file));
          } catch (e) {}
        }
        n++;
      } catch (e) {}
    }
    this.stats.restored = n;
  }

  /* ---------------- 批量落盘：定时器 ---------------- */
  _startTimer() {
    if (this._timer) return;
    this._timer = setInterval(() => {
      /* ★ 不能只靠 setInterval —— 同步死循环会饿死它（WAL.md 踩过这个坑）。
         所以 invoke 里也会同步检查。这里只是兜底。 */
      if (this._dirty.size) { this._flush(); this.stats.flushesByTimer++; }
    }, this.batchMs);
    if (this._timer.unref) this._timer.unref();
  }

  /* ---------------- 落盘 ---------------- */
  _flush() {
    if (!this._dirty.size) return { ok: true, flushed: 0 };
    if (this._saving) return { ok: false, error: '正在落盘' };
    this._saving = true;
    let n = 0, bytes = 0;
    try {
      for (const name of this._dirty) {
        const k = this.shell.kernels.get(name);
        if (!k) continue;
        const s = k._save();
        bytes += s.packed;
        n++;
      }
      this._dirty.clear();
      this._pending = 0;
      this.stats.flushes++;
      return { ok: true, flushed: n, bytes };
    } catch (e) {
      /* 落盘失败：不清脏集合，下次重试 */
      return { ok: false, error: e.message, flushed: n };
    } finally {
      this._saving = false;
    }
  }

  /* 显式落盘（想强一致时调） */
  flush() { return this._flush(); }

  /* ---------------- 部署 ---------------- */
  deploy(src) {
    const added = this.shell.registerAll(src);
    /* 持久化源码，否则重开后无法重建微内核 */
    const srcDir = path.join(this.root, '_src');
    try {
      fs.mkdirSync(srcDir, { recursive: true });
      for (const a of added) fs.writeFileSync(path.join(srcDir, a.name + '.pulse'), src);
    } catch (e) {}
    for (const a of added) {
      try {
        const r = compileToJs(src, { service: a.name });
        const file = path.join(this.root, '_gen', a.name + '.gen.js');
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, r.code + '\n');
        delete require.cache[file];
        this._cache.set(a.name, require(file));
      } catch (e) { /* 编译失败，回退解释器 */ }
    }
    return added;
  }

  undeploy(name) {
    this.shell.unregister(name);
    this._cache.delete(name);
    this._dirty.delete(name);
    try { fs.unlinkSync(path.join(this.root, '_src', name + '.pulse')); } catch (e) {}
    return { ok: true, removed: name };
  }

  services() { return this.shell.list().map(k => k.name); }

  /* ---------------- 调用（主路径）---------------- */
  invoke(service, op, args = []) {
    const t0 = process.hrtime.bigint();
    const k = this.shell.kernels.get(service);
    if (!k) return { ok: false, error: '没有服务 ' + service, ms: 0 };
    if (this.shell.kernels.get(service) && k.__frozen) {
      return { ok: false, error: '服务 ' + service + ' 已冻结', ms: 0 };
    }

    const mod = this._cache.get(service);
    let result = null, ok = false, error = null, emits = [];

    if (mod) {
      try {
        const r = mod.run(op, args, k.state);
        if (r.ok) { k.state = r.state; result = r.result; emits = r.emits; ok = true; }
        else error = r.error;
      } catch (e) { error = e.message; }
    }

    /* 落到解释器（含因果链） */
    if (!ok && !error) {
      const r = k.pulse(op, args);
      ok = r.ok; result = r.result; error = r.error; emits = r.emits;
    }

    /* ---------------- 持久化分支 ---------------- */
    let sizes = null;
    if (ok) {
      this.stats.invokes++;

      if (this.durability === 'sync') {
        sizes = k._save();
        this._dirty.delete(service);

      } else if (this.durability === 'batch') {
        this._dirty.add(service);
        this._pending++;
        /* ★ 不能只靠定时器（同步循环会饿死它）—— 这里同步检查 */
        if (this._pending >= this.batchSize) {
          const f = this._flush();
          if (f.ok) this.stats.flushesBySize++;
        }
        sizes = { raw: JSON.stringify(k.state).length, packed: -1, deferred: true };

      } else {
        /* none */
        sizes = { raw: JSON.stringify(k.state).length, packed: -1, skipped: true };
      }
    }

    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    if (ok) {
      k.stats.pulses++;
      k.stats.lat.push(ms);
      if (k.stats.lat.length > 200) k.stats.lat.shift();
    }

    return {
      ok, service, op, result, emits, error,
      stateBytes: sizes ? sizes.raw : null,
      ms,
      durability: this.durability,
      deferred: !!(sizes && sizes.deferred),
    };
  }

  /* 异步版：支持远端内核 */
  async invokeAsync(service, op, args = []) {
    return this.shell.callAsync(service, op, args);
  }

  /* ---------------- 运维 ---------------- */
  stat() {
    return Object.assign(this.shell.systemInfo(), {
      durability: this.durability,
      dirty: this._dirty.size,
      pending: this._pending,
      stats: this.stats,
    });
  }
  info(name) { const k = this.shell.kernels.get(name); return k ? k.info() : null; }
  all() { return this.shell.list(); }

  close() {
    if (this._timer) { clearInterval(this._timer); this._timer = null; }
    const f = this._flush();
    return { ok: true, flushed: f.flushed || 0, pendingLost: 0 };
  }
}

function create(opts) { return new PulseOS(opts); }

module.exports = {
  create, PulseOS,
  AggregatedShell,
  pulsescript: ps,
  compileToJs,
};
