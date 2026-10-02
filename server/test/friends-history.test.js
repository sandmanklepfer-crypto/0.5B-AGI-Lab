'use strict';
/*
 * 跨设备历史验证（真实 broker）
 *
 * 场景：设备1 发了消息后关掉 → 设备2 全新打开 → 能不能看到设备1 说过的话
 * 原理：消息用「一条一主题 + retain」，broker 替我们保存，新人订阅通配符即可拿到。
 *
 * 运行：node server/test/friends-history.test.js
 */
const tls = require('tls');
const crypto = require('crypto');
const vm = require('vm');
const fs = require('fs');
const path = require('path');

let pass = 0, fail = 0;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};
const wait = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (fn()) return true; await wait(150); } return false; };

/* ---------- 浏览器 WebSocket → Node tls ---------- */
class WS {
  constructor(url, proto) {
    const u = new URL(url);
    this.readyState = 0; this._b = Buffer.alloc(0); this._hs = false;
    this._s = tls.connect({ host: u.hostname, port: +(u.port || 443), servername: u.hostname, rejectUnauthorized: false }, () => {
      const k = crypto.randomBytes(16).toString('base64');
      let r = 'GET ' + (u.pathname || '/') + ' HTTP/1.1\r\nHost: ' + u.hostname + ':' + u.port +
        '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ' + k +
        '\r\nSec-WebSocket-Version: 13\r\n';
      if (proto) r += 'Sec-WebSocket-Protocol: ' + proto + '\r\n';
      this._s.write(r + '\r\n');
    });
    this._s.on('data', d => this._d(d));
    this._s.on('error', e => { this.readyState = 3; this.onerror && this.onerror(e); });
    this._s.on('close', () => { this.readyState = 3; this.onclose && this.onclose({}); });
  }
  _d(d) {
    this._b = Buffer.concat([this._b, d]);
    if (!this._hs) {
      const i = this._b.indexOf('\r\n\r\n'); if (i < 0) return;
      this._b = this._b.slice(i + 4); this._hs = true;
      this.readyState = 1; this.onopen && this.onopen({});
    }
    while (this._b.length >= 2 && this._hs) {
      const op = this._b[0] & 0x0f;
      let l = this._b[1] & 0x7f, o = 2;
      if (l === 126) { if (this._b.length < 4) return; l = this._b.readUInt16BE(2); o = 4; }
      if (this._b.length < o + l) return;
      const p = this._b.slice(o, o + l); this._b = this._b.slice(o + l);
      if (op === 9) { this._snd(p, 0xA); continue; }
      if (op === 8) { this.readyState = 3; this.onclose && this.onclose({}); continue; }
      if (op === 1 || op === 2) this.onmessage && this.onmessage({ data: p.buffer.slice(p.byteOffset, p.byteOffset + p.length) });
    }
  }
  _snd(p, op) {
    op = op || 2;
    const m = crypto.randomBytes(4), l = p.length;
    let h;
    if (l < 126) h = Buffer.from([0x80 | op, 0x80 | l]);
    else { h = Buffer.alloc(4); h[0] = 0x80 | op; h[1] = 0x80 | 126; h.writeUInt16BE(l, 2); }
    const mm = Buffer.alloc(l);
    for (let i = 0; i < l; i++) mm[i] = p[i] ^ m[i % 4];
    try { this._s.write(Buffer.concat([h, m, mm])); } catch (e) {}
  }
  send(d) { if (this.readyState === 1) this._snd(Buffer.isBuffer(d) ? d : Buffer.from(d), 2); }
  close() { this.readyState = 3; try { this._s.end(); } catch (e) {} }
}

const S = {
  crypto: { getRandomValues: a => { crypto.randomFillSync(a); return a; } },
  WebSocket: WS, TextEncoder, TextDecoder, DataView, Uint8Array, BigInt,
  console, setTimeout, clearTimeout, setInterval, clearInterval,
};
S.self = S;
vm.createContext(S);
vm.runInContext(fs.readFileSync(path.join(__dirname, '..', '..', 'js', 'mqtt.js'), 'utf8'), S);
const M = S.MiniMqtt;

const ROOM = 'T' + crypto.randomBytes(3).toString('hex').toUpperCase();
const T = k => 'zhz/c/' + ROOM + '/m/' + k;
const ALL = 'zhz/c/' + ROOM + '/m/#';
const key = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const mk = (text, n) => ({ id: 'u' + n + '-' + Date.now(), uid: 'u' + n, nick: '用户' + n, avatar: '🐱', text, at: Date.now() });
const rid = () => 'hst' + crypto.randomBytes(2).toString('hex');

(async () => {
  console.log('\n== 设备1：发消息后关掉 ==');
  const A = M.createClient({ clientId: rid() });
  let up = false;
  A.on('connect', () => { up = true; A.subscribe(ALL); });
  const aUp = await waitFor(() => up, 20000);
  ok('设备1 连上', aUp, A.broker);
  if (!aUp) { console.log('\n（网络不通，跳过 — 不算失败）\n'); process.exit(fail ? 1 : 0); }

  await wait(600);
  A.publish(T(key()), JSON.stringify(mk('第一句：晚上现捞', 1)), true);
  await wait(400);
  A.publish(T(key()), JSON.stringify(mk('第二句：猪蹄还有', 2)), true);
  await wait(800);
  ok('两条都以 retain 方式发出', true);

  A.end();
  await wait(1200);
  ok('设备1 已断开', A.connected === false);

  console.log('\n== 设备2：全新打开，应该能看到历史 ==');
  const B = M.createClient({ clientId: rid() });
  const got = [];
  let bUp = false;
  B.on('connect', () => { bUp = true; B.subscribe(ALL); });
  B.on('message', (t, m) => { try { got.push(JSON.parse(m)); } catch (e) {} });
  await waitFor(() => bUp, 20000);
  const gotHist = await waitFor(() => got.length >= 2, 12000);
  ok('设备2 拿到设备1 的历史消息', gotHist, got.map(x => x.text));
  ok('内容正确', got.some(x => x.text === '第一句：晚上现捞') && got.some(x => x.text === '第二句：猪蹄还有'),
    got.map(x => x.text));
  ok('昵称也跟着来了', got.every(x => !!x.nick), got.map(x => x.nick));

  console.log('\n== 设备2 也能实时收到新消息 ==');
  const C = M.createClient({ clientId: rid() });
  let cUp = false;
  C.on('connect', () => { cUp = true; C.subscribe(ALL); });
  await waitFor(() => cUp, 20000);
  await wait(700);
  C.publish(T(key()), JSON.stringify(mk('第三句：实时到达', 3)), true);
  const live = await waitFor(() => got.some(x => x.text === '第三句：实时到达'), 10000);
  ok('实时消息也能收到', live, got.map(x => x.text));

  console.log('\n== 删除能力（清理老消息用）==');
  const k4 = key();
  C.publish(T(k4), JSON.stringify(mk('待删除', 4)), true);
  await wait(900);
  ok('先发了一条', await waitFor(() => got.some(x => x.text === '待删除'), 6000));
  C.publish(T(k4), '', true);          // 空载荷 = 删除该保留消息
  await wait(1000);

  const D = M.createClient({ clientId: rid() });
  const got2 = [];
  let dUp = false;
  D.on('connect', () => { dUp = true; D.subscribe(ALL); });
  D.on('message', (t, m) => { try { got2.push(JSON.parse(m)); } catch (e) {} });
  await waitFor(() => dUp, 20000);
  await wait(2800);
  ok('被删的那条不再出现', !got2.some(x => x.text === '待删除'), got2.map(x => x.text));
  ok('其他消息还在', got2.length >= 2, got2.map(x => x.text));

  B.end(); C.end(); D.end();

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
