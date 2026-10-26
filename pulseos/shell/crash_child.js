#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  crash_child.js —— 崩溃测试的子进程
 *  --------------------------------------------------------------------------
 *  做两件事：
 *    1. 不断写 WAL，每次成功后把 seq/state 打到 stdout（父进程读它当"已确认"）
 *    2. 按需触发 compaction（这样也能测"崩溃在 compaction 中间"）
 *
 *  父进程会随机时刻 SIGKILL 我。所以我不能依赖任何"优雅退出"逻辑。
 * ========================================================================== */
const { WalStore } = require('./wal');

const DIR = process.argv[2];
const MODE = process.argv[3] || 'os';
const COMPACT_EVERY = parseInt(process.argv[4] || '0', 10);   // 0 = 不压缩
const SEG_MAX = parseInt(process.argv[5] || String(256 * 1024), 10);

const apply = (state, rec) => {
  state = state || { n: 0, sum: 0 };
  if (rec.op === 'inc') { state.n += 1; state.sum += rec.args[0]; }
  return state;
};

const s = new WalStore({ dir: DIR, mode: MODE, segMaxBytes: SEG_MAX, compactEvery: COMPACT_EVERY || 1e9 });
const r0 = s.recover(apply);
let state = r0.state || { n: 0, sum: 0 };

/* 一开始就告诉父进程：我恢复到了哪里 */
process.stdout.write(JSON.stringify({ type: 'boot', n: state.n, snapSeq: r0.snapSeq, replayed: r0.applied }) + '\n');

let i = 0;
function tick() {
  i++;
  s.append('inc', [i]);
  state.n += 1;
  state.sum += i;
  s.setState(state);

  /* 关键：append 返回后才算"已确认"（fsync 模式下已在磁盘） */
  process.stdout.write(JSON.stringify({ type: 'ack', seq: s.log.lastSeq, n: state.n, sum: state.sum }) + '\n');

  if (COMPACT_EVERY) {
    const c = s.maybeCompact();
    if (c) process.stdout.write(JSON.stringify({ type: 'compacted', seq: c.seq }) + '\n');
  }

  setImmediate(tick);
}
tick();
