#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  diskfull_test.js —— 磁盘满 / IO 错误测试
 *  --------------------------------------------------------------------------
 *  难点：怎么在用户态可靠地模拟 ENOSPC？
 *
 *  三个办法，我选了第三个：
 *    ① 真的写满一个 loop 设备  —— 需要 root 和 losetup，这台机器不行
 *    ② 临时改 ulimit -f        —— 影响整个进程，容易把测试自己弄死
 *    ③ monkey-patch fs 函数     —— 精确、可控、只影响被测对象  ✓
 *
 *  ★ 但 monkey-patch 有个必须承认的局限：
 *     它测的是「我的错误处理逻辑」，不是「真实的 ENOSPC 行为」。
 *     真实的 ENOSPC 可能在任何一次 write 才报（页缓存延迟），
 *     而 patch 是当场报。这个差异我在结论里写明。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');

const DIR = '/tmp/diskfull';

function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }

/* ---------------------------- 注入故障 ---------------------------- */
/* 只劫持对 DIR 的写，其他正常 */
function injectFault({ writeErr, fsyncErr, renameErr, openErr, afterWrites = 0 }) {
  const originals = {
    writeSync: fs.writeSync,
    fsyncSync: fs.fsyncSync,
    renameSync: fs.renameSync,
    openSync: fs.openSync,
  };
  let writes = 0;
  const mk = (code, sys) => Object.assign(new Error(code + ': simulated'), { code, syscall: sys });

  fs.writeSync = function (fd, ...a) {
    if (writeErr) {
      writes++;
      if (writes > afterWrites) throw mk(writeErr, 'write');
    }
    return originals.writeSync.call(fs, fd, ...a);
  };
  fs.fsyncSync = function (fd) {
    if (fsyncErr) throw mk(fsyncErr, 'fsync');
    return originals.fsyncSync.call(fs, fd);
  };
  fs.renameSync = function (a, b) {
    if (renameErr) throw mk(renameErr, 'rename');
    return originals.renameSync.call(fs, a, b);
  };
  fs.openSync = function (p, ...a) {
    if (openErr && String(p).startsWith(DIR)) throw mk(openErr, 'open');
    return originals.openSync.call(fs, p, ...a);
  };

  return () => { Object.assign(fs, originals); };
}

/* ---------------------------- 场景 ---------------------------- */
const apply = (state, rec) => {
  state = state || { n: 0 };
  if (rec.op === 'inc') state.n += 1;
  return state;
};

function fresh() { rmrf(DIR); fs.mkdirSync(DIR, { recursive: true }); }
const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };

const scenarios = [];

/* ① 写入时磁盘满 */
scenarios.push({
  name: '写入 ENOSPC（磁盘满）',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const s = new WalStore({ dir: DIR, mode: 'fsync' });
    let st = { n: 0 };
    for (let i = 0; i < 10; i++) {
      const r = s.append('inc', [1]);
      if (!r.ok) return { stage: 'pre', error: r.error };
      st.n++; s.setState(st);
    }
    const restore = injectFault({ writeErr: 'ENOSPC' });
    const r = s.append('inc', [1]);
    // 再写几次，确认一直是拒绝状态
    const r2 = s.append('inc', [1]);
    restore();

    const degraded = s.degraded;
    s.close();

    return {
      writeResult: r,
      secondWrite: r2,
      degraded,
      processAlive: true,        // 走到这里就说明没崩
      ok: !r.ok && r.degraded === 'readonly' && degraded && degraded.level === 'readonly',
    };
  }
});

/* ② fsync 时 ENOSPC */
scenarios.push({
  name: 'fsync ENOSPC',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const s = new WalStore({ dir: DIR, mode: 'fsync' });
    s.setState({ n: 0 });
    const restore = injectFault({ fsyncErr: 'ENOSPC' });
    const r = s.append('inc', [1]);
    restore();
    const d = s.degraded;
    s.close();
    return { writeResult: r, degraded: d, processAlive: true, ok: !r.ok && d && d.level === 'readonly' };
  }
});

/* ③ EIO（硬件故障）→ fault 级降级 */
scenarios.push({
  name: 'fsync EIO（硬件故障）',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const s = new WalStore({ dir: DIR, mode: 'fsync' });
    s.setState({ n: 0 });
    const restore = injectFault({ fsyncErr: 'EIO' });
    const r = s.append('inc', [1]);
    restore();
    const d = s.degraded;
    s.close();
    return { writeResult: r, degraded: d, processAlive: true, ok: !r.ok && d && d.level === 'fault' };
  }
});

/* ④ 磁盘满后恢复 */
scenarios.push({
  name: '磁盘满 → 腾出空间 → 恢复',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const s = new WalStore({ dir: DIR, mode: 'fsync' });
    let st = { n: 0 };
    for (let i = 0; i < 5; i++) { const r = s.append('inc', [1]); if (r.ok) { st.n++; s.setState(st); } }

    const restore = injectFault({ writeErr: 'ENOSPC' });
    const failed = s.append('inc', [1]);
    restore();

    const before = s.degraded;
    const rec = s.tryRecover();          // 磁盘已腾空，探针应成功
    const after = s.degraded;
    const resumed = s.append('inc', [1]); // 恢复后能继续写

    s.close();
    const s2 = new WalStore({ dir: DIR, mode: 'fsync' });
    const r2 = s2.recover(apply);
    s2.close();

    return {
      failed, degradedBefore: before,
      recoverResult: rec, degradedAfter: after,
      resumed, recoveredN: r2.state.n,
      ok: !failed.ok && rec && rec.ok && after === null && resumed.ok && r2.state.n >= 5,
    };
  }
});

/* ⑤ compaction 时磁盘满（快照写失败） */
scenarios.push({
  name: 'compaction 时快照写失败',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const s = new WalStore({ dir: DIR, mode: 'os' });
    let st = { n: 0 };
    for (let i = 0; i < 50; i++) { s.append('inc', [1]); st.n++; }
    s.setState(st);

    const restore = injectFault({ writeErr: 'ENOSPC' });
    const c = s.compact();
    restore();

    /* 关键：快照失败时，旧段必须保留（数据不能丢） */
    const segsAfter = s.log.segs.length;
    s.close();
    const s2 = new WalStore({ dir: DIR, mode: 'os' });
    const r2 = s2.recover(apply);
    s2.close();

    return {
      compactResult: c,
      segmentsKept: segsAfter,
      recoveredN: r2.state.n,
      ok: c && !c.ok && r2.state.n === 50,   // 压缩失败但数据完整
    };
  }
});

/* ⑥ 打开段文件失败（权限/路径） */
scenarios.push({
  name: '无法创建段文件（EACCES）',
  async run() {
    fresh();
    const { WalStore } = require('./wal');
    const restore = injectFault({ openErr: 'EACCES' });
    let s, err = null;
    try { s = new WalStore({ dir: DIR, mode: 'os' }); }
    catch (e) { err = e; }
    restore();
    if (s) { const d = s.degraded; s.close(); return { degraded: d, ok: d && d.level === 'fault' }; }
    return { err: String(err), ok: false, note: '构造时抛异常（未降级）' };
  }
});

/* ------------------------------------------------------------------ */
(async () => {
  console.log('='.repeat(90));
  console.log('  磁盘满 / IO 错误测试');
  console.log('  核心问题：任何一个 IO 失败，进程会不会直接挂？');
  console.log('='.repeat(90));

  let pass = 0;
  for (const sc of scenarios) {
    process.stdout.write('\n▸ ' + sc.name + '\n');
    let r;
    try {
      r = await sc.run();
    } catch (e) {
      console.log('  ✗ 测试本身抛异常（说明没有保护）: ' + e.message);
      continue;
    }
    const mark = r.ok ? '✓ 通过' : '✗ 失败';
    if (r.ok) pass++;

    /* 逐项打印 */
    const show = (k, v) => {
      if (v === undefined) return;
      const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
      console.log('    ' + k.padEnd(18) + s.slice(0, 100));
    };
    if (r.writeResult) {
      show('写入结果', { ok: r.writeResult.ok, degraded: r.writeResult.degraded, code: r.writeResult.code });
    }
    if (r.degraded !== undefined) show('降级状态', r.degraded);
    if (r.failed) show('失败写入', { ok: r.failed.ok, code: r.failed.code });
    if (r.recoverResult) show('tryRecover', r.recoverResult);
    if (r.resumed) show('恢复后写入', { ok: r.resumed.ok, seq: r.resumed.seq });
    if (r.recoveredN !== undefined) show('恢复后 n', r.recoveredN);
    if (r.compactResult) show('compact', { ok: r.compactResult.ok, error: r.compactResult.error });
    if (r.segmentsKept !== undefined) show('保留段数', r.segmentsKept);
    if (r.err) show('异常', r.err);
    if (r.note) show('备注', r.note);

    console.log('    进程存活          true   ← 没有崩');
    console.log('    ' + mark);
  }

  console.log('\n' + '='.repeat(90));
  console.log('  结果: ' + pass + '/' + scenarios.length + ' 通过');
  console.log('='.repeat(90));
  console.log('');
  console.log('  必须承认的局限：');
  console.log('    · monkey-patch 是「当场抛错」，真实 ENOSPC 可能延迟到下一次 write');
  console.log('    · 没有测「写到一半被杀 + 磁盘满」的组合场景');
  console.log('    · 没有测真实只读挂载（EROFS）的行为');
  console.log('  所以本测试证明的是「错误处理逻辑正确」，不是「真实硬件异常下的行为」');
  console.log('='.repeat(90));

  rmrf(DIR);
})();
