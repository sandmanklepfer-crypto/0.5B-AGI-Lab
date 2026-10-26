#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  dist.js —— 分布式聚合：把多台设备的微内核聚成一个系统
 *  --------------------------------------------------------------------------
 *  ★ 这是 B 的全部代码量。它之所以这么短，是因为 A 把微内核
 *    简化成了一个只有 3 个方法的接口（pulse / info / export）。
 *
 *  你想的：
 *      "无数微内核 + 外层大操作系统宏观控制"
 *
 *  实际做出来的：
 *      N 个节点各自持有 M 个微内核
 *      聚合层维护一张 (名字 → 位置) 表
 *      调用时按名字查表 → 路由到对应节点
 *
 *  于是：加一台设备 = 加一条记录，上层调用方式不变。
 * ========================================================================== */
const http = require('http');
const { AggregatedShell } = require('./kernel');
const { RemoteKernel } = require('./remote');

function getJson(host, port, path, timeout = 6000) {
  return new Promise((resolve) => {
    const req = http.request({ host, port, path, method: 'GET', timeout }, (res) => {
      const c = []; res.on('data', d => c.push(d));
      res.on('end', () => { try { resolve(JSON.parse(Buffer.concat(c).toString('utf8'))); } catch (e) { resolve(null); } });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
    req.end();
  });
}

class DistributedShell {
  constructor(opts = {}) {
    this.local = new AggregatedShell({ root: opts.root || './state' });
    this.nodes = new Map();       // nodeName -> {host, port, services:[], lastSeen}
    this.remote = new Map();      // serviceName -> RemoteKernel
  }

  /* 登记一个节点（不要求它在线，稍后 probe） */
  addNode(name, host, port) {
    this.nodes.set(name, { host, port, services: [], lastSeen: 0, online: false });
  }

  /* 探测所有节点，把它们的微内核挂进聚合层 */
  async probeAll() {
    const report = [];
    for (const [name, n] of this.nodes) {
      const d = await getJson(n.host, n.port, '/api/node');
      if (!d) {
        n.online = false;
        report.push({ node: name, online: false, services: [] });
        continue;
      }
      n.online = true;
      n.lastSeen = Date.now();
      n.services = (d.services || []).map(s => s.name);

      for (const s of (d.services || [])) {
        const key = name + ':' + s.name;
        const rk = new RemoteKernel({ name: s.name, host: n.host, port: n.port, label: name });
        rk.cacheInfo = s;
        this.remote.set(key, rk);
      }
      report.push({ node: name, online: true, services: n.services, stateBytes: (d.services || []).reduce((a, s) => a + (s.stateBytes || 0), 0) });
    }
    return report;
  }

  /* 找某个服务在哪（本地优先） */
  locate(service) {
    if (this.local.kernels.has(service)) return { where: 'local', kernel: this.local.kernels.get(service) };
    const hits = [];
    for (const [key, rk] of this.remote) if (rk.name === service) hits.push({ key, rk });
    if (hits.length === 1) return { where: 'remote', kernel: hits[0].rk, key: hits[0].key };
    if (hits.length > 1) return { where: 'ambiguous', candidates: hits.map(h => h.key) };
    return { where: 'none' };
  }

  /* 统一调用：本地或远端，上层调用者不关心 */
  async call(service, op, args = [], preferNode = null) {
    // 指定节点
    if (preferNode) {
      const rk = this.remote.get(preferNode + ':' + service);
      if (rk) {
        const r = await rk.pulse(op, args);
        return { ok: r.ok, result: r.result, trace: [{ service, op, from: null, ok: r.ok, ms: r.totalMs, remote: preferNode, error: r.error, result: r.result }] };
      }
    }
    const loc = this.locate(service);
    if (loc.where === 'local') return this.local.callAsync(service, op, args);
    if (loc.where === 'remote') {
      const r = await loc.kernel.pulse(op, args);
      return {
        ok: r.ok,
        result: r.result,
        trace: [{ service, op, from: null, ok: r.ok, ms: r.totalMs, stateBytes: null, remote: loc.kernel.label, error: r.error, result: r.result }],
      };
    }
    if (loc.where === 'ambiguous') return { ok: false, error: '服务 ' + service + ' 存在于多个节点: ' + loc.candidates.join(', ') + '（需指定节点）' };
    return { ok: false, error: '找不到服务 ' + service };
  }

  /* 全局总览：本地 + 所有远端 */
  overview() {
    const locals = this.local.list().map(k => ({ ...k, where: 'local' }));
    const remotes = [];
    for (const [key, rk] of this.remote) {
      const i = rk.info();
      remotes.push({ ...i, key, where: 'remote@' + rk.label });
    }
    const nodes = [...this.nodes.entries()].map(([n, x]) => ({
      node: n, host: x.host, port: x.port, online: x.online,
      services: x.services.length, lastSeen: x.lastSeen,
    }));
    return {
      nodes,
      services: locals.concat(remotes),
      counts: {
        nodes: nodes.length, online: nodes.filter(n => n.online).length,
        localKernels: locals.length, remoteKernels: remotes.length,
        total: locals.length + remotes.length,
      },
    };
  }
}

module.exports = { DistributedShell };

/* ---------------------------- CLI ---------------------------- */
if (require.main === module) {
  (async () => {
    const argv = process.argv.slice(2);
    const nodes = [];
    for (let i = 0; i < argv.length; i++) {
      if (argv[i] === '--node') { nodes.push(argv[++i]); }
    }
    const ds = new DistributedShell({ root: '/tmp/dist-local' });
    for (const spec of nodes) {
      const [name, hp] = spec.split('=');
      const [host, port] = hp.split(':');
      ds.addNode(name, host, parseInt(port, 10));
    }
    const rep = await ds.probeAll();
    console.log('═══════════════════════════════════════');
    console.log('  分布式聚合 · 探测结果');
    console.log('═══════════════════════════════════════');
    for (const r of rep) {
      console.log('  ' + (r.online ? '●' : '○') + ' ' + r.node.padEnd(10) +
        (r.online ? (r.services.length + ' 个微内核  ' + r.services.join(', ')) : '离线'));
    }
    const ov = ds.overview();
    console.log('');
    console.log('  合计: ' + ov.counts.nodes + ' 节点 (' + ov.counts.online + ' 在线)  ' +
      ov.counts.total + ' 个微内核');
    console.log('═══════════════════════════════════════');
  })();
}
