'use strict';
/*
 * ghchat.js 离线测试：伪造 GitHub API，验证
 *   1) 大厅收发
 *   2) 并发写入不丢消息（409 冲突重试 + 按 id 去重）
 *   3) 用户表 upsert（在线状态）
 *   4) 私聊 + 私聊索引
 *   5) 图片上传路径
 *   6) Token 权限不足时能报错
 *
 * 运行：node server/test/ghchat.test.js
 */
let pass = 0, fail = 0;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

/* ---------- 伪造 GitHub ---------- */
const files = new Map();      // path -> { content(string), sha }
let shaSeq = 0;
let conflictNext = 0;         // 接下来 N 次 PUT 强制 409
let permPush = true;          // 是否有写权限
let putCount = 0;

function makeSha() { return 'sha' + (++shaSeq).toString(36).padStart(5, '0'); }
const b64 = s => Buffer.from(String(s), 'utf8').toString('base64');
const unb64 = s => Buffer.from(String(s).replace(/\s/g, ''), 'base64').toString('utf8');

global.fetch = async function (url, opts) {
  opts = opts || {};
  const method = (opts.method || 'GET').toUpperCase();
  const u = new URL(url);
  const path = u.pathname;
  const json = (code, obj) => ({ ok: code < 400, status: code, text: async () => JSON.stringify(obj) });

  if (path === '/user') return json(200, { login: 'tester' });
  if (/^\/repos\/[^/]+\/[^/]+$/.test(path)) {
    return json(200, { full_name: 'tester/chat', private: true, permissions: { push: permPush, pull: true } });
  }

  const m = path.match(/^\/repos\/[^/]+\/[^/]+\/contents\/(.+)$/);
  if (!m) return json(404, { message: 'Not Found' });
  const rel = decodeURIComponent(m[1]);

  if (method === 'GET') {
    const f = files.get(rel);
    if (!f) return json(404, { message: 'Not Found' });
    return json(200, { sha: f.sha, content: b64(f.content), encoding: 'base64' });
  }

  if (method === 'PUT') {
    putCount++;
    if (!permPush) return json(403, { message: 'Resource not accessible by integration' });
    const body = JSON.parse(opts.body || '{}');
    const cur = files.get(rel);
    if (conflictNext > 0) {
      conflictNext--;
      return json(409, { message: 'sha does not match' });
    }
    if (cur && body.sha !== cur.sha) return json(409, { message: 'sha does not match' });
    if (!cur && body.sha) return json(409, { message: 'sha does not match' });
    const content = unb64(body.content);
    const sha = makeSha();
    files.set(rel, { content, sha });
    return json(200, { content: { sha } });
  }
  return json(405, { message: 'no' });
};

/* ---------- 伪造 localStorage ---------- */
const mem = {};
global.localStorage = {
  getItem: k => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: k => { delete mem[k]; },
};
global.btoa = s => Buffer.from(String(s), 'binary').toString('base64');
global.atob = s => Buffer.from(String(s), 'base64').toString('binary');

const GH = require('../../js/ghchat.js');

(async () => {
  console.log('\n== 1. 配置 ==');
  ok('初始未就绪', GH.ready() === false);
  GH.saveCfg({ owner: 'tester', repo: 'chat', branch: 'main', token: 'tok', path: 'social' });
  ok('保存后就绪', GH.ready() === true);
  ok('路径默认 social', GH.cfg().path === 'social');

  console.log('\n== 2. 连接测试 ==');
  const t = await GH.test();
  ok('能连上并能写', t.ok && t.canWrite === true, t);

  console.log('\n== 3. 大厅收发 ==');
  const m1 = { id: 'm1', uid: 'uA', nick: '阿明', avatar: '🐱', text: '大家好', at: 1000 };
  let r = await GH.hallSend(m1);
  ok('发第一条', r.ok === true, r);
  const h1 = await GH.hallRead();
  ok('能读回', h1.msgs.length === 1 && h1.msgs[0].text === '大家好', h1.msgs);

  const m2 = { id: 'm2', uid: 'uB', nick: '小美', avatar: '🐰', text: '你好', at: 2000 };
  await GH.hallSend(m2);
  const h2 = await GH.hallRead();
  ok('两条都在', h2.msgs.length === 2, h2.msgs.length);

  console.log('\n== 4. 重复发同一条（幂等）==');
  r = await GH.hallSend(m1);
  ok('重复 id 被识别', r.dup === true, r);
  const h3 = await GH.hallRead();
  ok('没有变成 3 条', h3.msgs.length === 2, h3.msgs.length);

  console.log('\n== 5. 并发写入（关键）==');
  conflictNext = 5;   // 制造连续冲突
  const before = files.get('social/hall.json').content;
  const many = [];
  for (let i = 0; i < 6; i++) {
    many.push(GH.hallSend({
      id: 'c' + i, uid: 'u' + i, nick: 'N' + i, avatar: '🙂', text: '并发' + i, at: 3000 + i,
    }));
  }
  const rs = await Promise.all(many);
  ok('全部成功', rs.every(x => x.ok === true), rs.map(x => x.ok));
  const h4 = await GH.hallRead();
  const ids = new Set(h4.msgs.map(x => x.id));
  ok('6 条并发消息一条不丢', ['c0', 'c1', 'c2', 'c3', 'c4', 'c5'].every(id => ids.has(id)),
    h4.msgs.filter(x => String(x.id).startsWith('c')).map(x => x.id));
  ok('冲突确实发生过', conflictNext === 0 && putCount > 6, { putCount, conflictNext });

  console.log('\n== 6. 上限截断 ==');
  for (let i = 0; i < 12; i++) {
    await GH.mergeMsgs('big.json', Array.from({ length: 50 }, (_, j) => (
      { id: 'b' + i + '_' + j, uid: 'u', text: 'x', at: i * 100 + j })), 100);
  }
  const big = await GH.getJSON('big.json');
  ok('超过上限会被裁到 100', big.data.msgs.length === 100, big.data.msgs.length);
  ok('保留的是最新的', big.data.msgs[big.data.msgs.length - 1].id === 'b11_49',
    big.data.msgs[big.data.msgs.length - 1].id);

  console.log('\n== 7. 用户表（在线状态）==');
  await GH.userUpsert('uA', { nick: '阿明', avatar: '🐱' });
  await GH.userUpsert('uB', { nick: '小美', avatar: '🐰' });
  let users = await GH.usersRead();
  ok('两个用户都在', Object.keys(users).length === 2, Object.keys(users));
  ok('带上了 lastSeen', users.uA.lastSeen > 0, users.uA.lastSeen);
  await GH.userUpsert('uA', { avatar: '🦊' });
  users = await GH.usersRead();
  ok('部分更新保留昵称', users.uA.nick === '阿明' && users.uA.avatar === '🦊', users.uA);

  console.log('\n== 8. 私聊 ==');
  const d1 = { id: 'd1', uid: 'uA', nick: '阿明', avatar: '🐱', text: '认识一下', at: 5000 };
  await GH.dmSend('uA', 'uB', d1);
  await GH.dmIndexAdd('uA', 'uB');
  const dm = await GH.dmRead('uA', 'uB');
  ok('A→B 能看到', dm.msgs.length === 1, dm.msgs.length);
  const dmRev = await GH.dmRead('uB', 'uA');
  ok('B→A 读的是同一个文件', dmRev.msgs.length === 1, dmRev.msgs.length);
  ok('文件名与顺序无关', GH.dmKey('uA', 'uB') === GH.dmKey('uB', 'uA'), GH.dmKey('uA', 'uB'));

  const d2 = { id: 'd2', uid: 'uB', nick: '小美', avatar: '🐰', text: '好呀', at: 6000 };
  await GH.dmSend('uB', 'uA', d2);
  const dm2 = await GH.dmRead('uA', 'uB');
  ok('双向都在', dm2.msgs.length === 2, dm2.msgs.map(x => x.text));

  const idx = await GH.dmIndexRead();
  ok('私聊索引有这条', idx.length === 1 && idx[0].key === GH.dmKey('uA', 'uB'), idx);
  await GH.dmIndexAdd('uA', 'uB');
  const idx2 = await GH.dmIndexRead();
  ok('重复加不会变两条', idx2.length === 1, idx2.length);

  console.log('\n== 9. 图片 ==');
  const dataUrl = 'data:image/jpeg;base64,' + b64('FAKEIMAGE');
  const url = await GH.uploadImage(dataUrl, 'jpg');
  ok('返回可访问地址', /^https:\/\/raw\.githubusercontent\.com\/tester\/chat\/main\/social\/img\//.test(url), url);
  const imgPath = 'social/' + url.split('/social/')[1];
  ok('图片确实写进仓库', files.has(imgPath), [...files.keys()].filter(k => k.includes('img')));

  console.log('\n== 10. 权限不足要报错 ==');
  permPush = false;
  let caught = null;
  try { await GH.hallSend({ id: 'nope', uid: 'x', text: 'x', at: 1 }); }
  catch (e) { caught = e; }
  ok('没权限时抛出错误', !!caught && /not accessible|403/i.test(caught.message + caught.status),
    caught && (caught.message + '|' + caught.status));
  permPush = true;

  console.log('\n== 11. 工具函数 ==');
  const id1 = GH.uid16(), id2 = GH.uid16();
  ok('生成的 id 唯一', id1 !== id2, [id1, id2]);
  ok('id 可用于文件名', /^[a-z0-9-]+$/.test(id1), id1);
  ok('清洗控制字符', GH.clean('a\u0000b\u0007c') === 'abc', GH.clean('a\u0000b\u0007c'));
  ok('截断超长', GH.clean('x'.repeat(500), 10).length === 10);

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
