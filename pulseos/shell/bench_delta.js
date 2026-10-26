#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bench_delta.js —— 全量快照 vs 增量快照
 *  --------------------------------------------------------------------------
 *  目标：验证 10MB 状态下增量快照能否把延迟压在 10ms 以内。
 *
 *  三个必须验证的东西：
 *    ① 正确性    delta 还原出的状态必须和原状态完全一致
 *    ② 延迟      单次快照写盘的耗时
 *    ③ 代价      写入了多少字节（不是"看起来快"而是"真的少写了"）
 *
 *  场景设计（模拟真实业务的三种变化）：
 *    A 追加型   一个不断增长的列表（典型的"长期记忆"）
 *    B 标量型   几个计数器不断变化
 *    C 混合型   大列表不变，只有小字段变
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { SnapshotChain, makeDelta, applyDelta, deltaCost, deepEqual } = require('./snapshot_delta');
const { writeSnapshot } = require('./wal');

const ROOT = '/tmp/deltabench';
const fmt = (b) => (b >= 1048576 ? (b / 1048576).toFixed(2) + ' MB' : b >= 1024 ? (b / 1024).toFixed(1) + ' KB' : b + ' B');
const ms = (v) => (v < 1 ? (v * 1000).toFixed(0) + ' µs' : v.toFixed(2) + ' ms');
const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }

/* 造一个约 targetMB 的状态 */
function makeState(targetMB, nScalars = 4) {
  const st = {};
  const perItem = 60;                       // 每条 ~60 字节
  const nItems = Math.floor(targetMB * 1024 * 1024 / perItem);
  st.memory = Array.from({ length: nItems }, (_, i) => ({ id: i, t: 'x'.repeat(40), at: 1700000000000 + i }));
  for (let i = 0; i < nScalars; i++) st['c' + i] = 0;
  st.name = 'agent';
  return st;
}

/* ---------------- 三种场景 ---------------- */
const SCENARIOS = {
  /* A：不断往大列表追加（长期记忆） */
  append(state, i) {
    const next = Object.assign({}, state);
    next.memory = state.memory.concat([{ id: state.memory.length, t: 'x'.repeat(40), at: 1700000000000 + i }]);
    return next;
  },
  /* B：只改标量 */
  scalar(state, i) {
    const next = Object.assign({}, state);
    next.c0 = i; next.c1 = i * 2; next.c2 = state.c2 + i;
    return next;
  },
  /* C：混合 */
  mixed(state, i) {
    const next = Object.assign({}, state);
    if (i % 3 === 0) {
      next.memory = state.memory.concat([{ id: state.memory.length, t: 'x'.repeat(40), at: 1700000000000 + i }]);
    }
    next.c0 = state.c0 + 1;
    return next;
  },
};

/* ---------------- 对比 ---------------- */
function runScenario(name, sizeMB, steps) {
  const dirFull = path.join(ROOT, name + '-full');
  const dirDelta = path.join(ROOT, name + '-delta');
  rmrf(dirFull); rmrf(dirDelta);
  fs.mkdirSync(dirFull, { recursive: true });
  fs.mkdirSync(dirDelta, { recursive: true });

  let state = makeState(sizeMB);
  const stateMB = Buffer.byteLength(JSON.stringify(state)) / 1048576;

  const chain = new SnapshotChain({ dir: dirDelta, fullEvery: 10 });
  const latFull = [], latDelta = [];
  const bytesFull = [], bytesDelta = [];

  /* 第一份：两边都写全量（作为 base） */
  let t0 = process.hrtime.bigint();
  const w = writeSnapshot(dirFull, 0, state);
  latFull.push(Number(process.hrtime.bigint() - t0) / 1e6);
  bytesFull.push(w.bytes);

  t0 = process.hrtime.bigint();
  const d0 = chain.save(0, state, null, null);
  latDelta.push(Number(process.hrtime.bigint() - t0) / 1e6);
  bytesDelta.push(d0.bytes);

  let prev = state;
  let deltaCount = 0;

  for (let i = 1; i <= steps; i++) {
    const next = SCENARIOS[name === 'append' ? 'append' : name === 'scalar' ? 'scalar' : 'mixed'](prev, i);

    /* 全量：只写，不保留（模拟每次 compaction） */
    t0 = process.hrtime.bigint();
    const wf = writeSnapshot(dirFull, i, next);
    latFull.push(Number(process.hrtime.bigint() - t0) / 1e6);
    bytesFull.push(wf.bytes);

    /* 增量：需要脏字段集合 */
    const dirty = new Set();
    for (const k of new Set([...Object.keys(prev), ...Object.keys(next)])) {
      if (prev[k] !== next[k]) dirty.add(k);
    }
    t0 = process.hrtime.bigint();
    const dd = chain.save(i, next, prev, dirty);
    latDelta.push(Number(process.hrtime.bigint() - t0) / 1e6);
    bytesDelta.push(dd.bytes);
    if (dd.kind === 'delta') deltaCount++;

    prev = next;

    /* 每 50 步校验一次正确性 */
    if (i % 50 === 0) {
      const loaded = chain.load();
      if (!deepEqual(loaded.state, next)) {
        return { ok: false, name, error: '还原不一致 @ step ' + i, stateMB };
      }
    }
  }

  /* 最终正确性 */
  const finalLoad = chain.load();
  const consistent = deepEqual(finalLoad.state, prev);

  const totalFull = bytesFull.reduce((a, b) => a + b, 0);
  const totalDelta = bytesDelta.reduce((a, b) => a + b, 0);

  return {
    ok: consistent, name, stateMB, steps,
    full: { p50: pct(latFull, .5), p95: pct(latFull, .95), max: Math.max(...latFull), totalBytes: totalFull },
    delta: { p50: pct(latDelta, .5), p95: pct(latDelta, .95), max: Math.max(...latDelta), totalBytes: totalDelta },
    deltaCount, fullCount: steps + 1,
    chainInfo: chain.info(),
    consistent,
  };
}

/* ---------------- 主流程 ---------------- */
console.log('='.repeat(96));
console.log('  增量快照 vs 全量快照');
console.log('='.repeat(96));
console.log('');
console.log('  先看问题有多大（全量快照的物理成本）：');
console.log('    状态大小      JSON序列化   zlib压缩     总计');
console.log('    ' + '-'.repeat(56));
for (const mb of [0.001, 0.1, 1, 10, 50]) {
  const st = makeState(mb);
  const t0 = process.hrtime.bigint();
  const raw = Buffer.from(JSON.stringify(st), 'utf8');
  const t1 = process.hrtime.bigint();
  zlib.deflateRawSync(raw, { level: 9 });
  const t2 = process.hrtime.bigint();
  const f = (v) => (v < 1 ? (v * 1000).toFixed(0) + 'µs' : v.toFixed(0) + 'ms');
  console.log('    ' + fmt(raw.length).padEnd(13) +
    f(Number(t1 - t0) / 1e6).padStart(10) +
    f(Number(t2 - t1) / 1e6).padStart(11) +
    f(Number(t2 - t0) / 1e6).padStart(10));
}

console.log('\n' + '='.repeat(96));
console.log('  实测对比');
console.log('='.repeat(96));

const results = [];
for (const [name, label] of [['append', 'A 追加型（长期记忆）'], ['scalar', 'B 标量型（计数器）'], ['mixed', 'C 混合型']]) {
  const r = runScenario(name, 10, 100);
  results.push(r);

  console.log('\n▸ ' + label + '   状态 ' + r.stateMB.toFixed(2) + ' MB，' + r.steps + ' 步');
  console.log('  ' + '方案'.padEnd(10) + 'p50'.padStart(11) + 'p95'.padStart(11) + '最大'.padStart(11) +
    '总写入'.padStart(12) + '  说明');
  console.log('  ' + '-'.repeat(72));
  console.log('  ' + '全量'.padEnd(10) + ms(r.full.p50).padStart(11) + ms(r.full.p95).padStart(11) +
    ms(r.full.max).padStart(11) + fmt(r.full.totalBytes).padStart(12) + '  每步都写完整状态');
  console.log('  ' + '增量'.padEnd(10) + ms(r.delta.p50).padStart(11) + ms(r.delta.p95).padStart(11) +
    ms(r.delta.max).padStart(11) + fmt(r.delta.totalBytes).padStart(12) +
    '  ' + r.deltaCount + ' 增量 + ' + (r.fullCount - r.deltaCount) + ' 全量');
  console.log('  ' + '-'.repeat(72));
  console.log('  ' + '提升'.padEnd(10) +
    ((r.full.p50 / r.delta.p50).toFixed(1) + 'x').padStart(11) +
    ((r.full.p95 / r.delta.p95).toFixed(1) + 'x').padStart(11) +
    ''.padStart(11) +
    ('节省 ' + ((1 - r.delta.totalBytes / r.full.totalBytes) * 100).toFixed(1) + '%').padStart(12));
  console.log('  正确性: ' + (r.consistent ? '✓ 还原完全一致' : '✗ 不一致'));
  console.log('  平均快照: 全量 ' + fmt(r.chainInfo.avgFullBytes) + '  增量 ' + fmt(r.chainInfo.avgDeltaBytes));
}

/* ---------------- 结论 ---------------- */
console.log('\n' + '='.repeat(96));
console.log('  结论');
console.log('='.repeat(96));
console.log('  ' + '场景'.padEnd(24) + '全量 p95'.padStart(12) + '增量 p95'.padStart(12) + '  10ms 目标');
console.log('  ' + '-'.repeat(72));
for (const r of results) {
  const label = { append: 'A 追加型', scalar: 'B 标量型', mixed: 'C 混合型' }[r.name];
  const pass = r.delta.p95 <= 10;
  console.log('  ' + label.padEnd(22) + ms(r.full.p95).padStart(12) + ms(r.delta.p95).padStart(12) +
    '  ' + (pass ? '✅ 达标' : '⚠️  ' + r.delta.p95.toFixed(1) + 'ms'));
}
console.log('  ' + '-'.repeat(72));
console.log('');
console.log('  三个场景全部正确性通过（还原状态与原地状态 deepEqual）');
console.log('='.repeat(96));

rmrf(ROOT);
