'use strict';
/*
 * 真跑一遍 friends.js 的启动流程（DOM 模拟）
 *
 * 目的：验证「在该用户手机上打开」会发生什么 ——
 *   1) 卤味后台已填过 Token 时，会不会自动沿用
 *   2) 还会不会弹出 Token 填写面板（这是之前的 bug）
 *   3) 设完昵称后有没有立刻拉数据（之前会空 6 秒）
 *
 * 运行：node server/test/friends-dom.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let pass = 0, fail = 0;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

/* ================= 极简 DOM ================= */
function makeEl(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(),
    _cls: new Set(), _children: [], _attrs: {},
    innerHTML: '', textContent: '', value: '',
    style: {}, dataset: {}, scrollTop: 0, scrollHeight: 0,
    disabled: false, files: null, type: '', placeholder: '', title: '',
    classList: {
      add: (...c) => c.forEach(x => el._cls.add(x)),
      remove: (...c) => c.forEach(x => el._cls.delete(x)),
      contains: c => el._cls.has(c),
      toggle: (c, f) => { const on = f === undefined ? !el._cls.has(c) : !!f; on ? el._cls.add(c) : el._cls.delete(c); return on; },
    },
    get className() { return [...el._cls].join(' '); },
    set className(v) { el._cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    appendChild(c) { el._children.push(c); c.parentNode = el; return c; },
    removeChild(c) { el._children = el._children.filter(x => x !== c); return c; },
    remove() { if (el.parentNode) el.parentNode.removeChild(el); },
    querySelector(sel) { return findIn(el, sel); },
    querySelectorAll(sel) { return findAllIn(el, sel); },
    insertBefore(c) { el._children.unshift(c); return c; },
    setAttribute(k, v) { el._attrs[k] = v; },
    getAttribute(k) { return el._attrs[k]; },
    focus() {}, click() { if (el.onclick) el.onclick({ preventDefault() {} }); },
    addEventListener() {},
  };
  return el;
}

// 从 HTML 里解析出顶层 id
const html = fs.readFileSync(path.join(__dirname, '..', '..', 'friends.html'), 'utf8');
const IDS = [...html.matchAll(/id="([A-Za-z0-9_-]+)"/g)].map(m => m[1]);
const registry = new Map();
IDS.forEach(id => { const e = makeEl('div'); e.id = id; registry.set(id, e); });

// 默认隐藏的（HTML 里没有 on 的）—— 模拟浏览器初始状态
const ON_BY_DEFAULT = new Set(
  [...html.matchAll(/class="(?:mask|sheet)( on)?"[^>]*id="([A-Za-z0-9_-]+)"/g)]
    .filter(m => m[1]).map(m => m[2])
);
ON_BY_DEFAULT.forEach(id => { const e = registry.get(id); if (e) e.classList.add('on'); });

function findIn(root, sel) {
  if (!sel) return null;
  // 只支持 '#id' 和 '.class' 的最简形式
  const first = sel.split(/[ >]/)[0].split(':')[0];
  if (first.startsWith('#')) return registry.get(first.slice(1)) || null;
  // 类选择器：在 root 子树里找
  const cls = first.startsWith('.') ? first.slice(1) : null;
  if (!cls) return null;
  const walk = n => {
    if (n._cls && n._cls.has(cls)) return n;
    for (const c of n._children || []) { const r = walk(c); if (r) return r; }
    return null;
  };
  for (const c of root._children || []) { const r = walk(c); if (r) return r; }
  return null;
}
function findAllIn(root, sel) {
  const cls = sel.startsWith('.') ? sel.slice(1) : null;
  const out = [];
  const walk = n => {
    if (cls && n._cls && n._cls.has(cls)) out.push(n);
    for (const c of n._children || []) walk(c);
  };
  for (const c of root._children || []) walk(c);
  return out;
}

const document = {
  body: makeEl('body'),
  createElement: makeEl,
  querySelector: s => findIn(document.body, s),
  querySelectorAll: s => findAllIn(document.body, s),
  addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') document._ready = fn; },
  hidden: false,
};
// 让 document.body 能查到全局注册的元素
document.body._children = [...registry.values()];

/* ================= 其他浏览器 API ================= */
const mem = {};
const localStorage = {
  getItem: k => (k in mem ? mem[k] : null),
  setItem: (k, v) => { mem[k] = String(v); },
  removeItem: k => { delete mem[k]; },
  get length() { return Object.keys(mem).length; },
};

/* ================= 伪造 GitHub API ================= */
const files = new Map();
let putN = 0;
const b64 = s => Buffer.from(String(s), 'utf8').toString('base64');
global.fetch = async (url, opts) => {
  opts = opts || {};
  const method = (opts.method || 'GET').toUpperCase();
  const p = new URL(url).pathname;
  const J = (code, obj) => ({ ok: code < 400, status: code, text: async () => JSON.stringify(obj) });
  if (p === '/user') return J(200, { login: 'sandmanklepfer-crypto' });
  if (/^\/repos\/[^/]+\/[^/]+$/.test(p)) return J(200, { full_name: 'x/y', private: false, permissions: { push: true } });
  const m = p.match(/\/contents\/(.+)$/);
  if (!m) return J(404, { message: 'Not Found' });
  const rel = decodeURIComponent(m[1]);
  if (method === 'GET') {
    const f = files.get(rel);
    if (!f) return J(404, { message: 'Not Found' });
    return J(200, { sha: f.sha, content: b64(f.content), encoding: 'base64' });
  }
  if (method === 'PUT') {
    putN++;
    const body = JSON.parse(opts.body || '{}');
    const content = Buffer.from(body.content, 'base64').toString('utf8');
    files.set(rel, { content, sha: 's' + putN });
    return J(200, { content: { sha: 's' + putN } });
  }
  return J(405, {});
};

/* ================= 组装沙箱 ================= */
const sandbox = {
  console, localStorage, fetch: global.fetch,
  document, location: { search: '', hostname: 'sandmanklepfer-crypto.github.io', origin: 'https://x' },
  navigator: { clipboard: { writeText: async () => {} } },
  setTimeout, clearTimeout, setInterval: () => 0, clearInterval: () => {},
  Promise, Date, Math, JSON, Object, Array, String, Number, Boolean, Set, Map, URLSearchParams,
  btoa: s => Buffer.from(String(s), 'binary').toString('base64'),
  atob: s => Buffer.from(String(s), 'base64').toString('binary'),
  Image: function () { this.onload = null; },
  FileReader: function () {},
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

/* ================= 模拟"用户手机"：卤味后台已填过 ================= */
mem['lh_gh'] = JSON.stringify({
  owner: 'sandmanklepfer-crypto', repo: '0.5B-AGI-Lab',
  branch: 'gh-pages', token: 'github_pat_ABC1234567890', path: '',
});
mem['lh_admin_ok'] = 'true';

(async () => {
  console.log('\n== 场景：用户手机上（卤味后台已填过 Token）打开聊天页 ==');

  // 按 HTML 顺序加载脚本
  const order = [...html.matchAll(/<script src="([^"]+)"><\/script>/g)].map(m => m[1]);
  ok('脚本加载顺序正确', order.length === 2 && order[0].includes('ghchat') && order[1].includes('friends'), order);

  for (const src of order) {
    const code = fs.readFileSync(path.join(__dirname, '..', '..', src), 'utf8');
    vm.runInContext(code, sandbox, { filename: src });
  }

  ok('ghchat 已挂载', typeof sandbox.GHChat === 'object');
  ok('friends 已执行', typeof document._ready === 'function');

  const GH = sandbox.GHChat;

  console.log('\n-- 配置继承 --');
  ok('自动找到卤味后台的配置', GH.hasLhCfg() === true);
  const c = GH.cfg();
  ok('仓库沿用卤味的', c.owner === 'sandmanklepfer-crypto' && c.repo === '0.5B-AGI-Lab', c.owner + '/' + c.repo);
  ok('Token 自动借用', c.token === 'github_pat_ABC1234567890', c.token && c.token.slice(0, 10));
  ok('判定为可发言', GH.canWrite() === true);
  ok('标记来源是卤味后台', c._fromLh === true);

  console.log('\n-- 关键：Token 面板不该弹出来 --');
  const sGh = registry.get('sGh');
  ok('Token 填写面板是关着的', !sGh.classList.contains('on'), [...sGh._cls]);
  const mask = registry.get('mask');
  ok('遮罩层默认关着', !mask.classList.contains('on'), [...mask._cls]);

  console.log('\n-- 跑启动流程 --');
  await document._ready();
  await new Promise(r => setTimeout(r, 120));

  const sMe = registry.get('sMe');
  ok('第一次进入：弹出「起昵称」面板', sMe.classList.contains('on'), [...sMe._cls]);
  ok('没有误弹 Token 面板', !sGh.classList.contains('on'));

  console.log('\n-- 起个昵称，看会不会立刻拉数据 --');
  registry.get('nickIn').value = '测试用户';
  await registry.get('meGo').onclick();
  await new Promise(r => setTimeout(r, 250));

  const bar = registry.get('connbar');
  ok('连接状态条显示已连上', /已连上/.test(bar.innerHTML), bar.innerHTML.slice(0, 60));
  ok('状态条里提到复用卤味令牌', /卤味后台/.test(bar.innerHTML), bar.innerHTML.slice(0, 80));

  const uid = JSON.parse(mem['yh_uid'] || '""');
  ok('已写入 users.json（心跳生效）', files.has('social/users.json'),
    [...files.keys()]);
  const users = JSON.parse(files.get('social/users.json').content).users;
  ok('users.json 里有这个用户且带 lastSeen', !!users[String(uid).replace(/[^\w-]/g, '')] &&
    users[String(uid).replace(/[^\w-]/g, '')].lastSeen > 0, Object.keys(users));

  console.log('\n-- 连接测试按钮 --');
  const t = await GH.test();
  ok('测试连接通过', t.ok && t.canWrite === true, t);

  console.log('\n-- 大厅发一条 --');
  const before = putN;
  registry.get('hallIn').value = '大家好';
  await registry.get('hallSend').onclick();
  await new Promise(r => setTimeout(r, 200));
  ok('调用写接口了', putN > before, { before, putN });
  ok('hall.json 已写入', files.has('social/hall.json'));
  const hall = JSON.parse(files.get('social/hall.json').content).msgs;
  ok('大厅里有这条消息', hall.length >= 1 && hall[hall.length - 1].text === '大家好',
    hall.map(x => x.text));

  console.log('\n== 对比场景：全新设备（没有卤味配置）==');
  delete mem['lh_gh'];
  delete mem['yh_gh'];
  delete mem['yh_me'];
  const GH2 = sandbox.GHChat;
  ok('不再借用', GH2.hasLhCfg() === false);
  ok('判定为只读（不能发言）', GH2.canWrite() === false);
  ok('但仍可读取（能看大厅）', GH2.ready() === true);
  ok('默认仓库已预填，用户少填字', GH2.cfg().owner === 'sandmanklepfer-crypto', GH2.cfg().owner);

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
