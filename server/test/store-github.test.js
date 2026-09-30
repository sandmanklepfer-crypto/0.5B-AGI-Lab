'use strict';
/*
 * GitHub 存储后端的离线测试：伪造一个 GitHub API，验证
 *   1) 首次写入（文件不存在 → 自动创建）
 *   2) 读回 / 更新 / 列表
 *   3) sha 冲突（409）自动重试
 *   4) 多实例并发写不丢单
 *
 * 运行：node test/store-github.test.js
 */
const https = require('https');
const { PassThrough } = require('stream');
const { createGitHubStore } = require('../lib/store');

let pass = 0, fail = 0;
const ok = (name, cond, extra) => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

/* ---------- 伪造 GitHub API ---------- */
const repo = { file: null, sha: 0 };       // 模拟仓库里的一个文件
let conflictOnce = false;                  // 下一次 PUT 强制返回 409
let putCount = 0;

const origRequest = https.request;
https.request = function (opts, cb) {
  const req = new PassThrough();
  req.setHeader = () => {};
  let body = '';
  req.on('data', d => body += d);

  const respond = (status, obj) => {
    const res = new PassThrough();
    res.statusCode = status;
    res.headers = {};
    process.nextTick(() => { cb(res); res.end(JSON.stringify(obj)); });
  };

  req.end = (data) => {
    if (data) body += data;
    const method = opts.method;
    const path = opts.path || '';

    if (method === 'GET') {
      if (!repo.file) return respond(404, { message: 'Not Found' });
      return respond(200, {
        sha: 'sha' + repo.sha,
        encoding: 'base64',
        content: Buffer.from(repo.file).toString('base64'),
      });
    }

    if (method === 'PUT') {
      putCount++;
      const parsed = JSON.parse(body);
      if (conflictOnce) {                       // 模拟并发冲突
        conflictOnce = false;
        return respond(409, { message: 'sha does not match' });
      }
      if (repo.file && parsed.sha !== 'sha' + repo.sha) {
        return respond(409, { message: 'sha does not match' });
      }
      const text = Buffer.from(parsed.content, 'base64').toString('utf8');
      repo.file = text; repo.sha++;
      return respond(200, { content: { sha: 'sha' + repo.sha } });
    }
    respond(404, { message: 'Not Found' });
  };
  req.on = req.on.bind(req);
  return req;
};

const mk = () => createGitHubStore({
  token: 'fake', owner: 'me', repo: 'shop', file: 'server-orders/orders.json', branch: 'main',
});

(async () => {
  console.log('\n== GitHub 存储后端 ==');

  const s = mk();
  await s.create({ outTradeNo: 'LH001', total: 56, createdAt: 100 });
  ok('文件不存在时能自动创建并写入', !!repo.file, repo.file);

  const back = await s.get('LH001');
  ok('能读回刚写的订单', back && back.total === 56, back);

  await s.update('LH001', { status: 'PAID', paidAt: 999 });
  const upd = await s.get('LH001');
  ok('更新生效', upd.status === 'PAID' && upd.paidAt === 999, upd);

  await s.create({ outTradeNo: 'LH002', total: 20, createdAt: 200 });
  const list = await s.list();
  ok('列表按时间倒序', list.map(x => x.outTradeNo).join(',') === 'LH002,LH001', list.map(x => x.outTradeNo));

  ok('不存在的订单返回 null', (await s.get('NOPE')) === null);

  console.log('\n== sha 冲突自动重试 ==');
  conflictOnce = true;
  const before = putCount;
  await s.create({ outTradeNo: 'LH003', total: 30, createdAt: 300 });
  ok('遇到 409 会重试并最终成功', putCount > before + 1, { puts: putCount - before });
  ok('冲突后数据没丢', !!(await s.get('LH003')), null);

  console.log('\n== 两个实例并发（模拟多容器）==');
  repo.file = null; repo.sha = 0;
  const a = mk(), b = mk();
  await Promise.all([
    a.create({ outTradeNo: 'X1', total: 1, createdAt: 1 }),
    b.create({ outTradeNo: 'X2', total: 2, createdAt: 2 }),
    a.create({ outTradeNo: 'X3', total: 3, createdAt: 3 }),
    b.create({ outTradeNo: 'X4', total: 4, createdAt: 4 }),
  ]);
  const finalAll = JSON.parse(repo.file).orders;
  ok('并发写后 4 单都在（合并策略生效）', Object.keys(finalAll).length === 4, Object.keys(finalAll));

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  https.request = origRequest;
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); https.request = origRequest; process.exit(1); });
