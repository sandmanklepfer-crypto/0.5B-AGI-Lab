#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bench_concurrent.js —— 并发压测 + 交叉验证
 *  --------------------------------------------------------------------------
 *  ★ 先诚实说明这个测试能证明什么、不能证明什么
 *
 *    Node 是单线程，server.js 里的 pulse() 是同步的。
 *    50 个 HTTP 请求「同时到达」时，事件循环会【串行】处理。
 *
 *    所以本测试证明的是：
 *      ✓ 50 个微内核的状态完全隔离（互不污染）
 *      ✓ 吞吐量（QPS）和延迟分布
 *      ✓ 每个微内核的数据在并发写后仍然正确（交叉验证）
 *      ✓ 崩溃后 50 个微内核全部能恢复
 *
 *    本测试【不】证明：
 *      ✗ 真正的并行执行（需要 worker_threads 或 cluster）
 *      ✗ 多核利用
 *
 *  想测真并行，看 bench_parallel.js（用 worker_threads）。
 * ========================================================================== */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const DIR = '/tmp/concbench';
const PORT = 8977;
const N_KERNELS = parseInt(process.env.KERNELS || '50', 10);
const N_REQ = parseInt(process.env.REQ || '500', 10);
const CONC = parseInt(process.env.CONC || '50', 10);

const SRV = path.join(__dirname, 'server.js');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }

/* ---------------------------- HTTP ---------------------------- */
function call(method, p, body, timeout = 30000) {
  return new Promise((resolve) => {
    const data = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const h = {};
    if (data) { h['Content-Type'] = 'application/json'; h['Content-Length'] = data.length; }
    const t0 = process.hrtime.bigint();
    const req = http.request({ host: '127.0.0.1', port: PORT, path: p, method, headers: h, timeout }, (res) => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const ms = Number(process.hrtime.bigint() - t0) / 1e6;
        let json = null;
        try { json = JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch (e) {}
        resolve({ ok: res.statusCode < 400, status: res.statusCode, json, ms });
      });
    });
    req.on('error', (e) => resolve({ ok: false, error: e.message, ms: Number(process.hrtime.bigint() - t0) / 1e6 }));
    req.on('timeout', () => { req.destroy(new Error('timeout')); });
    if (data) req.write(data);
    req.end();
  });
}
const post = (p, b) => call('POST', p, b);
const get = (p) => call('GET', p);

const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const f = (v) => (v < 1 ? (v * 1000).toFixed(0) + ' µs' : v.toFixed(2) + ' ms');

/* ---------------------------- 服务定义 ---------------------------- */
/* 每个压测服务：一个计数器 + 一个累加器，都是可交叉验证的 */
function makeSrc(name) {
  return `
service ${name} {
  state {
    n: int = 0
    sum: int = 0
    log: list = []
  }
  on "inc"(x) {
    set n = n + 1
    set sum = sum + x
    append(log, x)
    if len(log) > 5 { set log = slice(log, len(log) - 5, len(log)) }
    return { n: n, sum: sum }
  }
  on "get" {
    return { n: n, sum: sum }
  }
}
`;
}

/* ---------------------------- 主流程 ---------------------------- */
(async () => {
  console.log('='.repeat(90));
  console.log('  并发压测 + 交叉验证');
  console.log('  ' + N_KERNELS + ' 个微内核  ' + N_REQ + ' 个请求  并发度 ' + CONC);
  console.log('='.repeat(90));
  console.log('');
  console.log('  ⚠️  诚实前提：Node 单线程，pulse() 同步。');
  console.log('      "并发"= 50 个连接同时在途，但服务端串行执行。');
  console.log('      测的是状态隔离 / 吞吐 / 延迟，不是多核并行。');
  console.log('');

  rmrf(DIR);
  fs.mkdirSync(DIR, { recursive: true });

  /* 启动服务 */
  const srv = spawn(process.execPath, [SRV, '--port', String(PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.assign({}, process.env, { PULSE_STATE_DIR: DIR }),
  });
  let srvOut = '';
  srv.stdout.on('data', d => srvOut += d.toString());
  srv.stderr.on('data', d => srvOut += d.toString().slice(0, 500));

  for (let i = 0; i < 100 && !/http:\/\/127/.test(srvOut); i++) await sleep(100);
  if (!/http:\/\/127/.test(srvOut)) {
    console.log('  ✗ 服务没起来:\n' + srvOut);
    srv.kill(); process.exit(1);
  }
  await sleep(300);

  /* ① 部署 50 个微内核 */
  console.log('▸ ① 部署 ' + N_KERNELS + ' 个微内核');
  const tDeploy = Date.now();
  const deployed = [];
  for (let i = 0; i < N_KERNELS; i++) {
    const name = 'k' + String(i).padStart(3, '0');
    const r = await post('/api/deploy', { src: makeSrc(name) });
    if (r.ok && r.json && r.json.ok) deployed.push(name);
    else console.log('    ✗ ' + name + ': ' + (r.json && r.json.error));
  }
  console.log('  ✓ 部署 ' + deployed.length + '/' + N_KERNELS + '  耗时 ' + (Date.now() - tDeploy) + 'ms');

  const st0 = await get('/api/state');
  console.log('  系统状态: ' + st0.json.services.length + ' 个服务, ' +
    st0.json.system.totalStateBytes + ' B 状态合计');

  /* ② 并发压测 */
  console.log('\n▸ ② 并发压测：' + N_REQ + ' 个请求，并发度 ' + CONC);
  /* 每个服务的期望值，用于交叉验证 */
  const expect = new Map();
  for (const n of deployed) expect.set(n, { n: 0, sum: 0 });

  const lat = [];
  let ok = 0, fail = 0;
  const errs = new Map();
  const t0 = Date.now();

  /* 用 Promise 池控制并发度 */
  let idx = 0;
  async function worker() {
    while (true) {
      const my = idx++;
      if (my >= N_REQ) return;

      const name = deployed[my % deployed.length];
      const x = (my % 97) + 1;

      const r = await post('/api/pulse', { service: name, op: 'inc', args: [x] });
      lat.push(r.ms);

      const good = r.ok && r.json && r.json.ok;
      if (good) {
        ok++;
        const e = expect.get(name);
        e.n++; e.sum += x;
      } else {
        fail++;
        const k = (r.json && r.json.error) || r.error || ('HTTP ' + r.status);
        errs.set(k, (errs.get(k) || 0) + 1);
      }
    }
  }
  await Promise.all(Array.from({ length: CONC }, () => worker()));

  const wall = Date.now() - t0;
  console.log('  ✓ 完成 ' + ok + '/' + N_REQ + '   失败 ' + fail);
  console.log('  墙钟 ' + wall + 'ms   QPS ' + (N_REQ / wall * 1000).toFixed(0));
  console.log('  延迟  p50 ' + f(pct(lat, .5)) + '  p95 ' + f(pct(lat, .95)) +
    '  p99 ' + f(pct(lat, .99)) + '  max ' + f(Math.max(...lat)));

  if (errs.size) {
    console.log('  错误分布:');
    for (const [k, v] of errs) console.log('    ' + k + '  x' + v);
  }

  /* ③ 交叉验证 */
  console.log('\n▸ ③ 交叉验证：逐个核对每个微内核的 n 和 sum');
  let mismatch = 0, checked = 0;
  const bad = [];
  for (const name of deployed) {
    const r = await post('/api/pulse', { service: name, op: 'get', args: [] });
    const got = r.json && r.json.trace && r.json.trace[0] && r.json.trace[0].result;
    const exp = expect.get(name);
    checked++;
    if (!got || got.n !== exp.n || got.sum !== exp.sum) {
      mismatch++;
      if (bad.length < 5) bad.push({ name, exp, got });
    }
  }
  console.log('  核对 ' + checked + ' 个微内核，不一致 ' + mismatch);
  if (bad.length) {
    for (const b of bad) console.log('    ✗ ' + b.name + '  期望 ' + JSON.stringify(b.exp) + '  实际 ' + JSON.stringify(b.got));
  } else {
    console.log('  ✓ 全部一致（无交叉污染）');
  }

  /* 全局汇总：所有服务的 sum 应等于所有请求之和 */
  const st1 = await get('/api/state');
  const totalPulses = st1.json.system.totalPulses;
  let sumAll = 0;
  for (const n of deployed) {
    const r = await post('/api/pulse', { service: n, op: 'get', args: [] });
    const got = r.json.trace[0].result;
    sumAll += got.sum;
  }
  let expectSum = 0;
  for (const e of expect.values()) expectSum += e.sum;
  console.log('  全局 sum: 实际 ' + sumAll + '  期望 ' + expectSum + '  ' +
    (sumAll === expectSum ? '✓' : '✗'));
  console.log('  总脉冲次数: ' + totalPulses);

  /* ④ 持久化验证：杀掉重启，看 50 个微内核是否都恢复 */
  console.log('\n▸ ④ 持久化：kill -9 服务进程，重启后核对');
  srv.kill('SIGKILL');
  await sleep(500);

  const srv2 = spawn(process.execPath, [SRV, '--port', String(PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.assign({}, process.env, { PULSE_STATE_DIR: DIR }),
  });
  let out2 = '';
  srv2.stdout.on('data', d => out2 += d.toString());
  for (let i = 0; i < 100 && !/http:\/\/127/.test(out2); i++) await sleep(100);

  const st2 = await get('/api/state');
  let restoredOk = 0, restoredBad = 0;
  for (const name of deployed) {
    const r = await post('/api/pulse', { service: name, op: 'get', args: [] });
    const got = r.json && r.json.trace && r.json.trace[0] && r.json.trace[0].result;
    const exp = expect.get(name);
    if (got && got.n === exp.n && got.sum === exp.sum) restoredOk++;
    else restoredBad++;
  }
  console.log('  重启后服务数: ' + (st2.json ? st2.json.services.length : 0));
  console.log('  状态完全恢复: ' + restoredOk + '/' + deployed.length +
    '   不一致: ' + restoredBad + '  ' + (restoredBad === 0 ? '✓' : '✗'));

  srv2.kill('SIGKILL');
  await sleep(200);

  /* ---------------- 总结 ---------------- */
  console.log('\n' + '='.repeat(90));
  console.log('  总结');
  console.log('='.repeat(90));
  const pass = (fail === 0) && (mismatch === 0) && (restoredBad === 0) && (sumAll === expectSum);
  console.log('  ' + N_KERNELS + ' 微内核部署          ' + (deployed.length === N_KERNELS ? '✓' : '✗ ' + deployed.length));
  console.log('  ' + N_REQ + ' 请求全部成功        ' + (fail === 0 ? '✓' : '✗ 失败 ' + fail));
  console.log('  状态隔离（无污染）   ' + (mismatch === 0 ? '✓' : '✗ ' + mismatch + ' 个不一致'));
  console.log('  全局数据校验        ' + (sumAll === expectSum ? '✓' : '✗'));
  console.log('  崩溃后完全恢复      ' + (restoredBad === 0 ? '✓' : '✗'));
  console.log('  ' + '-'.repeat(60));
  console.log('  ' + (pass ? '✅ 全部通过' : '❌ 有失败'));
  console.log('');
  console.log('  能证明：状态隔离 / 吞吐 / 延迟 / 崩溃恢复');
  console.log('  不能证明：多核并行（Node 单线程，需 worker_threads）');
  console.log('='.repeat(90));

  rmrf(DIR);
})();
