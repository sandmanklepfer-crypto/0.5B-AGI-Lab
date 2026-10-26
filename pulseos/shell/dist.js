#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  dist.js —— 分布式聚合（带故障转移 + 自动健康检查）
 *  --------------------------------------------------------------------------
 *  第一版做完之后最痛的问题：节点一挂，调用就失败。
 *  这一版补上三件事：
 *
 *    1. 自动健康检查   每 N 秒 ping 所有节点，离线/上线自动维护
 *    2. 故障转移       同名服务在多个节点上时，主节点挂了自动切备用
 *    3. 可观测         每次调用都告诉你：走了哪个节点、重试了几次、是否降级
 * ========================================================================== */
const { AggregatedShell } = require('./kernel');
const { RemoteKernel, reqJson } = require('./remote');

class DistributedShell {
  constructor(opts = {}) {
    this.local = new AggregatedShell({ root: opts.root || './state' });
    this.nodes = new Map();       // nodeName -> {host, port, services, online, lastSeen, ...}
    this.remote = new Map();      // "node:service" -> RemoteKernel
    this.prefer = new Map();      // service -> 优先节点（可手动设）
    this.healthTimer = null;
    this.healthMs = opts.healthMs || 15000;
    this.stats = { calls: 0, ok: 0, failover: 0, failed: 0 };
  }

  /* ---------------- 节点管理 ---------------- */
  addNode(name, host, port, opts = {}) {
    this.nodes.set(name, {
      name, host, port,
      services: [], online: false, lastSeen: 0,
      failCount: 0, okCount: 0,
      priority: opts.priority || 0,      // 数字越小越优先
    });
  }

  removeNode(name) {
    this.nodes.delete(name);
    for (const [k, rk] of this.remote) if (rk.nodeName === name) this.remote.delete(k);
  }

  /* 指定某服务优先走某节点 */
  setPrefer(service, nodeName) { this.prefer.set(service, nodeName); }

  /* ---------------- 探测 / 健康检查 ---------------- */
  async probeAll() {
    const report = [];
    for (const [name, n] of this.nodes) {
      const t0 = Date.now();
      let d = null;
      try {
        d = await reqJson(n.host, n.port, 'GET', '/api/node', undefined, 4000);
      } catch (e) { d = null; }

      if (!d) {
        n.online = false;
        n.failCount++;
        // ★ 节点离线：给它名下所有远端微内核各记一次失败，让它能熔断
        let affected = 0;
        for (const [k, rk] of this.remote) {
          if (rk.nodeName === name && rk.breaker.state !== 'open') { rk.breaker.fail(); affected++; }
        }
        report.push({ node: name, online: false, services: [], ms: Date.now() - t0, breakerFails: affected });
        continue;
      }

      n.online = true;
      n.lastSeen = Date.now();
      n.okCount++;
      n.failCount = 0;
      n.services = (d.services || []).map(s => s.name);

      // 同步远端微内核表
      for (const s of (d.services || [])) {
        const key = name + ':' + s.name;
        let rk = this.remote.get(key);
        if (!rk) {
          rk = new RemoteKernel({ name: s.name, host: n.host, port: n.port, label: name });
          this.remote.set(key, rk);
        }
        rk.cacheInfo = s;
        rk.breaker.ok();
      }
      report.push({
        node: name, online: true, services: n.services,
        stateBytes: (d.services || []).reduce((a, s) => a + (s.stateBytes || 0), 0),
        ms: Date.now() - t0,
      });
    }
    return report;
  }

  /* 后台自动健康检查 */
  startHealthLoop() {
    if (this.healthTimer) return;
    const tick = async () => {
      try { await this.probeAll(); } catch (e) {}
    };
    tick();
    this.healthTimer = setInterval(tick, this.healthMs);
    if (this.healthTimer.unref) this.healthTimer.unref();
    return this;
  }

  stopHealthLoop() {
    if (this.healthTimer) { clearInterval(this.healthTimer); this.healthTimer = null; }
  }

  /* ---------------- 定位：返回候选列表（按优先级 + 健康度排序） ---------------- */
  candidates(service) {
    const list = [];

    // 本地
    if (this.local.kernels.has(service)) {
      list.push({ where: 'local', node: '(local)', kernel: this.local.kernels.get(service), priority: -100 });
    }

    // 远端
    for (const [key, rk] of this.remote) {
      if (rk.name !== service) continue;
      const n = this.nodes.get(rk.nodeName);
      const healthy = rk.online && (!n || n.online);
      list.push({
        where: 'remote', node: rk.nodeName, kernel: rk,
        priority: (n ? n.priority : 0) + (healthy ? 0 : 1000),
        healthy,
      });
    }

    // 手动指定优先
    const p = this.prefer.get(service);
    if (p) {
      list.sort((a, b) => (a.node === p ? -1 : b.node === p ? 1 : 0));
      return list;
    }

    list.sort((a, b) => a.priority - b.priority);
    return list;
  }

  /* ---------------- 调用：带故障转移 ---------------- */
  async call(service, op, args = [], opts = {}) {
    this.stats.calls++;
    const cands = this.candidates(service);

    if (!cands.length) {
      this.stats.failed++;
      return { ok: false, error: '找不到服务 ' + service, trace: [] };
    }

    // 指定节点
    if (opts.node) {
      const hit = cands.find(c => c.node === opts.node);
      if (!hit) {
        this.stats.failed++;
        return { ok: false, error: '服务 ' + service + ' 不在节点 ' + opts.node, trace: [] };
      }
      return this._invoke(service, op, args, [hit], true);
    }

    return this._invoke(service, op, args, cands, opts.noFailover === true);
  }

  async _invoke(service, op, args, cands, single) {
    const trace = [];
    const tried = [];

    for (let i = 0; i < cands.length; i++) {
      const c = cands[i];
      tried.push(c.node);

      let r;
      if (c.where === 'local') {
        // 本地：走 AggregatedShell，含因果链
        const res = await this.local.callAsync(service, op, args);
        r = {
          ok: res.ok,
          result: res.result,
          totalMs: res.trace.reduce((a, t) => a + (t.ms || 0), 0),
          trace: res.trace,
        };
      } else {
        r = await c.kernel.pulse(op, args);
      }

      trace.push({
        service, op, from: null,
        ok: r.ok,
        ms: r.totalMs,
        remote: c.node === '(local)' ? null : c.node,
        node: c.node,
        attempt: i + 1,
        error: r.error || null,
        result: r.result === undefined ? null : r.result,
        circuitOpen: r.circuitOpen || false,
      });

      if (r.ok) {
        this.stats.ok++;
        if (i > 0) this.stats.failover++;
        if (c.where === 'remote') {
          const n = this.nodes.get(c.node);
          if (n) { n.online = true; n.lastSeen = Date.now(); n.failCount = 0; }
        }
        return {
          ok: true,
          result: r.result,
          node: c.node,
          failover: i > 0,
          triedNodes: tried,
          trace: r.trace && r.trace.length > 1 ? r.trace : trace,
        };
      }

      // ★ 调用失败时同步节点表，让 overview 反映真实状态
      if (c.where === 'remote') {
        const n = this.nodes.get(c.node);
        if (n) { n.failCount++; n.online = false; }
      }

      if (single) break;
      // 熔断打开的直接跳过，不浪费时间
      if (r.circuitOpen) continue;
    }

    this.stats.failed++;
    return {
      ok: false,
      error: '所有节点都失败: ' + trace.map(t => t.node + '(' + (t.error || '?') + ')').join(' → '),
      triedNodes: tried,
      trace,
    };
  }

  /* ---------------- 全局总览 ---------------- */
  overview() {
    const locals = this.local.list().map(k => ({ ...k, where: 'local', node: '(local)' }));

    // 同名远端服务按节点聚合，显示谁在线
    const byService = new Map();
    for (const [key, rk] of this.remote) {
      const i = rk.info();
      if (!byService.has(rk.name)) byService.set(rk.name, []);
      byService.get(rk.name).push(i);
    }

    const remotes = [];
    for (const [svc, list] of byService) {
      const primary = list[0];
      remotes.push({
        ...primary,
        replicas: list.map(x => ({
          node: x.remote,
          online: x.online,                 // 来自 breaker
          state: x.breakerState || '?',
          stateBytes: x.stateBytes,
        })),
        replicaCount: list.length,
        onlineCount: list.filter(x => x.online).length,
        breakerStates: list.map(x => x.remote + ':' + (x.breakerState || '?')),
        where: 'remote',
      });
    }

    const nodes = [...this.nodes.values()].map(n => ({
      node: n.name, host: n.host, port: n.port, online: n.online,
      services: n.services, lastSeen: n.lastSeen, priority: n.priority,
      okCount: n.okCount, failCount: n.failCount,
    }));

    return {
      nodes,
      services: locals.concat(remotes),
      stats: { ...this.stats },
      counts: {
        nodes: nodes.length,
        online: nodes.filter(n => n.online).length,
        localKernels: locals.length,
        remoteServices: remotes.length,
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
    let healthMs = 0;
    for (let i = 0; i < argv.length; i++) {
      if (argv[i] === '--node') nodes.push(argv[++i]);
      else if (argv[i] === '--watch') healthMs = parseInt(argv[++i] || '5', 10) * 1000;
    }
    const ds = new DistributedShell({ root: '/tmp/dist-cli' });
    for (const spec of nodes) {
      const [name, hp] = spec.split('=');
      const [host, port] = hp.split(':');
      ds.addNode(name, host, parseInt(port, 10));
    }

    const show = async () => {
      const rep = await ds.probeAll();
      const ov = ds.overview();
      const now = new Date().toTimeString().slice(0, 8);
      console.log('\n[' + now + '] ═══════════════════════════════');
      for (const n of ov.nodes) {
        console.log('  ' + (n.online ? '●' : '○') + ' ' + n.node.padEnd(10) +
          ' ' + String(n.services.length).padStart(2) + ' 个微内核  ' +
          (n.online ? n.services.join(', ') : '离线'));
      }
      console.log('  ─────────────────────────────────');
      console.log('  节点 ' + ov.counts.online + '/' + ov.counts.nodes + ' 在线   ' +
        '微内核 ' + ov.counts.total + '   ' +
        '调用 ' + ov.stats.calls + ' (成功 ' + ov.stats.ok + ', 故障转移 ' + ov.stats.failover + ', 失败 ' + ov.stats.failed + ')');
    };

    await show();
    if (healthMs) {
      console.log('\n监控中（Ctrl-C 退出）…');
      ds.healthMs = healthMs;
      ds.startHealthLoop();
      setInterval(show, healthMs * 3);
    }
  })();
}
