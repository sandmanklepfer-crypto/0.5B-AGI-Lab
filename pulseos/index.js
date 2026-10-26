'use strict';
/* ==========================================================================
 *  PulseOS —— 进程内运行时（库形态）
 *  --------------------------------------------------------------------------
 *  ★ 这才是它的正确形态。
 *
 *  之前的 server.js 是「HTTP 包装」，测出的 QPS 359 是 Node HTTP 的极限，
 *  不是 PulseOS 的能力。pulse 本身只要 2.76ms，剩下 127ms 全花在
 *  TCP 握手、HTTP 头解析、JSON 往返、事件循环排队上。
 *
 *  用法（零网络）：
 *
 *      const pulse = require('pulseos');
 *      const rt = pulse.create({ dir: './state' });
 *
 *      rt.deploy(`
 *        service counter {
 *          state { n: int = 0 }
 *          on "inc" { set n = n + 1 return n }
 *        }
 *      `);
 *
 *      const r = rt.invoke('counter', 'inc');
 *      // { ok: true, result: 1, ms: 0.42, stateBytes: 8 }
 *
 *  HTTP 保留为【调试接口】，不是主路径。
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
    this.autoCompact = opts.autoCompact !== false;
    this.compactEvery = opts.compactEvery || 5000;
    this._counts = new Map();
    this._cache = new Map();      // service -> 编译后的模块（比每次走解释器快）
  }

  /* ---------------- 部署 ---------------- */
  /* 接受源码，返回部署了哪些服务 */
  deploy(src) {
    const added = this.shell.registerAll(src);
    /* 编译成 JS 以走快路径（可选，失败就回退解释器） */
    for (const a of added) {
      try {
        const r = compileToJs(src, { service: a.name });
        const file = path.join(this.root, '_gen', a.name + '.gen.js');
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, r.code + '\n');
        delete require.cache[file];
        this._cache.set(a.name, require(file));
      } catch (e) {
        /* 编译失败不是错误，解释器能跑就行 */
      }
    }
    return added;
  }

  undeploy(name) {
    this.shell.unregister(name);
    this._cache.delete(name);
    return { ok: true, removed: name };
  }

  services() { return this.shell.list().map(k => k.name); }

  /* ---------------- 调用（主路径）---------------- */
  /* 同步版：只支持本地内核，最快。这是压测和嵌入调用的入口。 */
  invoke(service, op, args = []) {
    const t0 = process.hrtime.bigint();
    const k = this.shell.kernels.get(service);
    if (!k) return { ok: false, error: '没有服务 ' + service, ms: 0 };

    /* 快路径：编译过的模块 */
    const mod = this._cache.get(service);
    if (mod) {
      try {
        const r = mod.run(op, args, k.state);
        if (r.ok) {
          k.state = r.state;
          const sizes = k._save();
          k.stats.pulses++;
          const ms = Number(process.hrtime.bigint() - t0) / 1e6;
          k.stats.lat.push(ms);
          if (k.stats.lat.length > 200) k.stats.lat.shift();
          return {
            ok: true, service, op, result: r.result,
            emits: r.emits, stateBytes: sizes.raw, ms,
          };
        }
      } catch (e) {
        /* 落到解释器路径 */
      }
    }

    /* 慢路径：解释器（含因果链） */
    const r = k.pulse(op, args);
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    return {
      ok: r.ok, service, op,
      result: r.result, emits: r.emits,
      stateBytes: r.stateSize ? r.stateSize.raw : null,
      error: r.error, ms,
    };
  }

  /* 异步版：支持远端内核（有网络时用它） */
  async invokeAsync(service, op, args = []) {
    return this.shell.callAsync(service, op, args);
  }

  /* ---------------- 运维 ---------------- */
  stat() { return this.shell.systemInfo(); }
  info(name) { const k = this.shell.kernels.get(name); return k ? k.info() : null; }
  all() { return this.shell.list(); }

  close() {
    for (const k of this.shell.kernels.values()) {
      try { k._save(); } catch (e) {}
    }
    return { ok: true };
  }
}

/* ---------------------------- 对外 ---------------------------- */
function create(opts) { return new PulseOS(opts); }

module.exports = {
  create, PulseOS,
  /* 直接暴露底层，方便高级用法 */
  AggregatedShell,
  pulsescript: ps,
  compileToJs,
};
