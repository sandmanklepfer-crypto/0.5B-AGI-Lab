'use strict';
/*
 * 真实验证 js/mqtt.js 能否连上公共 broker 并双向收发
 * （用 Node 的 tls 模拟浏览器的 WebSocket，跑真实 MQTT 协议）
 *
 * 运行：node server/test/mqtt.test.js
 */
const tls = require('tls');
const crypto = require('crypto');
const path = require('path');

let pass = 0, fail = 0;
const ok = (n, c, extra) => {
  if (c) { pass++; console.log('  ✅ ' + n); }
  else { fail++; console.log('  ❌ ' + n + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

/* ---------- 用 tls 包装成浏览器风格的 WebSocket ---------- */
class NodeWS {
  constructor(url, proto) {
    const u = new URL(url);
    this.url = url;
    this.readyState = 0;
    this.binaryType = 'arraybuffer';
    this.onopen = this.onmessage = this.onclose = this.onerror = null;
    this._buf = Buffer.alloc(0);
    this._sock = tls.connect({ host: u.hostname, port: Number(u.port || 443), servername: u.hostname, rejectUnauthorized: false }, () => {
      const key = crypto.randomBytes(16).toString('base64');
      let req = 'GET ' + (u.pathname || '/') + ' HTTP/1.1\r\nHost: ' + u.hostname + ':' + u.port +
        '\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ' + key +
        '\r\nSec-WebSocket-Version: 13\r\n';
      if (proto) req += 'Sec-WebSocket-Protocol: ' + proto + '\r\n';
      req += '\r\n';
      this._sock.write(req);
    });
    this._handshaked = false;
    this._sock.on('data', d => this._onData(d));
    this._sock.on('error', e => { this.readyState = 3; this.onerror && this.onerror(e); });
    this._sock.on('close', () => { this.readyState = 3; this.onclose && this.onclose({}); });
  }
  _onData(d) {
    this._buf = Buffer.concat([this._buf, d]);
    if (!this._handshaked) {
      const i = this._buf.indexOf('\r\n\r\n');
      if (i < 0) return;
      const head = this._buf.slice(0, i).toString();
      this._buf = this._buf.slice(i + 4);
      if (!/101/.test(head)) { this.readyState = 3; this.onerror && this.onerror(new Error('握手失败')); return; }
      this._handshaked = true;
      this.readyState = 1;
      this.onopen && this.onopen({});
    }
    // 拆帧
    while (this._buf.length >= 2 && this._handshaked) {
      const b0 = this._buf[0], b1 = this._buf[1];
      const op = b0 & 0x0f;
      let len = b1 & 0x7f, off = 2;
      if (len === 126) { if (this._buf.length < 4) return; len = this._buf.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (this._buf.length < 10) return; len = Number(this._buf.readBigUInt64BE(2)); off = 10; }
      if (this._buf.length < off + len) return;
      const payload = this._buf.slice(off, off + len);
      this._buf = this._buf.slice(off + len);
      if (op === 0x9) { this._send(payload, 0xA); continue; }
      if (op === 0x8) { this.readyState = 3; this.onclose && this.onclose({}); continue; }
      if (op === 0x1 || op === 0x2) {
        const ab = payload.buffer.slice(payload.byteOffset, payload.byteOffset + payload.length);
        this.onmessage && this.onmessage({ data: ab });
      }
    }
  }
  _send(payload, opcode) {
    opcode = opcode || 2;
    const mask = crypto.randomBytes(4);
    const len = payload.length;
    let head;
    if (len < 126) head = Buffer.from([0x80 | opcode, 0x80 | len]);
    else if (len < 65536) { head = Buffer.alloc(4); head[0] = 0x80 | opcode; head[1] = 0x80 | 126; head.writeUInt16BE(len, 2); }
    else { head = Buffer.alloc(10); head[0] = 0x80 | opcode; head[1] = 0x80 | 127; head.writeBigUInt64BE(BigInt(len), 2); }
    const masked = Buffer.alloc(len);
    for (let i = 0; i < len; i++) masked[i] = payload[i] ^ mask[i % 4];
    try { this._sock.write(Buffer.concat([head, mask, masked])); } catch (e) {}
  }
  send(data) {
    if (this.readyState !== 1) return;
    const buf = Buffer.isBuffer(data) ? data : Buffer.from(data);
    this._send(buf, 2);
  }
  close() { this.readyState = 3; try { this._sock.end(); } catch (e) {} }
}

/* ---------- 浏览器环境垫片 ---------- */
const sandboxSelf = {
  crypto: { getRandomValues: a => { crypto.randomFillSync(a); return a; } },
  WebSocket: NodeWS,
  TextEncoder, TextDecoder, DataView, Uint8Array, BigInt, console, setTimeout, clearTimeout, setInterval, clearInterval,
};
sandboxSelf.self = sandboxSelf;

const vm = require('vm');
vm.createContext(sandboxSelf);
vm.runInContext(require('fs').readFileSync(path.join(__dirname, '..', '..', 'js', 'mqtt.js'), 'utf8'), sandboxSelf, { filename: 'mqtt.js' });
const MiniMqtt = sandboxSelf.MiniMqtt;

const wait = ms => new Promise(r => setTimeout(r, ms));
const waitFor = async (fn, ms) => { const t = Date.now(); while (Date.now() - t < ms) { if (fn()) return true; await wait(120); } return false; };

(async () => {
  console.log('\n== 1. 模块导出 ==');
  ok('MiniMqtt 已挂载', typeof MiniMqtt === 'object' && typeof MiniMqtt.createClient === 'function');
  ok('内置多个 broker 备用', Array.isArray(MiniMqtt.BROKERS) && MiniMqtt.BROKERS.length >= 2, MiniMqtt.BROKERS);

  const topic = 'zhz/test/' + crypto.randomBytes(4).toString('hex');

  console.log('\n== 2. 连上公共 broker（免注册/免 Token）==');
  const A = MiniMqtt.createClient({ clientId: 'testA' });
  let aUp = false, aErr = null;
  A.on('connect', () => { aUp = true; });
  A.on('error', e => { aErr = e.message; });
  const connected = await waitFor(() => aUp, 20000);
  ok('成功连上', connected, { err: aErr, broker: A.broker });
  if (!connected) { A.end(); console.log('\n（连不上网络，跳过后续）\n'); process.exit(fail ? 1 : 0); }
  console.log('     broker = ' + A.broker);

  console.log('\n== 3. 订阅 + 发布 + 收到（双向）==');
  const gotA = [];
  A.on('message', (t, m) => gotA.push({ t, m }));
  A.subscribe(topic);
  await wait(800);   // 等 SUBACK

  A.publish(topic, '你好，这是A发的');
  const okA = await waitFor(() => gotA.length > 0, 8000);
  ok('A 收到自己的消息', okA && gotA[0].m === '你好，这是A发的', gotA);
  ok('topic 正确', gotA[0] && gotA[0].t === topic, gotA[0] && gotA[0].t);

  console.log('\n== 4. 两个客户端互发（真双向）==');
  const B = MiniMqtt.createClient({ clientId: 'testB' });
  let bUp = false;
  B.on('connect', () => { bUp = true; });
  await waitFor(() => bUp, 20000);
  ok('B 也连上', bUp, B.broker);
  const gotB = [];
  B.on('message', (t, m) => gotB.push(m));
  B.subscribe(topic);
  await wait(900);

  A.publish(topic, 'A对B说');
  await waitFor(() => gotB.length > 0, 8000);
  ok('B 收到 A 的消息', gotB.includes('A对B说'), gotB);

  B.publish(topic, 'B回A');
  await waitFor(() => gotA.filter(x => x.m === 'B回A').length > 0, 8000);
  ok('A 收到 B 的回复', gotA.some(x => x.m === 'B回A'), gotA.map(x => x.m));

  console.log('\n== 5. 中文/表情/长文本 ==');
  const cn = '卤味店的猪蹄🐷还有吗？—— 测试「引号」和换行\n第二行';
  A.publish(topic, cn);
  await waitFor(() => gotB.includes(cn), 8000);
  ok('中文+表情+换行 完整送达', gotB.includes(cn), gotB[gotB.length - 1]);

  const long = 'x'.repeat(3000);
  A.publish(topic, long);
  await waitFor(() => gotB.includes(long), 10000);
  ok('3KB 长文本送达', gotB.includes(long), (gotB[gotB.length - 1] || '').length);

  console.log('\n== 6. JSON 消息（聊天消息体）==');
  const msg = JSON.stringify({ id: 'm1', uid: 'uA', nick: '阿明', text: '在吗', at: 123, img: '' });
  A.publish(topic, msg);
  await waitFor(() => gotB.some(x => x.startsWith('{')), 8000);
  const parsed = JSON.parse(gotB.find(x => x.startsWith('{')));
  ok('JSON 能正确解析', parsed.nick === '阿明' && parsed.text === '在吗', parsed);

  console.log('\n== 7. 断开重连 ==');
  const before = A.connected;
  ok('连接状态可查', before === true);
  A.end();
  // end() 之后状态更新是异步的，轮询等待，避免时序抖动
  const down = await waitFor(() => A.connected === false, 4000);
  ok('end() 后标记为断开', down);

  B.end();
  await wait(300);

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
