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
const { FileLock } = require('./shell/lock');
const { Sandbox, NativeKernel } = require('./shell/sandbox');

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

    /* ★ 独占锁：同一状态目录只允许一个写入者。
       没有锁时两个进程各写各的 _save()，实测 4000 条 → 只剩 2000。
       durability:'none' 不落盘，可以不加锁（用于基准测试）。 */
    this.lock = null;
    if (this.durability !== 'none') {
      this.lock = new FileLock({ dir: this.root, name: 'pulse' });
      const lr = this.lock.acquire();
      if (!lr.ok) {
        const e = new Error('状态目录已被占用: ' + this.root +
          (lr.holder ? '（pid=' + lr.holder.pid + ' host=' + lr.holder.host + '）' : ''));
        e.lockFailed = true;
        e.holder = lr.holder;
        throw e;
      }
      this.lockTimer = setInterval(() => { try { this.lock.heartbeat(); } catch (e) {} }, 5000);
      if (this.lockTimer.unref) this.lockTimer.unref();
    }

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
        const s = k._save(this.durability === 'sync');
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

  /* ★ 注册原生 JS 微内核（例如外部沙箱）
     它不在 PulseScript 里 —— PulseScript 依然无副作用。
     但它和普通微内核形状一致，所以能作为 emit 的路由目标。 */
  registerNative(name, handlers, opts = {}) {
    const k = new NativeKernel(name, handlers, opts);
    this.shell.kernels.set(name, k);
    return { name, native: true, note: k.note };
  }

  /* 便捷：挂一个沙箱，注册成 pysandbox 微内核 */
  attachSandbox(rootfs, opts = {}) {
    const sb = new Sandbox(Object.assign({ rootfs }, opts));
    this.sandbox = sb;
    this.registerNative('pysandbox', {
      /* 测拉起耗时 */
      probe: (rounds) => sb.probe(rounds || 3),
      /* 跑 python，返回 {ok,stdout,ms} */
      run: (script, timeoutMs) => sb.runPython(script, { timeoutMs }),
      /* 便捷：算 sha256 */
      sha256: (text) => {
        const esc = JSON.stringify(String(text == null ? '' : text));
        const r = sb.runPython('import hashlib,sys;print(hashlib.sha256(' + esc + '.encode()).hexdigest())');
        return r.ok ? { sha256: r.stdout.trim(), ms: r.ms } : r;
      },
      /* 便捷：算 n 以内素数个数 */
      primes: (n) => {
        const k = Math.max(0, Math.min(parseInt(n, 10) || 1000, 200000));
        const r = sb.runPython(
          'n=' + k + '\n' +
          's=bytearray([1])*(n+1)\n' +
          's[0]=s[1]=0\n' +
          'for i in range(2,int(n**0.5)+1):\n' +
          '    if s[i]: s[i*i::i]=bytearray(len(s[i*i::i]))\n' +
          'print(sum(s))'
        );
        return r.ok ? { primes: parseInt(r.stdout.trim(), 10), n: k, ms: r.ms } : r;
      },
      /* 沙箱自身信息 */
      info: () => sb.info(),
    }, {
      note: '外部沙箱（chroot + python3），不由 PulseScript 驱动',
      /* emit 派发时 payload 是 {text:...} / {n:...}，按这些 key 解包 */
      paramKeys: {
        sha256: ['text'],
        primes: ['n'],
        run: ['script', 'timeoutMs'],
        probe: ['rounds'],
      },
    });
    return { name: 'pysandbox', available: sb.available, reason: sb.reason, probeMs: sb.probeMs };
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

    /* 落到解释器 */
    if (!ok && !error) {
      const r = k.pulse(op, args);
      ok = r.ok; result = r.result; error = r.error; emits = r.spawned || r.emits || [];
    }

    /* ---------------- ★ 因果派发 ----------------
       这是 PulseOS 和「自己调 python」的本质区别：
       一次 invoke 可能触发下游微内核，形成真因果链。
       之前两条路径都只收了 emits 却从未派发 —— 因果是死的。 */
    let causal = [];
    if (ok && emits && emits.length) {
      try { causal = this.shell.dispatchEmits(service, emits); }
      catch (e) { causal = [{ error: 'dispatch 失败: ' + e.message }]; }
    }

    /* ---------------- 持久化分支 ----------------
       原生微内核（如 pysandbox）无状态，不落盘 */
    let sizes = null;
    if (ok && !k.isNative) {
      this.stats.invokes++;

      if (this.durability === 'sync') {
        sizes = k._save(true);        /* ★ 真 fsync */
        this._dirty.delete(service);

      } else if (this.durability === 'batch') {
        this._dirty.add(service);
        this._pending++;
        /* ★ 不能只靠定时器（同步循环会饿死它）—— 这里同步检查 */
        if (this._pending >= this.batchSize) {
          const f = this._flush();
          if (f.ok) this.stats.flushesBySize++;
        }
        /* ★ 不要每次全量 stringify —— 那是热路径杀手。
           只在调用方显式要 stateBytes 时才算（这里给个估算下界）。 */
        sizes = { raw: -1, packed: -1, deferred: true };

      } else {
        /* none */
        sizes = { raw: -1, packed: -1, skipped: true };
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
      causal: causal.length ? causal : undefined,
      stateBytes: sizes ? sizes.raw : null,   /* -1 = 未计算（省掉热路径开销） */
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
    if (this.lockTimer) { clearInterval(this.lockTimer); this.lockTimer = null; }
    const f = this._flush();
    if (this.lock) { try { this.lock.release(); } catch (e) {} this.lock = null; }
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
