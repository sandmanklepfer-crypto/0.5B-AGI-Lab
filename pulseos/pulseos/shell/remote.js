'use strict';
/* ==========================================================================
 *  remote.js —— 远端微内核适配器（带健康检查 + 重试 + 熔断）
 *  --------------------------------------------------------------------------
 *  B 的本质不是"搞一个通信协议"，而是：
 *
 *     本地微内核和远端微内核，在聚合层看来【没有区别】
 *
 *  但"没区别"的前提是：远端挂掉时，表现得像本地挂掉一样可预测。
 *  所以这个文件做四件事：
 *
 *    1. 健康检查    周期性 /api/node，维护 online 状态
 *    2. 重试        瞬时抖动（1 次）自动重试
 *    3. 熔断        连续失败到阈值就"打开"，短时间内直接拒绝，避免拖慢整个系统
 *    4. 半开恢复    熔断一段时间后放一个探针过去，成功就恢复
 * ========================================================================== */
const http = require('http');

const agent = new http.Agent({ keepAlive: true, maxSockets: 8 });

/* ---------------------------- HTTP ---------------------------- */
function reqJson(host, port, method, path, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const headers = {};
    if (data) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = data.length; }
    const req = http.request({ host, port, path, method, agent, headers, timeout: timeoutMs }, (res) => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const txt = Buffer.concat(chunks).toString('utf8');
        try { resolve(JSON.parse(txt)); }
        catch (e) { reject(new Error('响应不是 JSON（' + res.statusCode + '）')); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('超时 ' + timeoutMs + 'ms')); });
    if (data) req.write(data);
    req.end();
  });
}

/* ---------------------------- 熔断器 ---------------------------- */
/* closed  → 正常
   open    → 连续失败超过阈值，直接拒绝（不尝试连接）
   halfOpen→ 打开一段时间后，放一个探针 */
class Breaker {
  constructor(opts = {}) {
    this.threshold = opts.threshold || 3;       // 连续失败几次打开
    this.openMs = opts.openMs || 10000;         // 打开多久后试恢复
    this.state = 'closed';
    this.fails = 0;
    this.openedAt = 0;
    this.totalFails = 0;
    this.totalOk = 0;
  }

  canTry() {
    if (this.state === 'closed') return true;
    if (this.state === 'open') {
      if (Date.now() - this.openedAt >= this.openMs) { this.state = 'halfOpen'; return true; }
      return false;
    }
    return true;   // halfOpen：放一个过去
  }

  ok() {
    this.fails = 0;
    this.totalOk++;
    if (this.state !== 'closed') this.state = 'closed';
  }

  fail() {
    this.fails++;
    this.totalFails++;
    if (this.state === 'halfOpen') {
      this.state = 'open'; this.openedAt = Date.now();
    } else if (this.fails >= this.threshold) {
      this.state = 'open'; this.openedAt = Date.now();
    }
  }

  info() {
    return {
      state: this.state, fails: this.fails,
      openFor: this.state === 'open' ? Date.now() - this.openedAt : 0,
      totalOk: this.totalOk, totalFails: this.totalFails,
    };
  }
}

/* ==========================================================================
 *  RemoteKernel
 * ========================================================================== */
class RemoteKernel {
  constructor(opts) {
    this.name = opts.name;
    this.host = opts.host || '127.0.0.1';
    this.port = opts.port;
    this.nodeName = opts.label || (this.host + ':' + this.port);
    this.isRemote = true;

    this.timeout = opts.timeout || 8000;
    this.retry = opts.retry === undefined ? 1 : opts.retry;     // 瞬时失败重试次数

    this.breaker = new Breaker(opts.breaker);
    this.cacheInfo = null;
    this.stats = { pulses: 0, emits: 0, errors: 0, retries: 0, lat: [] };
  }

  get statePath() { return null; }
  get online() { return this.breaker.state !== 'open'; }

  /* ---------------- 核心：一次远端调用 ---------------- */
  async _call(op, args) {
    return reqJson(this.host, this.port, 'POST', '/api/pulse',
      { service: this.name, op, args }, this.timeout);
  }

  async pulse(op, args = [], depth = 0) {
    const t0 = Date.now();

    /* 熔断打开：直接拒绝，不浪费一次连接超时 */
    if (!this.breaker.canTry()) {
      this.stats.errors++;
      return {
        ok: false,
        error: '节点 ' + this.nodeName + ' 已熔断（连续失败，' +
          Math.round((Date.now() - this.breaker.openedAt) / 1000) + 's 前打开）',
        totalMs: 0, circuitOpen: true,
      };
    }

    let lastErr = null;
    for (let attempt = 0; attempt <= this.retry; attempt++) {
      if (attempt > 0) {
        this.stats.retries++;
        await new Promise(r => setTimeout(r, 120 * attempt));   // 退避
      }
      try {
        const r = await this._call(op, args);
        this.breaker.ok();

        const ms = Date.now() - t0;
        this.stats.pulses++;
        this.stats.lat.push(ms);
        if (this.stats.lat.length > 200) this.stats.lat.shift();

        if (!r.ok) { this.stats.errors++; return r; }

        const mine = (r.trace || []).find(t => t.service === this.name && t.op === op);
        return {
          ok: true, service: this.name, op,
          result: mine ? mine.result : (r.result === undefined ? null : r.result),
          emits: [], spawned: [],
          stateSize: mine && mine.stateBytes != null ? { raw: mine.stateBytes } : null,
          totalMs: ms,
          remote: this.nodeName,
          attempts: attempt + 1,
          remoteTrace: r.trace,
        };
      } catch (e) {
        lastErr = e;
      }
    }

    this.breaker.fail();
    this.stats.errors++;
    return {
      ok: false,
      error: '节点 ' + this.nodeName + ' 不可达: ' + (lastErr ? lastErr.message : '未知'),
      totalMs: Date.now() - t0,
      attempts: this.retry + 1,
    };
  }

  /* ---------------- 健康检查 ---------------- */
  async ping() {
    try {
      const d = await reqJson(this.host, this.port, 'GET', '/api/node', undefined, 4000);
      this.breaker.ok();
      return { online: true, services: d.services || [], node: d.node };
    } catch (e) {
      this.breaker.fail();
      return { online: false, error: e.message };
    }
  }

  /* ---------------- info（与 MicroKernel 同形状） ---------------- */
  info() {
    const lat = this.stats.lat.slice().sort((a, b) => a - b);
    const pct = (p) => (lat.length ? +lat[Math.min(lat.length - 1, Math.floor(lat.length * p))].toFixed(3) : null);
    const c = this.cacheInfo || {};
    return {
      name: this.name,
      remote: this.nodeName,
      isRemote: true,
      online: this.online,
      breaker: this.breaker.info(),
      breakerState: this.breaker.state,
      handlers: c.handlers || [],
      fields: c.fields || [],
      warnings: [],
      stateBytes: c.stateBytes == null ? 0 : c.stateBytes,
      state: c.state || '(远端)',
      pulses: this.stats.pulses,
      emits: this.stats.emits,
      errors: this.stats.errors,
      retries: this.stats.retries,
      lat: { p50: pct(0.5), p95: pct(0.95), n: lat.length },
    };
  }

  async sync() {
    try {
      const s = await reqJson(this.host, this.port, 'GET', '/api/state', undefined, 6000);
      const svc = (s.services || []).find(x => x.name === this.name);
      if (svc) this.cacheInfo = svc;
      this.breaker.ok();
      return svc || null;
    } catch (e) {
      this.breaker.fail();
      return null;
    }
  }
}

module.exports = { RemoteKernel, Breaker, reqJson };
