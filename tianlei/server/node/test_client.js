/* 联机后端自测客户端（零依赖）
 * 用法: node test_client.js [名字] [秒数]
 */
'use strict';
const net = require('net');
const crypto = require('crypto');

const NAME = process.argv[2] || '测试者';
const SECONDS = parseInt(process.argv[3] || '3', 10);
const HOST = process.env.HOST || '127.0.0.1';
const PORT = parseInt(process.env.PORT || '8787', 10);

const key = crypto.randomBytes(16).toString('base64');
const sock = net.connect(PORT, HOST, () => {
  sock.write(
    `GET /ws?name=${encodeURIComponent(NAME)} HTTP/1.1\r\n` +
    `Host: ${HOST}:${PORT}\r\n` +
    `Upgrade: websocket\r\nConnection: Upgrade\r\n` +
    `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`
  );
});

let handshaken = false;
let buf = Buffer.alloc(0);

function send(obj) {
  const payload = Buffer.from(JSON.stringify(obj), 'utf8');
  const mask = crypto.randomBytes(4);
  const len = payload.length;
  let header;
  if (len < 126) { header = Buffer.alloc(2); header[1] = 0x80 | len; }
  else { header = Buffer.alloc(4); header[1] = 0x80 | 126; header.writeUInt16BE(len, 2); }
  header[0] = 0x81;
  const masked = Buffer.from(payload);
  for (let i = 0; i < masked.length; i++) masked[i] ^= mask[i % 4];
  sock.write(Buffer.concat([header, mask, masked]));
}

sock.on('data', chunk => {
  buf = Buffer.concat([buf, chunk]);
  if (!handshaken) {
    const i = buf.indexOf('\r\n\r\n');
    if (i === -1) return;
    console.log('[握手]', buf.slice(0, buf.indexOf('\r\n')).toString());
    buf = buf.slice(i + 4);
    handshaken = true;
    // 连上后先报到 + 持续上报位置
    let step = 0;
    const timer = setInterval(() => {
      step++;
      send({ t: 'state', x: 600 + step * 20, y: 900, dir: 1, state: 'run', hp: 100, maxHp: 100, level: 1, scene: 'world' });
    }, 100);
    setTimeout(() => { clearInterval(timer); send({ t: 'chat', text: '大家好，我是' + NAME }); }, 500);
    setTimeout(() => { sock.end(); process.exit(0); }, SECONDS * 1000);
  }
  // 解帧
  while (buf.length >= 2) {
    const b1 = buf[1];
    let len = b1 & 0x7f, off = 2;
    if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
    else if (len === 127) { if (buf.length < 10) return; len = Number(buf.readBigUInt64BE(2)); off = 10; }
    if (buf.length < off + len) return;
    const payload = buf.slice(off, off + len);
    buf = buf.slice(off + len);
    if ((buf[0] || 0) & 0x0f) { /* noop */ }
    try {
      const msg = JSON.parse(payload.toString('utf8'));
      if (msg.t === 'players' || msg.t === 'monsters') continue; // 太吵，跳过
      console.log('[收到]', JSON.stringify(msg).slice(0, 200));
    } catch (e) { /* ignore */ }
  }
});

sock.on('close', () => process.exit(0));
sock.on('error', e => { console.error('错误:', e.message); process.exit(1); });
