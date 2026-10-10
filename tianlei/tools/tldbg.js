#!/usr/bin/env node
/* ==========================================================================
 *  tldbg —— 天泪纪元 · 命令行调试台（沙箱侧）
 *  --------------------------------------------------------------------------
 *  原理：游戏网页里内置了「调试命令通道」（走同一条 MQTT 实时通道）。
 *        本工具用原生 TCP 直连公共 MQTT broker，把命令发到
 *          zhz/tianlei/v1/<频道>/debug
 *        游戏执行后把结果发回
 *          zhz/tianlei/v1/<频道>/debug/result
 *        本工具打印结果 —— 就像在 Linux 终端敲命令一样。
 *
 *  为什么走 MQTT：沙箱（proot）里的端口到不了手机，但两边都能连公网，
 *                 所以用公共 broker 当"总线"，完全不需要部署服务器。
 *
 *  用法：
 *    node tools/tldbg.js                      # 交互式命令行
 *    node tools/tldbg.js state                # 单条命令
 *    node tools/tldbg.js --room main state
 *    node tools/tldbg.js --listen             # 只看游戏主动上报
 *
 *  常用命令（游戏侧实现，见 web/js/debug.js）：
 *    help                 命令列表
 *    state                玩家/世界/联机 汇总状态
 *    ping                 测往返延迟
 *    tp <x> <y>           传送
 *    boss <1-4>           传送到锚点并触发
 *    spawn <type> [n]     在玩家附近刷怪（floater/golem/wraith）
 *    killall              清空附近怪物
 *    overlay on|off       画面调试信息开关
 *    god on|off           无敌
 *    pvp on|off           开关对战
 *    who                  在线玩家列表
 *    chat <文本>          以调试身份发一条世界消息
 *    say <文本>           同上（别名）
 * ========================================================================== */
'use strict';

const net = require('net');
const crypto = require('crypto');

const BROKERS = [
  { host: 'broker.emqx.io', port: 1883 },
  { host: 'test.mosquitto.org', port: 1883 },
  { host: 'broker.hivemq.com', port: 1883 },
];

/* ---------------- MQTT 3.1.1 最小实现（QoS0，TCP） ---------------- */

function encStr(s) {
  const b = Buffer.from(s, 'utf8');
  const out = Buffer.alloc(b.length + 2);
  out.writeUInt16BE(b.length, 0);
  b.copy(out, 2);
  return out;
}
function encRemain(n) {
  const out = [];
  do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; out.push(d); } while (n > 0);
  return Buffer.from(out);
}
function packet(type, body) {
  return Buffer.concat([Buffer.from([type]), encRemain(body.length), body]);
}
function parsePublish(buf) {
  // buf 从"topic 长度"开始（已跳过固定头与剩余长度）
  const tlen = buf.readUInt16BE(0);
  const topic = buf.toString('utf8', 2, 2 + tlen);
  const payload = buf.toString('utf8', 2 + tlen);
  return { topic, payload };
}

class MqttCli {
  constructor(opts) {
    this.opts = opts;
    this.buf = Buffer.alloc(0);
    this.ready = false;
    this.subs = new Set();
    this.handlers = { connect: [], message: [], close: [] };
    this.bi = 0;
    this.closed = false;
    this.connect();
  }
  on(ev, fn) { this.handlers[ev].push(fn); return this; }
  _emit(ev, a, b) { this.handlers[ev].forEach(f => { try { f(a, b); } catch (e) {} }); }

  connect() {
    if (this.closed) return;
    const b = BROKERS[this.bi % BROKERS.length];
    this.broker = b;
    this.sock = net.connect(b.port, b.host);
    this.sock.setNoDelay(true);

    this.sock.on('connect', () => {
      const cid = 'tldbg' + Math.random().toString(36).slice(2, 8);
      const vh = Buffer.concat([encStr('MQTT'), Buffer.from([4, 0x02, 0x00, 0x3C])]);
      this.sock.write(packet(0x10, Buffer.concat([vh, encStr(cid)])));
    });
    this.sock.on('data', (d) => this._onData(d));
    this.sock.on('error', () => {});
    this.sock.on('close', () => {
      this.ready = false;
      this._emit('close');
      if (!this.closed) setTimeout(() => { this.bi++; this.connect(); }, 1500);
    });
  }

  _onData(d) {
    this.buf = Buffer.concat([this.buf, d]);
    while (this.buf.length >= 2) {
      const type = this.buf[0] >> 4;
      let len = 0, mul = 1, i = 1, b;
      do { b = this.buf[i++]; len += (b & 127) * mul; mul *= 128; if (i > 4) return; } while (b & 128);
      if (this.buf.length < i + len) return;
      const body = this.buf.slice(i, i + len);
      this.buf = this.buf.slice(i + len);

      if (type === 2) {                        // CONNACK
        if (body[1] !== 0) { this.sock.destroy(); return; }
        this.ready = true;
        this.subs.forEach(t => this._sub(t));
        this._emit('connect', `${this.broker.host}:${this.broker.port}`);
      } else if (type === 3) {                 // PUBLISH
        const { topic, payload } = parsePublish(body);
        this._emit('message', topic, payload);
      }
    }
  }

  _sub(topic) { this.sock.write(packet(0x82, Buffer.concat([Buffer.from([0, 1]), encStr(topic), Buffer.from([0])]))); }
  subscribe(topic) { this.subs.add(topic); if (this.ready) this._sub(topic); }
  publish(topic, text) { if (this.ready) this.sock.write(packet(0x30, Buffer.concat([encStr(topic), Buffer.from(String(text), 'utf8')]))); }
  end() { this.closed = true; try { this.sock.write(packet(0xE0, Buffer.alloc(0))); this.sock.end(); } catch (e) {} }
}

/* ---------------- CLI ---------------- */

const argv = process.argv.slice(2);
let room = 'main';
let listenOnly = false;
const cmds = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--room') { room = argv[++i]; }
  else if (argv[i] === '--listen') { listenOnly = true; }
  else cmds.push(argv[i]);
}

const BASE = `zhz/tianlei/v1/${room}/`;
const T_DEBUG = BASE + 'debug';
const T_RESULT = BASE + 'debug/result';

const cli = new MqttCli({});
let pending = null;

cli.on('connect', (broker) => {
  if (listenOnly) {
    console.log(`[tldbg] 已连接 ${broker} · 频道=${room} · 监听中…`);
  } else {
    console.log(`[tldbg] 已连接 ${broker} · 频道=${room}`);
  }
  cli.subscribe(T_RESULT);
  if (cmds.length) {
    send(cmds.join(' '));
  } else if (!listenOnly) {
    // 交互式
    const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout, prompt: 'tldbg> ' });
    console.log('输入命令，help 看列表，exit 退出');
    rl.prompt();
    rl.on('line', (line) => {
      const t = line.trim();
      if (!t) return rl.prompt();
      if (t === 'exit' || t === 'quit') { cli.end(); process.exit(0); }
      send(t);
      setTimeout(() => rl.prompt(), 300);
    });
    rl.on('close', () => { cli.end(); process.exit(0); });
  }
});

cli.on('message', (topic, payload) => {
  if (topic !== T_RESULT) return;
  let o; try { o = JSON.parse(payload); } catch (e) { console.log('[结果]', payload); return; }
  const ms = pending ? (Date.now() - pending) : null;
  console.log(o.ok === false ? '✗ ' + o.text : ('✓ ' + o.text));
  if (o.data) console.log(typeof o.data === 'string' ? o.data : JSON.stringify(o.data, null, 2));
  if (ms !== null && !o.noRtt) console.log(`  (往返 ${ms}ms)`);
  pending = null;
  if (cmds.length) setTimeout(() => { cli.end(); process.exit(0); }, 150);
});

function send(cmd) {
  pending = Date.now();
  cli.publish(T_DEBUG, JSON.stringify({ cmd, from: 'tldbg', at: pending }));
}

// 单条命令超时
if (cmds.length) {
  setTimeout(() => {
    if (pending) { console.log('✗ 超时：游戏没响应（确认游戏已进入联机世界、且频道相同）'); cli.end(); process.exit(1); }
  }, 8000);
}
process.on('SIGINT', () => { cli.end(); process.exit(0); });
