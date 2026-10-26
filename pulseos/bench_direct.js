#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bench_direct.js —— 直连压测 vs HTTP 压测
 *  --------------------------------------------------------------------------
 *  同一个运行时，同 50 个微内核，同 500 次调用。
 *  唯一区别：一个走 HTTP，一个直接函数调用。
 *
 *  这个对比能回答：HTTP 到底吃掉了多少性能。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');
const pulse = require('./index');

const ROOT = '/tmp/directbench';
const PORT = 8988;
const N_K = parseInt(process.env.KERNELS || '50', 10);
const N_REQ = parseInt(process.env.REQ || '500', 10);

const fmt = (v) => (v < 1 ? (v * 1000).toFixed(0) + ' µs' : v.toFixed(3) + ' ms');
const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }

const src = (name) => `
service ${name} {
  state { n: int = 0 acc: int = 0 }
  on "inc"(x) { set n = n + 1 set acc = acc + x return n }
  on "get" { return { n: n, acc: acc } }
}
`;

/* ---------------------------- HTTP 版本 ---------------------------- */
function httpCall(method, p, body) {
  return new Promise((resolve) => {
    const d = body === undefined ? null : Buffer.from(JSON.stringify(body));
    const h = {};
    if (d) { h['Content-Type'] = 'application/json'; h['Content-Length'] = d.length; }
    const t0 = process.hrtime.bigint();
    const q = http.request({ host: '127.0.0.1', port: PORT, path: p, method, headers: h, timeout: 30000 }, (res) => {
      const c = [];
      res.on('data', x => c.push(x));
      res.on('end', () => {
        let j = null;
        try { j = JSON.parse(Buffer.concat(c).toString()); } catch (e) {}
        resolve({ ok: res.statusCode < 400, json: j, ms: Number(process.hrtime.bigint() - t0) / 1e6 });
      });
    });
    q.on('error', e => resolve({ ok: false, error: e.message, ms: Number(process.hrtime.bigint() - t0) / 1e6 }));
    q.on('timeout', () => q.destroy(new Error('timeout')));
    if (d) q.write(d);
    q.end();
  });
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* ---------------------------- 主流程 ---------------------------- */
(async () => {
  console.log('='.repeat(92));
  console.log('  直连（库调用） vs HTTP：同一运行时，同一负载');
  console.log('  ' + N_K + ' 个微内核，每个调用 ' + Math.ceil(N_REQ / N_K) + ' 次，共 ' + N_REQ + ' 次');
  console.log('='.repeat(92));

  /* ============ ① 直连 ============ */
  console.log('\n▸ ① 直连（require + invoke，零网络）');
  rmrf(ROOT);
  const rt = pulse.create({ root: ROOT });

  const tDeploy0 = Date.now();
  const names = [];
  for (let i = 0; i < N_K; i++) {
    const n = 'k' + String(i).padStart(3, '0');
    rt.deploy(src(n));
    names.push(n);
  }
  const deployMs = Date.now() - tDeploy0;
  console.log('  部署 ' + names.length + ' 个微内核: ' + deployMs + 'ms');

  /* 预热（不统计） */
  for (let i = 0; i < Math.min(200, N_REQ); i++) {
    rt.invoke(names[i % names.length], 'inc', [1]);
  }

  /* ★ 预热之后才建期望基线，否则交叉验证会差 200 次 */
  const expect = new Map();
  for (const n of names) {
    const g = rt.invoke(n, 'get', []);
    expect.set(n, g.result ? { n: g.result.n, acc: g.result.acc } : { n: 0, acc: 0 });
  }

  const latD = [];
  let okD = 0, failD = 0;
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < N_REQ; i++) {
    const name = names[i % names.length];
    const x = (i % 97) + 1;
    const r = rt.invoke(name, 'inc', [x]);
    latD.push(r.ms);                    // ★ 只收单次耗时
    if (r.ok) { okD++; const e = expect.get(name); e.n++; e.acc += x; }
    else failD++;
  }
  const wallD = Number(process.hrtime.bigint() - t0) / 1e6;

  console.log('  ✓ 完成 ' + okD + '/' + N_REQ + '   失败 ' + failD);
  console.log('  总耗时 ' + fmt(wallD) + '   QPS ' + (N_REQ / wallD * 1000).toFixed(0));
  console.log('  延迟  p50 ' + fmt(pct(latD, .5)) + '  p95 ' + fmt(pct(latD, .95)) +
    '  p99 ' + fmt(pct(latD, .99)) + '  max ' + fmt(Math.max(...latD)));

  /* 交叉验证 */
  let mismatch = 0;
  for (const n of names) {
    const r = rt.invoke(n, 'get', []);
    const got = r.result;
    const exp = expect.get(n);
    if (!got || got.n !== exp.n || got.acc !== exp.acc) mismatch++;
  }
  console.log('  交叉验证: ' + (mismatch === 0 ? '✓ 50 个内核全部一致' : '✗ ' + mismatch + ' 个不一致'));

  const sysD = rt.stat();
  console.log('  系统: ' + sysD.services + ' 服务, ' + sysD.totalStateBytes + ' B 状态, ' +
    sysD.totalPulses + ' 次脉冲');
  rt.close();

  /* ============ ② HTTP ============ */
  console.log('\n▸ ② HTTP（同一个运行时，套一层 server.js）');
  rmrf(ROOT);
  fs.mkdirSync(ROOT, { recursive: true });

  const srv = spawn(process.execPath, [path.join(__dirname, 'shell', 'server.js'), '--port', String(PORT)], {
    stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.assign({}, process.env, { PULSE_STATE_DIR: ROOT }),
  });
  let out = '';
  srv.stdout.on('data', d => out += d.toString());
  srv.stderr.on('data', d => out += d.toString().slice(0, 300));
  for (let i = 0; i < 120 && !/http:\/\/127/.test(out); i++) await sleep(100);
  await sleep(400);

  const tDep1 = Date.now();
  const hnames = [];
  for (let i = 0; i < N_K; i++) {
    const n = 'h' + String(i).padStart(3, '0');
    const r = await httpCall('POST', '/api/deploy', { src: src(n) });
    if (r.json && r.json.ok) hnames.push(n);
  }
  console.log('  部署 ' + hnames.length + ' 个微内核: ' + (Date.now() - tDep1) + 'ms');

  const latH = [];
  let okH = 0, failH = 0;
  const t1 = process.hrtime.bigint();
  for (let i = 0; i < N_REQ; i++) {
    const n = hnames[i % hnames.length];
    const r = await httpCall('POST', '/api/pulse', { service: n, op: 'inc', args: [(i % 97) + 1] });
    latH.push(r.ms);
    if (r.ok && r.json && r.json.ok) okH++; else failH++;
  }
  const wallH = Number(process.hrtime.bigint() - t1) / 1e6;

  console.log('  ✓ 完成 ' + okH + '/' + N_REQ + '   失败 ' + failH);
  console.log('  总耗时 ' + fmt(wallH) + '   QPS ' + (N_REQ / wallH * 1000).toFixed(0));
  console.log('  延迟  p50 ' + fmt(pct(latH, .5)) + '  p95 ' + fmt(pct(latH, .95)) +
    '  p99 ' + fmt(pct(latH, .99)) + '  max ' + fmt(Math.max(...latH)));

  srv.kill('SIGKILL');
  await sleep(300);

  /* ============ 对比 ============ */
  console.log('\n' + '='.repeat(92));
  console.log('  对比');
  console.log('='.repeat(92));
  console.log('  ' + '指标'.padEnd(16) + '直连(库)'.padStart(16) + 'HTTP'.padStart(16) + '  倍数');
  console.log('  ' + '-'.repeat(76));
  const row = (k, a, b, ratio) => {
    console.log('  ' + k.padEnd(14) + a.padStart(16) + b.padStart(16) + '  ' + ratio);
  };
  row('p50', fmt(pct(latD, .5)), fmt(pct(latH, .5)),
    (pct(latH, .5) / pct(latD, .5)).toFixed(0) + 'x 慢');
  row('p95', fmt(pct(latD, .95)), fmt(pct(latH, .95)),
    (pct(latH, .95) / pct(latD, .95)).toFixed(0) + 'x 慢');
  row('QPS', (N_REQ / wallD * 1000).toFixed(0), (N_REQ / wallH * 1000).toFixed(0),
    (wallH / wallD).toFixed(1) + 'x 快');
  row('部署 ' + N_K + ' 个', deployMs + ' ms', (Date.now() - tDep1) + ' ms', '');
  console.log('  ' + '-'.repeat(76));
  console.log('');
  console.log('  ★ 直连 p50 = ' + fmt(pct(latD, .5)) + '，这是 PulseOS 的真实能力');
  console.log('  ★ HTTP 那层吃掉了 ' + ((1 - wallD / wallH) * 100).toFixed(1) + '% 的时间');
  console.log('='.repeat(92));

  rmrf(ROOT);
})();
