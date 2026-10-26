#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  lock_test.js —— 多进程并发锁测试
 *  --------------------------------------------------------------------------
 *  要证明三件事：
 *
 *    ① 互斥      多个进程同时抢，只有一个能拿到
 *    ② 不丢写    最终记录数 == 所有成功写入之和
 *    ③ 僵尸可回收 进程被 kill -9 后，锁能自动被抢走
 *
 *  ② 是最难的：如果两个进程都以为自己持锁，就会互相覆盖写。
 * ========================================================================== */
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const { FileLock } = require('./lock');

const DIR = '/tmp/locktest';
const CHILD = path.join(__dirname, 'lock_child.js');
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function rmrf(p) { try { fs.rmSync(p, { recursive: true, force: true }); } catch (e) {} }

/* 跑一个子进程，收集输出 */
function runChild(id, count, holdMs) {
  return new Promise((resolve) => {
    const c = spawn(process.execPath, [CHILD, DIR, id, String(count), String(holdMs || 0)],
      { stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    c.stdout.on('data', d => out += d.toString());
    c.stderr.on('data', d => err += d.toString().slice(0, 300));
    const t0 = Date.now();
    c.on('close', (code) => {
      let rec = null;
      for (const l of out.trim().split('\n')) {
        if (!l.trim()) continue;
        try { const o = JSON.parse(l); if (o.type === 'done') rec = o; } catch (e) {}
      }
      resolve({ id, code, rec, out, err, ms: Date.now() - t0 });
    });
  });
}

(async () => {
  console.log('='.repeat(84));
  console.log('  多进程文件锁测试');
  console.log('='.repeat(84));

  /* ---------------- ① 互斥 ---------------- */
  console.log('\n▸ ① 互斥：6 个进程同时抢锁，每个写 40 条');
  rmrf(DIR); fs.mkdirSync(DIR, { recursive: true });

  const N_PROC = 6, PER = 40;
  const results = await Promise.all(
    Array.from({ length: N_PROC }, (_, i) => runChild('p' + i, PER, 0))
  );

  const acquired = results.filter(r => r.rec);
  const lockedOut = results.filter(r => !r.rec && /locked-out/.test(r.out));
  const totalWritten = acquired.reduce((a, r) => a + (r.rec ? r.rec.ok : 0), 0);

  console.log('  进程'.padEnd(8) + '状态'.padStart(10) + '写入'.padStart(8) + '耗时'.padStart(9));
  console.log('  ' + '-'.repeat(40));
  for (const r of results) {
    const st = r.rec ? '✓ 拿到锁' : (/locked-out/.test(r.out) ? '✗ 被拒' : '✗ 异常(' + r.code + ')');
    console.log('  ' + r.id.padEnd(8) + st.padStart(10) +
      String(r.rec ? r.rec.ok : 0).padStart(8) + String(r.ms + 'ms').padStart(9));
  }
  console.log('  ' + '-'.repeat(40));
  console.log('  全部拿到锁: ' + acquired.length + '/' + N_PROC + '  （串行执行，所以都拿到了）');
  console.log('  总写入: ' + totalWritten);

  /* 校验：最终记录数 = 总写入数 */
  const { WalStore } = require('./wal');
  const s = new WalStore({ dir: DIR, mode: 'fsync' });
  const rec = s.recover((state, rc) => { state = state || { writes: [] }; state.writes.push(rc.args[0]); return state; });
  s.close();
  const finalN = rec.state ? rec.state.writes.length : 0;
  const uniq = rec.state ? new Set(rec.state.writes).size : 0;
  const dup = finalN - uniq;

  console.log('  恢复后记录数: ' + finalN + '   去重后: ' + uniq + '   重复: ' + dup);
  const t1ok = (finalN === totalWritten) && (dup === 0);
  console.log('  ' + (t1ok ? '✓ 无丢失、无重复（互斥生效）' : '✗ 数据不一致'));

  /* ---------------- ② 僵尸锁回收 ---------------- */
  console.log('\n▸ ② 僵尸锁回收：kill -9 持有者，另一个进程应能抢到');
  rmrf(DIR); fs.mkdirSync(DIR, { recursive: true });

  /* 起一个进程，持锁不退出 */
  const holder = spawn(process.execPath, [CHILD, DIR, 'holder', '5', '60000'],
    { stdio: ['ignore', 'pipe', 'pipe'] });
  let holderOut = '';
  holder.stdout.on('data', d => holderOut += d.toString());
  await sleep(1200);       // 等它拿到锁

  const lockBefore = new FileLock({ dir: DIR, name: 'wal' }).inspect();
  console.log('  持有者: ' + (lockBefore.holder ? 'pid=' + lockBefore.holder.pid : '无') +
    '  存活=' + lockBefore.alive);

  /* 确认此时别的进程抢不到 */
  const blocked = await runChild('blocked', 5, 0);
  console.log('  持锁期间别人抢: ' + (blocked.rec ? '✗ 竟然拿到了' : '✓ 被拒'));

  /* kill -9 */
  holder.kill('SIGKILL');
  await sleep(600);
  const lockAfterKill = new FileLock({ dir: DIR, name: 'wal' }).inspect();
  console.log('  kill 后锁文件: ' + (lockAfterKill.exists ? '仍在（僵尸）' : '已清'));

  /* 现在应该能抢到 */
  const afterKill = await runChild('afterkill', 5, 0);
  console.log('  kill 后别人抢: ' + (afterKill.rec ? '✓ 拿到（僵尸回收成功）' : '✗ 仍被拒'));

  const t2ok = !!afterKill.rec;

  /* ---------------- ③ 释放后可用 ---------------- */
  console.log('\n▸ ③ 正常释放后，别人能立刻拿到');
  rmrf(DIR); fs.mkdirSync(DIR, { recursive: true });
  const a = await runChild('A', 10, 0);
  const b = await runChild('B', 10, 0);
  const t3ok = !!(a.rec && b.rec);
  console.log('  A: ' + (a.rec ? '✓ ' + a.rec.ok + ' 条' : '✗'));
  console.log('  B: ' + (b.rec ? '✓ ' + b.rec.ok + ' 条' : '✗'));
  console.log('  ' + (t3ok ? '✓ 释放正常' : '✗ 释放有问题'));

  /* ---------------- 汇总 ---------------- */
  console.log('\n' + '='.repeat(84));
  console.log('  汇总');
  console.log('='.repeat(84));
  console.log('  ① 互斥+不丢写    ' + (t1ok ? '✓ 通过' : '✗ 失败'));
  console.log('  ② 僵尸锁回收    ' + (t2ok ? '✓ 通过' : '✗ 失败'));
  console.log('  ③ 正常释放      ' + (t3ok ? '✓ 通过' : '✗ 失败'));
  console.log('='.repeat(84));

  rmrf(DIR);
})();
