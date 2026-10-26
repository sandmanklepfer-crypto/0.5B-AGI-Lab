'use strict';
/* ==========================================================================
 *  kernel.js —— 聚合态 OS 的内核（把散落微内核聚成一个系统）
 *  --------------------------------------------------------------------------
 *  职责：
 *    1. 注册 PulseScript 服务（编译 + 静态检查）
 *    2. 每个服务持有独立状态，落盘为「状态箱」
 *    3. 一次脉冲：唤醒 → 执行 → 派生 emit → 挂起
 *    4. 因果链：emit 可以触发另一个服务的脉冲（派生 Spawn）
 *    5. 统计：脉冲次数、状态大小、延迟分布
 *
 *  ★ 关键设计：状态箱与代码分离。
 *     代码在仓库里（可 git diff），状态在 state/ 目录（可单独备份/迁移）。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const ps = require('../lang/pulsescript');
const { RemoteKernel } = require('./remote');

class MicroKernel {
  /* spec = { name, src, statePath } */
  constructor(spec, opts = {}) {
    this.name = spec.name;
    this.src = spec.src;
    this.statePath = spec.statePath;
    this.maxCausalDepth = opts.maxCausalDepth || 8;

    const { ast, diag } = ps.compile(spec.src);
    if (diag.errors.length) {
      throw new Error('编译失败:\n  ' + diag.errors.join('\n  '));
    }
    const svc = ast.services.find(s => s.name === spec.name) || ast.services[0];
    if (!svc) throw new Error('源码里没有 service 定义');
    this.svc = svc;
    this.warnings = diag.warnings;

    this.state = this._load();
    this.stats = {
      pulses: 0,
      emits: 0,
      errors: 0,
      lat: [],          // 最近 200 次总延迟
      lastPulse: null,
    };
  }

  /* ---------- 状态箱：落盘 / 恢复 ---------- */
  _load() {
    try {
      const buf = fs.readFileSync(this.statePath);
      if (buf.length < 8) return ps.makeState(this.svc);
      const raw = zlib.inflateRawSync(buf);
      return JSON.parse(raw.toString('utf8'));
    } catch (e) {
      return ps.makeState(this.svc);
    }
  }

  _save() {
    fs.mkdirSync(path.dirname(this.statePath), { recursive: true });
    const raw = Buffer.from(JSON.stringify(this.state), 'utf8');
    const packed = zlib.deflateRawSync(raw, { level: 9 });
    fs.writeFileSync(this.statePath, packed);
    return { raw: raw.length, packed: packed.length };
  }

  /* ---------- 一次脉冲 ---------- */
  pulse(op, args = [], depth = 0) {
    const t0 = process.hrtime.bigint();

    // ① 唤醒（状态已在内存时是零成本；跨进程时来自 _load）
    const tWake = process.hrtime.bigint();

    // ② 执行
    let r;
    try {
      r = ps.runHandler(this.svc, op, args, this.state);
    } catch (e) {
      this.stats.errors++;
      return { ok: false, error: String(e.message), totalMs: 0 };
    }
    if (!r.ok) { this.stats.errors++; return r; }

    // ③ 挂起
    this.state = r.state;
    const sizes = this._save();
    const tEnd = process.hrtime.bigint();

    const ms = Number(tEnd - t0) / 1e6;
    this.stats.pulses++;
    this.stats.lastPulse = Date.now();
    this.stats.lat.push(ms);
    if (this.stats.lat.length > 200) this.stats.lat.shift();

    // ④ 派生：把 emit 交给外层调度（因果链）
    const spawned = [];
    if (depth < this.maxCausalDepth) {
      for (const e of r.emits) spawned.push({ from: this.name, ...e });
    }

    return {
      ok: true,
      service: this.name,
      op,
      result: r.result,
      emits: r.emits,
      spawned,
      stateSize: sizes,
      totalMs: +ms.toFixed(3),
    };
  }

  info() {
    const lat = this.stats.lat.slice().sort((a, b) => a - b);
    const pct = (p) => (lat.length ? +lat[Math.min(lat.length - 1, Math.floor(lat.length * p))].toFixed(3) : null);
    const sz = ps.stateSize(this.state);
    return {
      name: this.name,
      handlers: this.svc.handlers.map(h => ({ op: h.op, params: h.params })),
      fields: this.svc.state.map(f => f.name + ':' + f.type),
      warnings: this.warnings,
      stateBytes: sz.raw,
      state: sz.json.length > 400 ? sz.json.slice(0, 400) + '…' : sz.json,
      pulses: this.stats.pulses,
      emits: this.stats.emits,
      errors: this.stats.errors,
      lat: { p50: pct(0.5), p95: pct(0.95), n: lat.length },
    };
  }
}

/* ==========================================================================
 *  AggregatedShell —— 聚合层：多个微内核 = 一个系统
 * ========================================================================== */
class AggregatedShell {
  constructor(opts = {}) {
    this.root = opts.root || path.join(__dirname, '..', 'state');
    this.kernels = new Map();
    this.causalLog = [];       // 因果链记录
    this.bootAt = Date.now();
  }

  /* 注册源码里的【全部】服务（单文件多服务） */
  registerAll(src) {
    const { ast, diag } = ps.compile(src);
    if (diag.errors.length) {
      const e = new Error(diag.errors.join('\n'));
      e.diagnostics = diag;
      throw e;
    }
    const added = [];
    for (const svc of ast.services) {
      const k = new MicroKernel({
        name: svc.name, src,
        statePath: path.join(this.root, svc.name + '.box'),
      });
      this.kernels.set(svc.name, k);
      added.push({ name: svc.name, warnings: k.warnings });
    }
    if (!added.length) throw new Error('源码里没有 service 定义');
    return added;
  }

  /* 兼容：注册单个（默认第一个） */
  register(src, name) {
    if (!name) {
      const all = this.registerAll(src);
      return all[0];
    }
    const { ast, diag } = ps.compile(src);
    if (diag.errors.length) {
      const e = new Error(diag.errors.join('\n'));
      e.diagnostics = diag;
      throw e;
    }
    const svc = ast.services.find(s => s.name === name);
    if (!svc) throw new Error('源码里没有名为 ' + name + ' 的 service');
    const k = new MicroKernel({
      name: svc.name, src,
      statePath: path.join(this.root, svc.name + '.box'),
    });
    this.kernels.set(svc.name, k);
    return { name: svc.name, warnings: k.warnings };
  }

  /* 把一台远端设备上的某个服务，作为一个"远端微内核"挂进来
     ★ 挂进来之后，它在聚合层眼里和本地微内核无差别 */
  attachRemote(name, host, port, label) {
    const k = new RemoteKernel({ name, host, port, label });
    this.kernels.set(name + '@' + (label || (host + ':' + port)), k);
    return k;
  }

  /* 扫描远端设备上有哪些服务，全部挂进来 */
  async discoverRemote(host, port, label) {
    const { RemoteKernel: RK } = require('./remote');
    const tmp = new RK({ name: '__probe', host, port });
    const s = await tmp.sync().catch(() => null);
    if (!s) {
      // sync 只拿单个服务，探测要用 /api/state
      const http = require('http');
      const all = await new Promise((resolve) => {
        const req = http.request({ host, port, path: '/api/state', method: 'GET', timeout: 6000 }, (res) => {
          const c = []; res.on('data', d => c.push(d));
          res.on('end', () => { try { resolve(JSON.parse(Buffer.concat(c).toString())); } catch (e) { resolve(null); } });
        });
        req.on('error', () => resolve(null));
        req.on('timeout', () => { req.destroy(); resolve(null); });
        req.end();
      });
      if (!all) return [];
    }
    return [];
  }

  unregister(name) {
    const k = this.kernels.get(name);
    if (k) {
      try { fs.unlinkSync(k.statePath); } catch (e) {}
      this.kernels.delete(name);
    }
  }

  /* ---------- 派生路由：先本服务，再全局唯一匹配 ---------- */
  resolveTarget(fromService, op) {
    const self = this.kernels.get(fromService);
    if (self && self.svc.handlers.some(h => h.op === op)) return fromService;
    const hits = [];
    for (const [name, k] of this.kernels) {
      if (k.svc.handlers.some(h => h.op === op)) hits.push(name);
    }
    return hits.length === 1 ? hits[0] : (hits.includes(fromService) ? fromService : null);
  }

  /* ---------- 调用：统一入口（本地同步 / 远端异步都能用） ---------- */
  async callAsync(service, op, args = []) {
    const trace = [];
    const queue = [{ service, op, args, depth: 0, from: null }];
    let last = null, guard = 0;

    while (queue.length && guard++ < 64) {
      const job = queue.shift();
      const kern = this.kernels.get(job.service);
      if (!kern) { trace.push({ service: job.service, op: job.op, from: job.from, ok: false, error: '没有这个微内核' }); continue; }

      const r = await kern.pulse(job.op, job.args, job.depth);
      trace.push({
        service: job.service, op: job.op, from: job.from,
        ok: r.ok,
        ms: r.totalMs === undefined ? null : r.totalMs,
        stateBytes: r.stateSize ? r.stateSize.raw : null,
        error: r.error,
        result: r.result === undefined ? null : r.result,
        remote: r.remote || null,
      });
      last = r;

      // 本地内核才继续传播因果（远端自己管自己的链）
      if (r.ok && r.spawned && r.spawned.length) {
        for (const e of r.spawned) {
          const target = (e.payload && e.payload.__to) || this.resolveTarget(job.service, e.op);
          if (!target) continue;
          queue.push({ service: target, op: e.op, args: [e.payload], depth: job.depth + 1, from: job.service + '.' + job.op });
          kern.stats.emits++;
        }
      }
    }

    this.causalLog.push({ t: Date.now(), service, op, trace });
    if (this.causalLog.length > 100) this.causalLog.shift();
    return { ok: last ? last.ok : false, result: last ? last.result : null, trace };
  }

  /* ---------- 同步版（仅本地内核，保留兼容） ---------- */
  call(service, op, args = []) {
    const k = this.kernels.get(service);
    if (!k) return { ok: false, error: '没有服务: ' + service };
    if (k.isRemote) {
      // 远端必须用 callAsync
      return { ok: false, error: '远端微内核请使用 callAsync' };
    }

    const trace = [];
    const queue = [{ service, op, args, depth: 0, from: null }];
    let last = null;
    let guard = 0;

    while (queue.length && guard++ < 64) {
      const job = queue.shift();
      const kern = this.kernels.get(job.service);
      if (!kern) continue;

      const r = kern.pulse(job.op, job.args, job.depth);
      trace.push({
        service: job.service,
        op: job.op,
        from: job.from,
        ok: r.ok,
        ms: r.totalMs === undefined ? null : r.totalMs,
        stateBytes: r.stateSize ? r.stateSize.raw : null,
        error: r.error,
        result: r.result === undefined ? null : r.result,
      });
      last = r;

      // 派生 → 入队（因果链）
      if (r.ok && r.spawned) {
        for (const e of r.spawned) {
          // ① 显式指定 __to 优先
          // ② 否则本服务有这个 op 就地触发
          // ③ 否则全局按 op 唯一匹配（这就是「因果自动路由」）
          const target = (e.payload && e.payload.__to) || this.resolveTarget(job.service, e.op);
          if (!target) continue;
          queue.push({
            service: target,
            op: e.op,
            args: [e.payload],
            depth: job.depth + 1,
            from: job.service + '.' + job.op,
          });
          kern.stats.emits++;
        }
      }
    }

    this.causalLog.push({ t: Date.now(), service, op, trace });
    if (this.causalLog.length > 100) this.causalLog.shift();

    return { ok: last ? last.ok : false, result: last ? last.result : null, trace };
  }

  list() {
    return [...this.kernels.values()].map(k => k.info());
  }

  systemInfo() {
    const ks = this.list();
    const totalState = ks.reduce((a, k) => a + k.stateBytes, 0);
    const totalPulses = ks.reduce((a, k) => a + k.pulses, 0);
    const up = Date.now() - this.bootAt;
    return {
      services: ks.length,
      totalPulses,
      totalStateBytes: totalState,
      causalEdges: this.causalLog.reduce((a, c) => a + Math.max(0, c.trace.length - 1), 0),
      uptimeMs: up,
      bootAt: this.bootAt,
    };
  }
}

module.exports = { MicroKernel, AggregatedShell };
