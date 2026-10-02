'use strict';
/*
 * 端到端：两个「用户」连真实公共 broker，互发消息，验证界面真的收到
 * （会访问网络；连不上就跳过，不算失败）
 *
 * 运行：node server/test/friends-live.test.js
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const tls = require('tls');
const crypto = require('crypto');

let pass = 0, fail = 0, skipped = false;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (fn()) return true; await wait(150); } return false; };

/* ================= 浏览器 WebSocket → Node tls ================= */
class NodeWS {
  constructor(url, proto) {
    const u = new URL(url);
    this.url = url; this.readyState = 0; this.binaryType = 'arraybuffer';
    this.onopen = this.onmessage = this.onclose = this.onerror = null;
    this._buf = Buffer.alloc(0); this._hs = false;
    this._sock = tls.connect({ host: u.hostname, port: +(u.port || 443), servername: u.hostname, rejectUnauthorized: false }, () => {
      const k = crypto.randomBytes(16).toString('base64');
      let r = 'GET ' + (u.pathname || '/') + ' HTTP/1.1\r\nHost: ' + u.hostname + ':' + u.port +
        '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ' + k +
        '\r\nSec-WebSocket-Version: 13\r\n';
      if (proto) r += 'Sec-WebSocket-Protocol: ' + proto + '\r\n';
      this._sock.write(r + '\r\n');
    });
    this._sock.on('data', d => this._onData(d));
    this._sock.on('error', e => { this.readyState = 3; this.onerror && this.onerror(e); });
    this._sock.on('close', () => { this.readyState = 3; this.onclose && this.onclose({}); });
  }
  _onData(d) {
    this._buf = Buffer.concat([this._buf, d]);
    if (!this._hs) {
      const i = this._buf.indexOf('\r\n\r\n'); if (i < 0) return;
      const head = this._buf.slice(0, i).toString();
      this._buf = this._buf.slice(i + 4);
      if (!/101/.test(head)) { this.readyState = 3; this.onerror && this.onerror(new Error('握手失败')); return; }
      this._hs = true; this.readyState = 1; this.onopen && this.onopen({});
    }
    while (this._buf.length >= 2 && this._hs) {
      const op = this._buf[0] & 0x0f;
      let len = this._buf[1] & 0x7f, off = 2;
      if (len === 126) { if (this._buf.length < 4) return; len = this._buf.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (this._buf.length < 10) return; len = Number(this._buf.readBigUInt64BE(2)); off = 10; }
      if (this._buf.length < off + len) return;
      const p = this._buf.slice(off, off + len);
      this._buf = this._buf.slice(off + len);
      if (op === 0x9) { this._send(p, 0xA); continue; }
      if (op === 0x8) { this.readyState = 3; this.onclose && this.onclose({}); continue; }
      if (op === 0x1 || op === 0x2) {
        const ab = p.buffer.slice(p.byteOffset, p.byteOffset + p.length);
        this.onmessage && this.onmessage({ data: ab });
      }
    }
  }
  _send(p, op) {
    op = op || 2;
    const m = crypto.randomBytes(4), len = p.length;
    let h;
    if (len < 126) h = Buffer.from([0x80 | op, 0x80 | len]);
    else if (len < 65536) { h = Buffer.alloc(4); h[0] = 0x80 | op; h[1] = 0x80 | 126; h.writeUInt16BE(len, 2); }
    else { h = Buffer.alloc(10); h[0] = 0x80 | op; h[1] = 0x80 | 127; h.writeBigUInt64BE(BigInt(len), 2); }
    const mm = Buffer.alloc(len);
    for (let i = 0; i < len; i++) mm[i] = p[i] ^ m[i % 4];
    try { this._sock.write(Buffer.concat([h, m, mm])); } catch (e) {}
  }
  send(d) { if (this.readyState !== 1) return; this._send(Buffer.isBuffer(d) ? d : Buffer.from(d), 2); }
  close() { this.readyState = 3; try { this._sock.end(); } catch (e) {} }
}

/* ================= 极简 DOM ================= */
function mkEl(tag) {
  const el = {
    tagName: (tag || 'div').toUpperCase(), id: '', _cls: new Set(), _ch: [], innerHTML: '',
    textContent: '', value: '', style: {}, dataset: {}, scrollTop: 0, scrollHeight: 0,
    clientHeight: 0, disabled: false, files: null, parentNode: null,
    classList: {
      add: (...c) => c.forEach(x => el._cls.add(x)),
      remove: (...c) => c.forEach(x => el._cls.delete(x)),
      contains: c => el._cls.has(c),
      toggle: (c, f) => { const on = f === undefined ? !el._cls.has(c) : !!f; on ? el._cls.add(c) : el._cls.delete(c); return on; },
    },
    get className() { return [...el._cls].join(' '); },
    set className(v) { el._cls = new Set(String(v).split(/\s+/).filter(Boolean)); },
    appendChild(c) { el._ch.push(c); c.parentNode = el; return c; },
    removeChild(c) { el._ch = el._ch.filter(x => x !== c); return c; },
    remove() { if (el.parentNode) el.parentNode.removeChild(el); },
    insertBefore(c) { el._ch.unshift(c); c.parentNode = el; return c; },
    querySelector(s) { return q1(el, s); },
    querySelectorAll(s) { return qa(el, s); },
    setAttribute() {}, getAttribute() { return null; },
    focus() {}, click() { el.onclick && el.onclick({ preventDefault() {} }); },
    addEventListener() {},
  };
  return el;
}
function q1(root, sel) {
  const m = String(sel).split(/[ >]/)[0].split(':')[0];
  if (m.startsWith('#')) return (root.__all && root.__all.get(m.slice(1))) || null;
  const cls = m.startsWith('.') ? m.slice(1) : null;
  const walk = n => { if (cls && n._cls.has(cls)) return n; for (const c of n._ch) { const r = walk(c); if (r) return r; } return null; };
  for (const c of root._ch) { const r = walk(c); if (r) return r; }
  return null;
}
function qa(root, sel) {
  const cls = String(sel).startsWith('.') ? String(sel).slice(1).split(/[ >]/)[0] : null;
  const out = [];
  const walk = n => { if (cls && n._cls.has(cls)) out.push(n); for (const c of n._ch) walk(c); };
  for (const c of root._ch) walk(c);
  return out;
}

function makeUser(tag) {
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'friends.html'), 'utf8');
  const ALL = new Map();
  for (const m of html.matchAll(/id="([\w-]+)"/g)) { const e = mkEl(); e.id = m[1]; ALL.set(m[1], e); }
  const body = mkEl('body');
  body.__all = ALL;
  body._ch = [...ALL.values()];
  const doc = {
    body, hidden: false, title: '',
    createElement: mkEl,
    querySelector: s => q1(body, s),
    querySelectorAll: s => qa(body, s),
    addEventListener: (ev, fn) => { if (ev === 'DOMContentLoaded') doc._ready = fn; },
  };
  const mem = {};
  const sb = {
    console, document: doc,
    location: { search: '?room=TESTRM', hostname: 'x.github.io', origin: 'https://x' },
    localStorage: {
      getItem: k => (k in mem ? mem[k] : null),
      setItem: (k, v) => { mem[k] = String(v); },
      removeItem: k => { delete mem[k]; },
    },
    navigator: { clipboard: { writeText: async () => {} } },
    WebSocket: NodeWS,
    TextEncoder, TextDecoder, DataView, Uint8Array, BigInt, Promise, Date, Math, JSON,
    Object, Array, String, Number, Boolean, Set, Map, URLSearchParams, Error,
    setTimeout, clearTimeout, setInterval, clearInterval,
    Image: function () { this.onload = null; }, FileReader: function () {},
    addEventListener() {},
  };
  sb.window = sb; sb.self = sb; sb.globalThis = sb;
  vm.createContext(sb);
  for (const src of ['js/mqtt.js', 'js/friends.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', src), 'utf8'), sb, { filename: src });
  }
  // 预置身份
  mem['yh_uid'] = JSON.stringify('u' + tag + 'xxxxxx');
  mem['yh_me'] = JSON.stringify({ nick: '用户' + tag, avatar: tag === 'A' ? '🐱' : '🐰' });
  return { sb, ALL, doc, mem, tag };
}

(async () => {
  const A = makeUser('A');
  const B = makeUser('B');

  console.log('\n== 启动两个客户端（连真实 broker）==');
  A.doc._ready();
  B.doc._ready();

  const aUp = await waitFor(() => A.sb.__mqUp, 15000);
  // friends.js 没暴露状态，改从 DOM 判断
  const aOk = await waitFor(() => A.ALL.get('liveTxt').textContent === '已连接', 15000);
  const bOk = await waitFor(() => B.ALL.get('liveTxt').textContent === '已连接', 15000);
  ok('A 客户端连上', aOk, A.ALL.get('liveTxt').textContent);
  ok('B 客户端连上', bOk, B.ALL.get('liveTxt').textContent);
  if (!aOk || !bOk) { skipped = true; console.log('\n（网络连不上，跳过后续 — 不算失败）\n'); process.exit(fail ? 1 : 0); }

  console.log('\n== 互相能看到在线 ==');
  await wait(2500);
  const aSees = await waitFor(() => A.ALL.get('onlineTxt').textContent.indexOf('人在线') >= 0, 12000);
  ok('A 看到有人在线', aSees, A.ALL.get('onlineTxt').textContent);

  console.log('\n== A 发消息，B 能否收到 ==');
  A.ALL.get('input').value = '你好，我是A';
  A.ALL.get('btnSend').onclick();
  const bGot = await waitFor(() => /你好，我是A/.test(B.ALL.get('flow').innerHTML) ||
    B.ALL.get('flow')._ch.some(x => /你好，我是A/.test(x.innerHTML || '')), 12000);
  ok('B 收到 A 的消息', bGot, B.ALL.get('flow').innerHTML.slice(0, 120));

  console.log('\n== B 回复，A 能否收到 ==');
  B.ALL.get('input').value = '收到啦，我是B';
  B.ALL.get('btnSend').onclick();
  const aGot = await waitFor(() => A.ALL.get('flow')._ch.some(x => /收到啦/.test(x.innerHTML || '')), 12000);
  ok('A 收到 B 的回复', aGot);

  console.log('\n== 中文 / 表情 ==');
  A.ALL.get('input').value = '卤味店的猪蹄🐷还有吗';
  A.ALL.get('btnSend').onclick();
  const cnOk = await waitFor(() => B.ALL.get('flow')._ch.some(x => /猪蹄🐷还有吗/.test(x.innerHTML || '')), 12000);
  ok('表情和中文完整送达', cnOk);

  console.log('\n== 敏感内容拦截 ==');
  B.ALL.get('input').value = '快来加微信';
  B.ALL.get('btnSend').onclick();
  await wait(400);
  ok('含敏感词的消息没发出去', !B.ALL.get('flow')._ch.some(x => /加微信/.test(x.innerHTML || '')));

  console.log('\n== 本机历史保存 ==');
  ok('历史已写入 localStorage', !!A.mem['yh_hist_TESTRM'], Object.keys(A.mem).join(','));

  A.sb.__stop && A.sb.__stop();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
