#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  crash_test.js —— 崩溃恢复测试
 *  --------------------------------------------------------------------------
 *  这是最难的一步，因为它的失败方式是【静默的】：
 *  数据可能看起来对，但少了几条、或重放出重复记录。
 *
 *  测试做法：
 *    1. 启动子进程，它不断写 WAL 并报告"已确认的 n"
 *    2. 随机等一段时间，SIGKILL（不是 SIGTERM —— 不给它任何清理机会）
 *    3. 父进程重新打开，恢复
 *    4. 校验三件事：
 *
 *       ① 不丢已确认   recovered.n >= 崩溃前最后一次 ack 的 n
 *       ② 无跳号       WAL 里的 seq 必须连续
 *       ③ 状态自洽     恢复出的 sum 必须等于 1+2+...+n
 *
 *  ① 是最重要的：如果 fsync 模式丢了已确认的数据，那就是致命 bug。
 * ========================================================================== */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { WalStore } = require('./wal');

const HERE = __dirname;
const DIR = '/tmp/crashtest';
const TRIALS = parseInt(process.env.TRIALS || '12', 10);

const apply = (state, rec) => {
  state = state || { n: 0, sum: 0 };
  if (rec.op === 'inc') { state.n += 1; state.sum += rec.args[0]; }
  return state;
};

function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

/* 跑一次试验 */
async function trial(idx, { mode, compactEvery, killAfterMs, segMax, killAtAck }) {
  rmrf(DIR);

  const child = spawn(process.execPath, [
    path.join(HERE, 'crash_child.js'),
    DIR, mode, String(compactEvery || 0), String(segMax || 256 * 1024),
  ], { stdio: ['ignore', 'pipe', 'pipe'] });

  let lastAck = { n: 0, sum: 0, seq: 0 };
  let boots = [];
  let buf = '';

  child.stdout.on('data', (d) => {
    buf += d.toString();
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const l of lines) {
      if (!l.trim()) continue;
      try {
        const o = JSON.parse(l);
        if (o.type === 'ack') lastAck = { n: o.n, sum: o.sum, seq: o.seq };
        else if (o.type === 'boot') boots.push(o);
      } catch (e) {}
    }
  });
  let stderrBuf = '';
  child.stderr.on('data', (d) => { stderrBuf += d.toString().slice(0, 500); });

  /* ★ 按"写入条数"触发 kill，而不是按时间：
     机器负载高时 node 启动就要几百毫秒，按时间 kill 会杀掉还没开始写的进程，
     测试就变成了空转。按条数才能保证"写到一半被杀"。
     随后再等一个 0~15ms 的随机抖动，让 kill 落在不确定的写入位置。 */
  const target = killAtAck;
  const t0wait = Date.now();
  while (lastAck.n < target && Date.now() - t0wait < 8000) await sleep(5);
  await sleep(Math.floor(Math.random() * 15));
  child.kill('SIGKILL');            // ★ 不给清理机会
  await sleep(150);

  /* 恢复 */
  const t0 = Date.now();
  const s = new WalStore({ dir: DIR, mode, segMaxBytes: segMax || 256 * 1024 });
  let rec;
  try {
    rec = s.recover(apply);
  } catch (e) {
    s.close();
    return { idx, mode, ok: false, err: '恢复抛异常: ' + e.message, lastAck, stderrBuf };
  }

  /* 校验 ②：seq 连续 */
  const allRecs = s.log.replay(0);
  let gap = null;
  for (let i = 1; i < allRecs.length; i++) {
    if (allRecs[i].seq !== allRecs[i - 1].seq + 1) { gap = { at: i, a: allRecs[i - 1].seq, b: allRecs[i].seq }; break; }
  }

  /* 校验 ③：状态自洽 —— sum 必须等于 1+2+...+n
     ★ 子进程可能还没写任何东西就被杀，此时 state 为 null */
  const st = rec.state || { n: 0, sum: 0 };
  const expectSum = st.n * (st.n + 1) / 2;
  const selfConsistent = st.sum === expectSum;

  /* 校验 ①：不丢已确认 */
  const noLoss = st.n >= lastAck.n;

  s.close();
  const ms = Date.now() - t0;

  return {
    idx, mode, ok: noLoss && !gap && selfConsistent,
    noLoss, gap, selfConsistent,
    ackedN: lastAck.n, recoveredN: st.n, lostN: lastAck.n - st.n,
    ackedSum: lastAck.sum, recoveredSum: st.sum, expectSum,
    replayedCount: rec.applied, snapSeq: rec.snapSeq,
    segs: s.info().segments, ms, stderrBuf,
  };
}

/* ------------------------------------------------------------------ */
(async () => {
  console.log('='.repeat(92));
  console.log('  崩溃恢复测试 —— 随机 SIGKILL，验证不丢已确认数据');
  console.log('  ' + TRIALS + ' 次试验 / 配置');
  console.log('='.repeat(92));

  const configs = [
    { name: 'os（不 fsync）',   mode: 'os',    compactEvery: 0 },
    { name: 'fsync（每次刷）',  mode: 'fsync', compactEvery: 0 },
    { name: 'fsync + compaction', mode: 'fsync', compactEvery: 300 },
    { name: 'group(5ms)',      mode: 'group', compactEvery: 0 },
  ];

  const summary = [];

  for (const cfg of configs) {
    console.log('\n▸ ' + cfg.name);
    console.log('  ' + '轮'.padEnd(4) + '已确认n'.padStart(9) + '恢复n'.padStart(9) +
      '丢失'.padStart(7) + '跳号'.padStart(6) + '自洽'.padStart(6) + '重放'.padStart(7) +
      '段'.padStart(4) + '恢复ms'.padStart(8) + '  判定');
    console.log('  ' + '-'.repeat(84));

    let pass = 0;
    let worstLoss = 0;

    for (let i = 0; i < TRIALS; i++) {
      /* 随机 kill 时机：20~260ms，覆盖"刚开始写"到"写了很多" */
      /* 每轮随机目标条数：30 ~ 800 条，覆盖"刚起步"到"积累了快照" */
      const killAtAck = 30 + Math.floor(Math.random() * 770);
      const r = await trial(i, Object.assign({ killAtAck }, cfg));

      if (r.ok) pass++;
      if (r.lostN > worstLoss) worstLoss = r.lostN;

      const mark = r.ok ? '✓' : '✗';
      console.log('  ' + String(i + 1).padEnd(4) +
        String(r.ackedN).padStart(9) + String(r.recoveredN).padStart(9) +
        String(r.lostN > 0 ? '-' + r.lostN : '0').padStart(7) +
        (r.gap ? '有' : '无').padStart(6) +
        (r.selfConsistent ? '✓' : '✗').padStart(6) +
        String(r.replayedCount).padStart(7) +
        String(r.segs || 0).padStart(4) +
        String(r.ms).padStart(8) + '  ' + mark + (r.err ? ' ' + r.err : '') +
        (r.stderrBuf ? ' [stderr] ' + r.stderrBuf.trim().split('\n')[0].slice(0, 60) : ''));
    }

    console.log('  ' + '-'.repeat(84));
    console.log('  通过 ' + pass + '/' + TRIALS + '   最大丢失 ' + worstLoss + ' 条');
    summary.push({ cfg: cfg.name, pass, total: TRIALS, worstLoss });
  }

  console.log('\n' + '='.repeat(92));
  console.log('  汇总');
  console.log('='.repeat(92));
  console.log('  配置'.padEnd(24) + '通过'.padStart(10) + '最大丢失'.padStart(12) + '  判定');
  console.log('  ' + '-'.repeat(80));
  for (const s of summary) {
    const verdict = s.pass === s.total
      ? (s.worstLoss === 0 ? '✅ 完全不丢' : '✅ 通过')
      : '❌ 有失败';
    console.log('  ' + s.cfg.padEnd(22) + (s.pass + '/' + s.total).padStart(10) +
      String(s.worstLoss).padStart(12) + '  ' + verdict);
  }
  console.log('  ' + '-'.repeat(80));
  console.log('');
  console.log('  说明：');
  console.log('    · os 模式丢几条是【预期行为】—— 没 fsync，断电必丢最后几条');
  console.log('    · fsync 模式丢任何一条都是【致命 bug】');
  console.log('    · 跳号 = WAL 断裂；自洽失败 = 状态被破坏');
  console.log('='.repeat(92));

  rmrf(DIR);
})();
