'use strict';
/* ==========================================================================
 *  remote.js —— 远端微内核适配器
 *  --------------------------------------------------------------------------
 *  B 的本质不是"搞一个通信协议"，而是：
 *
 *     本地微内核和远端微内核，在聚合层看来【没有区别】
 *
 *  因为它们对外只有三个动作：pulse / info / export。
 *  只要满足这三件事，它跑在本进程还是跑在另一台设备上，聚合层不关心。
 *
 *  ★ 这就是 A 做完之后 B 变成"自然结果"的原因：
 *    A 把微内核变成了一个【只有 3 个方法的接口】，
 *    于是"无穷多的微内核"不再受进程边界约束。
 * ========================================================================== */
const http = require('http');

const agent = new http.Agent({ keepAlive: true, maxSockets: 8 });

function post(host, port, path, body, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const data = Buffer.from(JSON.stringify(body));
    const req = http.request({
      host, port, path, method: 'POST', agent,
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length },
      timeout: timeoutMs,
    }, (res) => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch (e) { reject(new Error('响应不是 JSON')); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('远端超时 ' + timeoutMs + 'ms')); });
    req.write(data);
    req.end();
  });
}

function get(host, port, path, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host, port, path, method: 'GET', agent, timeout: timeoutMs }, (res) => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))); }
        catch (e) { reject(new Error('响应不是 JSON')); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('远端超时')); });
    req.end();
  });
}

/* ==========================================================================
 *  RemoteKernel —— 与 MicroKernel 同形状
 * ========================================================================== */
class RemoteKernel {
  constructor(opts) {
    this.name = opts.name;        // 远端服务名
    this.host = opts.host || '127.0.0.1';
    this.port = opts.port;
    this.label = opts.label || (this.host + ':' + this.port);
    this.isRemote = true;

    this.cacheInfo = null;
    this.stats = { pulses: 0, emits: 0, errors: 0, lat: [] };
  }

  get statePath() { return null; }

  /* 与 MicroKernel.pulse 同签名 */
  async pulse(op, args = [], depth = 0) {
    const t0 = Date.now();
    try {
      const r = await post(this.host, this.port, '/api/pulse', {
        service: this.name, op, args,
      });
      const ms = Date.now() - t0;
      this.stats.pulses++;
      this.stats.lat.push(ms);
      if (this.stats.lat.length > 200) this.stats.lat.shift();

      if (!r.ok) { this.stats.errors++; return r; }

      // 远端 trace 的最后一条就是本次结果
      const mine = (r.trace || []).find(t => t.service === this.name && t.op === op);
      const result = mine ? mine.result : (r.result === undefined ? null : r.result);

      return {
        ok: true, service: this.name, op,
        result,
        emits: [],
        spawned: [],          // 远端的派生由远端自己处理
        stateSize: mine && mine.stateBytes != null ? { raw: mine.stateBytes } : null,
        totalMs: ms,
        remote: this.label,
        remoteTrace: r.trace,
      };
    } catch (e) {
      this.stats.errors++;
      return { ok: false, error: '远端不可达(' + this.label + '): ' + e.message, totalMs: Date.now() - t0 };
    }
  }

  /* 与 MicroKernel.info 同形状 */
  info() {
    const lat = this.stats.lat.slice().sort((a, b) => a - b);
    const pct = (p) => (lat.length ? +lat[Math.min(lat.length - 1, Math.floor(lat.length * p))].toFixed(3) : null);
    const c = this.cacheInfo || {};
    return {
      name: this.name,
      remote: this.label,
      isRemote: true,
      handlers: c.handlers || [],
      fields: c.fields || [],
      warnings: [],
      stateBytes: c.stateBytes == null ? 0 : c.stateBytes,
      state: c.state || '(远端)',
      pulses: this.stats.pulses,
      emits: this.stats.emits,
      errors: this.stats.errors,
      lat: { p50: pct(0.5), p95: pct(0.95), n: lat.length },
    };
  }

  /* 拉取远端信息，填充 handlers */
  async sync() {
    try {
      const s = await get(this.host, this.port, '/api/state');
      const svc = (s.services || []).find(x => x.name === this.name);
      if (svc) this.cacheInfo = svc;
      return svc || null;
    } catch (e) {
      return null;
    }
  }
}

module.exports = { RemoteKernel };
