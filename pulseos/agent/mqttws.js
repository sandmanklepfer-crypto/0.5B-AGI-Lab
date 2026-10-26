#!/usr/bin/env node
/* ==========================================================================
 *  mqttws —— 零依赖「MQTT over WebSocket(TLS)」客户端（沙箱侧用）
 *  --------------------------------------------------------------------------
 *  为什么不用裸 TCP 1883：实测沙箱到公网 broker 的 1883 会在 TCP 连上后被掐断
 *  （连 paho 都连不上）；而 wss://…:8084 可用（TLS1.3 + WS 101 + 子协议 mqtt）。
 *  WSS 端口最像 HTTPS，最不容易被防火墙拦。手机端 WebView 用的也是 WSS，天然一致。
 *
 *  用法：
 *    const { MqttWs } = require('./mqttws');
 *    const c = new MqttWs('wss://broker.emqx.io:8084/mqtt', { clientId:'x' });
 *    await c.connect();
 *    c.onMessage((topic,payload)=>...);
 *    c.sub('a/b'); c.pub('a/c','hi', true);
 * ========================================================================== */
'use strict';
const tls = require('tls');
const dns = require('dns');
const crypto = require('crypto');
const { URL } = require('url');

// ★强制 IPv4：本环境里 mosquitto/hivemq 只解析出 IPv6，node 直连会 ECONNREFUSED，
//   而 python 会自动回退 IPv4。这里显式解析 A 记录再连。
function resolve4(host) {
  return new Promise((res) => {
    dns.lookup(host, { family: 4 }, (err, addr) => res(err ? null : addr));
  });
}

function encStr(s) { const b = Buffer.from(s, 'utf8'); const o = Buffer.alloc(b.length + 2); o.writeUInt16BE(b.length, 0); b.copy(o, 2); return o; }
function encLen(n) { const o = []; do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; o.push(d); } while (n > 0); return Buffer.from(o); }
function packet(type, body) { return Buffer.concat([Buffer.from([type]), encLen(body.length), body]); }

class MqttWs {
  constructor(url, opts) {
    opts = opts || {};
    this.url = new URL(url);
    this.clientId = opts.clientId || ('mqttws-' + crypto.randomBytes(3).toString('hex'));
    this.username = opts.username || '';          // ★ 自建 broker 鉴权
    this.password = opts.password || '';
    this.clean = opts.clean !== false;
    this.keepalive = opts.keepalive || 60;
    this.timeoutMs = opts.connectTimeout || 8000;
    this.ready = false;
    this._wsBuf = Buffer.alloc(0);      // WS 层字节
    this._payload = Buffer.alloc(0);    // 解帧后的 MQTT 字节流
    this._frag = [];                    // 分片帧缓存
    this._subs = [];
    this._onMsg = null;
    this._keepTimer = null;
    this._closed = false;
    this.lastInboundAt = 0;      // 最后一次收到任何字节
    this.lastPongAt = 0;         // 最后一次收到 PINGRESP
  }

  connect() {
    return new Promise((resolve) => {
      let done = false;
      // ★ 连上后必须清掉空闲超时，否则 socket 空闲 connectTimeout 毫秒就自杀（常驻服务致命）
      const fin = (v) => {
        if (!done) {
          done = true;
          if (v) { try { this.sock.setTimeout(0); } catch (e) {} }
          resolve(v);
        }
      };
      const host = this.url.hostname, port = Number(this.url.port || 8084);
      resolve4(host).then((addr) => {
      const sock = tls.connect({ host: addr || host, port: port, servername: host }, () => {
        const key = crypto.randomBytes(16).toString('base64');
        const path = this.url.pathname || '/mqtt';
        sock.write(
          `GET ${path} HTTP/1.1\r\nHost: ${this.url.host}\r\n` +
          'Upgrade: websocket\r\nConnection: Upgrade\r\n' +
          `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n` +
          'Sec-WebSocket-Protocol: mqtt\r\n\r\n');
      });
      this.sock = sock;
      sock.setTimeout(this.timeoutMs);
      sock.on('data', (d) => {
        this.lastInboundAt = Date.now();
        this._wsBuf = Buffer.concat([this._wsBuf, d]);
        if (!this._upgraded) {
          const i = this._wsBuf.indexOf('\r\n\r\n');
          if (i === -1) return;
          const head = this._wsBuf.slice(0, i).toString();
          if (!/101/.test(head.split('\r\n')[0])) { this.close(); fin(false); return; }
          this._upgraded = true;
          this._wsBuf = this._wsBuf.slice(i + 4);
          this._sendMqttConnect();
        }
        this._drainWs();
      });
      sock.on('error', () => fin(false));
      sock.on('timeout', () => { try { sock.destroy(); } catch (e) {} fin(false); });
      sock.on('close', () => { this.ready = false; fin(false); });
      this._readyCb = () => fin(true);          // ★ CONNACK 成功时 resolve
      setTimeout(() => fin(false), this.timeoutMs + 2000);
      });                                       // ← 结束 .then(addr)
    });
  }

  _sendMqttConnect() {
    // ★ 自建 broker（EMQX）需要鉴权：带 username 时置 0xC0（username+password）
    let flags = this.clean ? 0x02 : 0x00;
    if (this.username) flags |= 0xC0;
    const vh = Buffer.concat([encStr('MQTT'), Buffer.from([0x04, flags, (this.keepalive >> 8) & 255, this.keepalive & 255])]);
    const parts = [vh, encStr(this.clientId)];
    if (this.username) { parts.push(encStr(this.username)); parts.push(encStr(this.password || '')); }
    this._sendMqtt(packet(0x10, Buffer.concat(parts)));
  }

  /* ---------- WS 帧收发 ---------- */
  _wsWrite(payload, opcode) {
    if (!this.sock || this.sock.destroyed) return;
    const p = Buffer.isBuffer(payload) ? payload : Buffer.from(payload);
    const mask = crypto.randomBytes(4);
    let head;
    if (p.length < 126) head = Buffer.from([0x80 | opcode, 0x80 | p.length]);
    else if (p.length < 65536) { head = Buffer.alloc(4); head[0] = 0x80 | opcode; head[1] = 0x80 | 126; head.writeUInt16BE(p.length, 2); }
    else { head = Buffer.alloc(10); head[0] = 0x80 | opcode; head[1] = 0x80 | 127; head.writeUInt32BE(0, 2); head.writeUInt32BE(p.length, 6); }
    const m = Buffer.from(p); for (let i = 0; i < m.length; i++) m[i] ^= mask[i % 4];
    try { this.sock.write(Buffer.concat([head, mask, m])); } catch (e) {}
  }
  _sendMqtt(bytes) { this._wsWrite(bytes, 0x2); }   // 二进制帧
  _pong() { this._wsWrite(Buffer.alloc(0), 0xA); }

  _drainWs() {
    while (this._wsBuf.length >= 2) {
      const b0 = this._wsBuf[0], b1 = this._wsBuf[1];
      const opcode = b0 & 0x0F, masked = (b1 & 0x80) !== 0;
      let len = b1 & 0x7F, off = 2;
      if (len === 126) { if (this._wsBuf.length < 4) return; len = this._wsBuf.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (this._wsBuf.length < 10) return; len = Number(this._wsBuf.readBigUInt64BE(2)); off = 10; }
      let mask = null;
      if (masked) { if (this._wsBuf.length < off + 4) return; mask = this._wsBuf.slice(off, off + 4); off += 4; }
      if (this._wsBuf.length < off + len) return;
      let payload = this._wsBuf.slice(off, off + len);
      this._wsBuf = this._wsBuf.slice(off + len);
      if (mask) { const c = Buffer.from(payload); for (let i = 0; i < c.length; i++) c[i] ^= mask[i % 4]; payload = c; }

      if (opcode === 0x9) { this._pong(); continue; }      // PING → PONG
      if (opcode === 0xA) continue;                        // PONG
      if (opcode === 0x8) { this.close(); continue; }       // CLOSE
      if (opcode === 0x2) { this._frag = [payload]; }       // binary（未分片）
      else if (opcode === 0x0) { this._frag.push(payload); }
      else continue;
      // 简化处理：假设 FIN 帧（MQTT 通常整包/整帧）
      const chunk = Buffer.concat(this._frag);
      this._payload = Buffer.concat([this._payload, chunk]);
      this._drainMqtt();
      this._frag = [];
    }
  }

  _drainMqtt() {
    while (this._payload.length >= 2) {
      const type = this._payload[0] >> 4;
      let len = 0, mult = 1, i = 1;
      while (true) { if (i >= this._payload.length) return; const b = this._payload[i++]; len += (b & 127) * mult; if (!(b & 128)) break; mult *= 128; }
      if (this._payload.length < i + len) return;
      const body = this._payload.slice(i, i + len);
      this._payload = this._payload.slice(i + len);
      if (type === 2) {                                   // CONNACK
        if (body[1] !== 0) { this.ready = false; continue; }
        this.ready = true;
        this._subs.forEach(t => this._rawSub(t));
        this._startKeep();
        if (this._readyCb) { const f = this._readyCb; this._readyCb = null; try { f(); } catch (e) {} }
      } else if (type === 13) {                           // PINGRESP
        this.lastPongAt = Date.now();
      } else if (type === 3) {                            // PUBLISH
        const tl = body.readUInt16BE(0);
        const topic = body.toString('utf8', 2, 2 + tl);
        const payload = body.toString('utf8', 2 + tl);
        if (this._onMsg) { try { this._onMsg(topic, payload); } catch (e) {} }
      }
    }
  }

  _startKeep() { clearInterval(this._keepTimer); this._keepTimer = setInterval(() => { if (this.ready) this._sendMqtt(packet(0xC0, Buffer.alloc(0))); }, Math.max(5, this.keepalive / 2) * 1000); }

  _rawSub(t) { this._sendMqtt(packet(0x82, Buffer.concat([Buffer.from([0x00, 0x01]), encStr(t), Buffer.from([0x00])]))); }
  sub(t) { this._subs.push(t); if (this.ready) this._rawSub(t); }
  pub(t, msg, retain) { if (this.ready) this._sendMqtt(packet(retain ? 0x31 : 0x30, Buffer.concat([encStr(t), Buffer.from(String(msg), 'utf8')]))); }
  onMessage(cb) { this._onMsg = cb; }
  close() { this._closed = true; clearInterval(this._keepTimer); try { this.sock.destroy(); } catch (e) {} }
}

module.exports = { MqttWs, encStr, encLen, packet };
