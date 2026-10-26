#!/usr/bin/env node
'use strict';
/* 子进程：抢锁 → 写 N 条 → 报告 → 退出（或被 kill） */
const { LockedStore } = require('./lock');

const DIR = process.argv[2];
const ID = process.argv[3];
const COUNT = parseInt(process.argv[4] || '50', 10);
const HOLD_MS = parseInt(process.argv[5] || '0', 10);

const apply = (state, rec) => {
  state = state || { writes: [] };
  state.writes.push(rec.args[0]);
  return state;
};

let store;
try {
  store = new LockedStore({ dir: DIR, mode: 'fsync', heartbeatMs: 1000 });
} catch (e) {
  process.stdout.write(JSON.stringify({ type: 'locked-out', id: ID, error: e.message }) + '\n');
  process.exit(2);
}

process.stdout.write(JSON.stringify({ type: 'acquired', id: ID, pid: process.pid }) + '\n');

let st = store.recover(apply).state || { writes: [] };
let ok = 0, fail = 0;
for (let i = 0; i < COUNT; i++) {
  const r = store.append('w', [ID + ':' + i]);
  if (r.ok) { ok++; st.writes.push(ID + ':' + i); store.setState(st); }
  else fail++;
  if (HOLD_MS && i === 0) {
    /* 故意持锁一段时间，让别的进程等 */
    const until = Date.now() + HOLD_MS;
    while (Date.now() < until) {}
  }
}

process.stdout.write(JSON.stringify({ type: 'done', id: ID, ok, fail, total: st.writes.length }) + '\n');
store.close();
