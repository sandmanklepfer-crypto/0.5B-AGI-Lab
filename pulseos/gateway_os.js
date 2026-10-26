#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  gateway_os.js —— 统一网关：所有调用都走 PulseOS
 *  --------------------------------------------------------------------------
 *  ★ 架构原则（用户提的）
 *
 *      HTTP    只传「标记/指针」，不传流量
 *      MQTT    只传「信令」，不传载荷
 *      PulseOS 是唯一执行层 —— 不管调用方是纯文本 AI、agent、还是本地脚本
 *
 *  ★ 冷/热分离（这是「OS 速度」的真正含义）
 *
 *      WARMUP  python 算一次 → 注入 PulseOS 状态箱   贵（几十 ms）
 *      HOT     之后所有读取全部走 PulseOS           便宜（亚微秒）
 *
 *    所以「快不快」不看 python 多快，看热路径有多快。
 *
 *  ★ 什么时候还要 python
 *     只有「PulseScript 表达不出来的运算」（SHA-256、大数阶乘）。
 *     而且只在 warmup 跑一次，结果进状态箱，之后不再调。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const pulse = require('./index');

const CHAN = process.env.PULSE_CHAN || 'live7k';
const STATE_DIR = process.env.PULSE_STATE || path.join(__dirname, '_state', 'provider');

const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const fmt = (v) => v < 0.001 ? (v * 1e6).toFixed(0) + ' ns' : v < 1 ? (v * 1000).toFixed(1) + ' µs' : v < 1000 ? v.toFixed(2) + ' ms' : (v / 1000).toFixed(2) + ' s';

/* ==========================================================================
 *  ① WARMUP —— python 算一次，注入 PulseOS
 *  ========================================================================== */
function warmup(rt) {
  const t0 = process.hrtime.bigint();

  const py = `
import hashlib, math, time, json
now = time.time()
ps = [i for i in range(2,2001) if all(i%d for d in range(2,int(i**0.5)+1))]
facts = [
  ("unix_ms",      str(int(now*1000)),                      "time"),
  ("unix_s",       str(int(now)),                           "time"),
  ("utc",          time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "time"),
  ("bj",           time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now+8*3600)), "time"),
  ("sha_hello",    hashlib.sha256(b"hello").hexdigest(),    "hash"),
  ("sha_pulseos",  hashlib.sha256(b"pulseos").hexdigest(),  "hash"),
  ("sha_2026",     hashlib.sha256(b"2026").hexdigest(),     "hash"),
  ("f50",          str(math.factorial(50)),                 "math"),
  ("f100_len",     str(len(str(math.factorial(100)))),      "math"),
  ("primes_2000",  str(len(ps)),                            "math"),
  ("prime_300th",  str(ps[299]),                            "math"),
  ("pi",           f"{math.pi:.15f}",                       "math"),
  ("e",            f"{math.e:.15f}",                        "math"),
  ("phi",          f"{(1+5**0.5)/2:.15f}",                  "math"),
  ("sqrt2",        f"{2**0.5:.15f}",                        "math"),
]
print(json.dumps(facts))
`;
  const pyT0 = process.hrtime.bigint();
  const facts = JSON.parse(execFileSync('python3', ['-c', py], { encoding: 'utf8', timeout: 60000 }));
  const pyMs = Number(process.hrtime.bigint() - pyT0) / 1e6;

  /* 注入 PulseOS —— 每次 put 都触发 index 的因果 */
  const inject = [];
  let causalCount = 0;
  for (const [k, v, kind] of facts) {
    const r = rt.invoke('provider', 'put', [k, v, kind]);
    if (r.causal) causalCount += r.causal.length;
    inject.push({ k, kind, ms: r.ms });
  }

  const totalMs = Number(process.hrtime.bigint() - t0) / 1e6;

  return {
    pyMs,
    injectMs: inject.reduce((a, x) => a + (x.ms || 0), 0),
    totalMs,
    facts: facts.length,
    causalCount,
    detail: inject,
  };
}

/* ==========================================================================
 *  ② HOT PATH —— 全部走 PulseOS，零 python
 *  ========================================================================== */
function hotBench(rt, rounds) {
  const keys = ['unix_ms', 'sha_hello', 'pi', 'primes_2000', 'bj', 'e', 'f100_len', 'phi'];

  /* 预热 */
  for (let i = 0; i < 200; i++) rt.invoke('provider', 'stat', []);

  const lat = [];
  for (let i = 0; i < rounds; i++) {
    const k = keys[i % keys.length];
    const r = rt.invoke('provider', 'get', [k]);
    lat.push(r.ms);
  }

  return {
    rounds,
    p50: pct(lat, 0.5),
    p95: pct(lat, 0.95),
    p99: pct(lat, 0.99),
    avg: lat.reduce((a, b) => a + b, 0) / lat.length,
    qps: rounds / (lat.reduce((a, b) => a + b, 0) / 1000),
  };
}

/* ==========================================================================
 *  ③ 对照：如果每次都调 python
 *  ========================================================================== */
function pythonBench(rounds) {
  const py = `import hashlib,math;print(hashlib.sha256(b"hello").hexdigest()[:8])`;
  const lat = [];
  for (let i = 0; i < rounds; i++) {
    const t0 = process.hrtime.bigint();
    try { execFileSync('python3', ['-c', py], { encoding: 'utf8', timeout: 10000 }); } catch (e) {}
    lat.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  return {
    rounds,
    p50: pct(lat, 0.5),
    p95: pct(lat, 0.95),
    avg: lat.reduce((a, b) => a + b, 0) / lat.length,
  };
}

/* ==========================================================================
 *  ④ 对照：纯 PulseScript 计算（不含状态写入）
 * ========================================================================== */
function pureBench(rt, rounds) {
  const lat = [];
  for (let i = 0; i < rounds; i++) {
    const t0 = process.hrtime.bigint();
    rt.invoke('provider', 'stat', []);
    lat.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  return {
    rounds,
    p50: pct(lat, 0.5),
    p95: pct(lat, 0.95),
    avg: lat.reduce((a, b) => a + b, 0) / lat.length,
  };
}

/* ==========================================================================
 *  主流程
 *  ========================================================================== */
function main() {
  let mode = 'full';
  const argv = process.argv.slice(2);
  if (argv.includes('--bench-only')) mode = 'bench';

  try { fs.rmSync(STATE_DIR, { recursive: true, force: true }); } catch (e) {}
  fs.mkdirSync(STATE_DIR, { recursive: true });

  const rt = pulse.create({ root: STATE_DIR, durability: 'batch', batchSize: 16, batchMs: 10 });
  const deployed = rt.deploy(fs.readFileSync(path.join(__dirname, 'services', 'provider.pulse'), 'utf8'));

  console.log('='.repeat(80));
  console.log('  PulseOS 统一网关 · 冷热分离实测');
  console.log('='.repeat(80));
  console.log('  部署微内核: ' + deployed.map(d => d.name).join(', '));
  console.log('  持久化: ' + rt.durability + ' (每 ' + rt.batchSize + ' 次或 ' + rt.batchMs + 'ms)');
  console.log('');

  /* ① Warmup */
  const w = warmup(rt);
  console.log('▸ WARMUP（python 算一次 → 注入 PulseOS）');
  console.log('  python 计算      ' + fmt(w.pyMs));
  console.log('  注入 ' + w.facts + ' 条事实   ' + fmt(w.injectMs));
  console.log('  触发因果          ' + w.causalCount + ' 次（provider → index）');
  console.log('  合计              ' + fmt(w.totalMs));
  console.log('');

  /* ② Pure PulseScript */
  const pure = pureBench(rt, 10000);
  console.log('▸ 纯 PulseScript（stat，只读内存状态）');
  console.log('  p50 ' + fmt(pure.p50) + '   p95 ' + fmt(pure.p95) + '   平均 ' + fmt(pure.avg));
  console.log('');

  /* ③ Hot path */
  const hot = hotBench(rt, 20000);
  console.log('▸ 热路径（get，走 PulseOS，零 python）  20,000 次');
  console.log('  p50 ' + fmt(hot.p50) + '   p95 ' + fmt(hot.p95) + '   p99 ' + fmt(hot.p99));
  console.log('  平均 ' + fmt(hot.avg) + '   QPS ' + Math.round(hot.qps).toLocaleString());
  console.log('');

  /* ④ Python 对照 */
  const pyb = pythonBench(10);
  console.log('▸ 对照：每次都调 python（10 次，慢）');
  console.log('  p50 ' + fmt(pyb.p50) + '   平均 ' + fmt(pyb.avg));
  console.log('');

  /* 汇总 */
  const sysInfo = rt.stat();

  console.log('='.repeat(80));
  console.log('  结论：谁的速度');
  console.log('='.repeat(80));
  console.log('  ' + '路径'.padEnd(28) + 'p50'.padStart(12) + '相对脉冲'.padStart(14));
  console.log('  ' + '-'.repeat(70));
  const rows = [
    ['纯 PulseScript 计算', pure.p50],
    ['PulseOS 热路径 get', hot.p50],
    ['WARMUP 注入一条', w.injectMs / w.facts],
    ['python 子进程一次', pyb.p50],
  ];
  for (const [name, v] of rows) {
    console.log('  ' + name.padEnd(26) + fmt(v).padStart(12) +
      (v <= pure.p50 * 1.5 ? '  1x（就是 OS 速度）' : '  ' + Math.round(v / pure.p50).toLocaleString() + 'x').padStart(14));
  }
  console.log('  ' + '-'.repeat(70));
  console.log('');
  console.log('  ★ 热路径 ' + fmt(hot.p50) + ' —— 这是 PulseOS 的真实速度');
  console.log('  ★ python 一次 ' + fmt(pyb.p50) + ' —— 这是进程创建 + 解释器启动的成本');
  console.log('  ★ 差 ' + Math.round(pyb.p50 / hot.p50).toLocaleString() + ' 倍');
  console.log('');
  console.log('  PulseOS 运行时:');
  console.log('    微内核        ' + sysInfo.services);
  console.log('    总脉冲        ' + sysInfo.totalPulses);
  console.log('    状态字节      ' + sysInfo.totalStateBytes + ' B');
  console.log('='.repeat(80));

  /* 导出给页面用 */
  const out = {
    generated_at: new Date().toISOString(),
    deployed,
    warmup: { pyMs: +w.pyMs.toFixed(3), injectMs: +w.injectMs.toFixed(3), totalMs: +w.totalMs.toFixed(3), facts: w.facts, causalCount: w.causalCount },
    pure: { p50: +pure.p50.toFixed(6), p95: +pure.p95.toFixed(6), rounds: pure.rounds },
    hot: { p50: +hot.p50.toFixed(6), p95: +hot.p95.toFixed(6), p99: +hot.p99.toFixed(6), avg: +hot.avg.toFixed(6), qps: Math.round(hot.qps), rounds: hot.rounds },
    python: { p50: +pyb.p50.toFixed(3), avg: +pyb.avg.toFixed(3), rounds: pyb.rounds },
    ratio: Math.round(pyb.p50 / hot.p50),
    sysInfo: { services: sysInfo.services, totalPulses: sysInfo.totalPulses, totalStateBytes: sysInfo.totalStateBytes },
    detail: w.detail,
  };
  fs.writeFileSync(path.join(__dirname, '_state', 'bench.json'), JSON.stringify(out, null, 2) + '\n');

  rt.close();
  console.log('\n  → _state/bench.json 已更新');
}

main();
