#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bench_wal.js —— WAL 对脉冲延迟的真实影响
 *  --------------------------------------------------------------------------
 *  这不是微基准，是端到端测量：
 *      完整走一遍 pulse()（激活 → 执行 → 落盘 → 挂起）
 *      分别配 4 种持久化策略，量 p50/p95/p99
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { WriteAheadLog } = require('./wal');
const ps = require('../lang/pulsescript');

const DIR = path.join(__dirname, '..', '_walbench');
const N = parseInt(process.env.N || '2000', 10);

const SRC = `
service counter {
  state { n: int = 0 items: list = [] }
  on "inc" {
    set n = n + 1
    return n
  }
  on "add"(x) {
    append(items, x)
    set n = n + 1
    if len(items) > 10 { set items = slice(items, len(items) - 10, len(items)) }
    return n
  }
}
`;

function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }
const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const f = (v) => (v < 1 ? (v * 1000).toFixed(0) + ' µs' : v.toFixed(2) + ' ms');

/* ------------------------------------------------------------------ */
/*  一次脉冲（把 WAL 挂进真实路径）                                     */
/* ------------------------------------------------------------------ */
function makeRun(mode, groupMs) {
  const dir = path.join(DIR, mode + (groupMs ? '-' + groupMs : ''));
  rmrf(dir);
  fs.mkdirSync(dir, { recursive: true });

  const { ast } = ps.compile(SRC);
  const svc = ast.services[0];
  let state = ps.makeState(svc);

  const wal = new WriteAheadLog({ dir, name: 'svc', mode, groupMs });
  const stateFile = path.join(dir, 'state.box');

  return {
    pulse(op, args) {
      const t0 = process.hrtime.bigint();

      /* ① 先写 WAL（预写：日志在状态之前） */
      wal.append({ op, args, stateHash: hash(state) });

      /* ② 执行 */
      const r = ps.runHandler(svc, op, args, state);
      if (!r.ok) return r;
      state = r.state;

      /* ③ 落盘状态箱 */
      const raw = Buffer.from(JSON.stringify(state), 'utf8');
      const packed = zlib.deflateRawSync(raw, { level: 9 });
      fs.writeFileSync(stateFile, packed);

      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      return { ok: true, result: r.result, ms, stateBytes: raw.length, walBytes: wal.bytes };
    },
    wal,
    get state() { return state; },
    close() { wal.close(); },
  };
}

function hash(s) {
  return require('crypto').createHash('sha1').update(JSON.stringify(s)).digest('hex').slice(0, 8);
}

/* ------------------------------------------------------------------ */
/*  跑一轮                                                             */
/* ------------------------------------------------------------------ */
function bench(mode, groupMs) {
  const R = makeRun(mode, groupMs);
  const lat = [];
  // 预热
  for (let i = 0; i < 50; i++) R.pulse('inc', []);
  lat.length = 0;

  for (let i = 0; i < N; i++) {
    const r = R.pulse(i % 3 === 0 ? 'add' : 'inc', [i]);
    if (r && r.ok) lat.push(r.ms);
  }
  const info = R.wal.info();
  const stateBytes = R.pulse('inc', []).stateBytes;
  R.close();

  return {
    mode: mode + (groupMs ? '(' + groupMs + 'ms)' : ''),
    p50: pct(lat, 0.5),
    p95: pct(lat, 0.95),
    p99: pct(lat, 0.99),
    avg: lat.reduce((a, b) => a + b, 0) / lat.length,
    max: Math.max(...lat),
    fsyncs: info.fsyncs,
    walBytes: info.bytes,
    stateBytes,
    n: lat.length,
  };
}

/* ------------------------------------------------------------------ */
console.log('='.repeat(88));
console.log('  WAL 对脉冲延迟的真实影响');
console.log('  ' + N + ' 次脉冲 / 策略，完整走 激活→WAL→执行→落盘→挂起');
console.log('='.repeat(88));
console.log('');
console.log('  策略'.padEnd(18) + 'p50'.padStart(10) + 'p95'.padStart(10) + 'p99'.padStart(10) +
  '平均'.padStart(10) + '最大'.padStart(10) + '  fsync次数');
console.log('-'.repeat(88));

const results = [];
const cases = [
  ['none', null, '纯内存，不落盘'],
  ['os', null, '写文件但不 fsync，靠 OS 页缓存'],
  ['fsync', null, '每次 writeSync + fsync'],
  ['group', 5, '攒 5ms 再 fsync'],
  ['group', 20, '攒 20ms 再 fsync'],
  ['group', 50, '攒 50ms 再 fsync'],
];

for (const [mode, g, desc] of cases) {
  const r = bench(mode, g);
  results.push(r);
  console.log('  ' + r.mode.padEnd(16) + f(r.p50).padStart(10) + f(r.p95).padStart(10) +
    f(r.p99).padStart(10) + f(r.avg).padStart(10) + f(r.max).padStart(10) +
    String(r.fsyncs).padStart(10));
}
console.log('-'.repeat(88));
console.log('');
for (const [mode, g, desc] of cases) console.log('  ' + (mode + (g ? '(' + g + 'ms)' : '')).padEnd(16) + desc);

/* 相对倍数 */
const base = results[0];
console.log('');
console.log('='.repeat(88));
console.log('  相对「纯内存」的倍数');
console.log('='.repeat(88));
console.log('  策略'.padEnd(18) + 'p50 倍数'.padStart(14) + 'p95 倍数'.padStart(14) + '  结论');
console.log('-'.repeat(88));
for (const r of results) {
  const x50 = r.p50 / base.p50;
  const x95 = r.p95 / base.p95;
  const verdict = x95 < 1.5 ? '✅ 几乎无感' : x95 < 3 ? '⚠️  可接受' : x95 < 8 ? '⚠️  明显变慢' : '❌ 脉冲优势消失';
  console.log('  ' + r.mode.padEnd(16) + (x50.toFixed(1) + 'x').padStart(14) +
    (x95.toFixed(1) + 'x').padStart(14) + '  ' + verdict);
}
console.log('='.repeat(88));

/* 数据安全边界 */
console.log('');
console.log('='.repeat(88));
console.log('  每种策略「断电会丢多少」');
console.log('='.repeat(88));
console.log('  策略'.padEnd(18) + '丢什么'.padStart(24) + '  适用场景');
console.log('-'.repeat(88));
const risk = [
  ['none', '全部（内存里的都没有）', '可重算的缓存、临时会话'],
  ['os', '最后 ≤5 秒（OS 刷盘间隔）', '能容忍重放的场景'],
  ['group(5ms)', '最后 ≤5ms 的操作', '大多数业务'],
  ['group(20ms)', '最后 ≤20ms 的操作', '吞吐优先'],
  ['group(50ms)', '最后 ≤50ms 的操作', '日志/统计类'],
  ['fsync', '不丢已确认的', '记账、订单'],
];
for (const [m, lose, use] of risk) console.log('  ' + m.padEnd(16) + lose.padStart(24) + '  ' + use);
console.log('='.repeat(88));

fs.writeFileSync(path.join(__dirname, '..', 'wal-bench.json'), JSON.stringify({ at: new Date().toISOString(), N, results: results.map(r => ({ ...r })) }, null, 2));
rmrf(DIR);
console.log('\n结果已存 wal-bench.json');
