#!/usr/bin/env node
/* ==========================================================================
 *  tldbg_cdp —— 用 adb 直连 WebView 的"命令行调试器"
 *  --------------------------------------------------------------------------
 *  不需要改游戏、不在画面上显示任何东西。
 *  原理：App 的 WebView 调试是开着的（webview_devtools_remote）。
 *        adb forward 把设备上的调试 socket 映射到本机端口，
 *        再用 Chrome DevTools Protocol 执行任意 JS 并取回结果。
 *
 *  用法：
 *    node tools/tldbg_cdp.js "表达式"            # 执行任意 JS，打印返回值
 *    node tools/tldbg_cdp.js --console           # 看最近的 console 日志
 *    node tools/tldbg_cdp.js --shot              # 打印当前页面关键状态
 *    node tools/tldbg_cdp.js                     # 交互式（一行一条 JS）
 *    node tools/tldbg_cdp.js --pkg com.tianlei.game "1+1"
 * ========================================================================== */
'use strict';

const { execSync } = require('child_process');
const net = require('net');
const http = require('http');
const crypto = require('crypto');

const PORT = 9222;

function adb(args, opts) {
  return execSync(`adb -P 5039 -s 127.0.0.1:5555 ${args}`, Object.assign({ encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }, opts || {}));
}

/* ---------- 1) 找到 WebView 调试 socket ---------- */
function findSocket(pkg) {
  adb('start-server', { stdio: 'ignore' });
  try { adb('connect 127.0.0.1:5555', { stdio: 'ignore' }); } catch (e) {}
  let out = '';
  try { out = adb('shell cat /proc/net/unix'); } catch (e) { out = ''; }
  const names = [...out.matchAll(/@([a-zA-Z0-9_.]*devtools_remote[a-zA-Z0-9_]*)/g)].map(m => m[1]);
  if (!names.length) return null;
  // 优先 webview_devtools_remote_<pid>
  const web = names.find(n => n.startsWith('webview_devtools_remote'));
  return web || names[0];
}

/* ---------- 2) adb forward ---------- */
function forward(sockName) {
  try { adb(`forward --remove tcp:${PORT}`, { stdio: 'ignore' }); } catch (e) {}
  adb(`forward tcp:${PORT} localabstract:${sockName}`);
}

/* ---------- 3) 取页面目标 ---------- */
function getTarget() {
  return new Promise((resolve, reject) => {
    const req = http.get({ host: '127.0.0.1', port: PORT, path: '/json', timeout: 4000 }, (res) => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => {
        try {
          const list = JSON.parse(d);
          const pages = list.filter(t => t.type === 'page' && t.webSocketDebuggerUrl);
          resolve(pages[0] || list[0] || null);
        } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('devtools /json 超时')); });
  });
}

/* ---------- 4) 极简 WebSocket 客户端（带掩码） ---------- */
class Ws {
  constructor(url) { this.url = url; this.buf = Buffer.alloc(0); this.handlers = []; }
  connect() {
    return new Promise((resolve, reject) => {
      const u = new URL(this.url);
      const key = crypto.randomBytes(16).toString('base64');
      this.sock = net.connect(Number(u.port || 80), u.hostname, () => {
        this.sock.write(
          `GET ${u.pathname}${u.search} HTTP/1.1\r\nHost: ${u.host}\r\n` +
          `Upgrade: websocket\r\nConnection: Upgrade\r\n` +
          `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`);
      });
      this.sock.on('data', (d) => {
        this.buf = Buffer.concat([this.buf, d]);
        if (!this.ok) {
          const i = this.buf.indexOf('\r\n\r\n');
          if (i === -1) return;
          const head = this.buf.slice(0, i).toString();
          if (!/101/.test(head.split('\r\n')[0])) { reject(new Error(head.split('\r\n')[0])); return; }
          this.ok = true;
          this.buf = this.buf.slice(i + 4);
          resolve();
        }
        this._drain();
      });
      this.sock.on('error', reject);
    });
  }
  _drain() {
    while (this.buf.length >= 2) {
      const b1 = this.buf[1]; let len = b1 & 127, off = 2;
      if (len === 126) { if (this.buf.length < 4) return; len = this.buf.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (this.buf.length < 10) return; len = Number(this.buf.readBigUInt64BE(2)); off = 10; }
      if (this.buf.length < off + len) return;
      const payload = this.buf.slice(off, off + len); this.buf = this.buf.slice(off + len);
      const text = payload.toString('utf8');
      for (const h of this.handlers) { try { h(text); } catch (e) {} }
    }
  }
  send(str) {
    const p = Buffer.from(str, 'utf8');
    const mask = crypto.randomBytes(4);
    let head;
    if (p.length < 126) { head = Buffer.from([0x81, 0x80 | p.length]); }
    else if (p.length < 65536) { head = Buffer.alloc(4); head[0] = 0x81; head[1] = 0x80 | 126; head.writeUInt16BE(p.length, 2); }
    else { head = Buffer.alloc(10); head[0] = 0x81; head[1] = 0x80 | 127; head.writeUInt32BE(0, 2); head.writeUInt32BE(p.length, 6); }
    const m = Buffer.from(p); for (let i = 0; i < m.length; i++) m[i] ^= mask[i % 4];
    this.sock.write(Buffer.concat([head, mask, m]));
  }
  onMsg(fn) { this.handlers.push(fn); }
  close() { try { this.sock.end(); } catch (e) {} }
}

/* ---------- 5) CDP 调用 ---------- */
let msgId = 1;
function cdp(ws, method, params) {
  return new Promise((resolve) => {
    const id = msgId++;
    const onMsg = (t) => {
      let o; try { o = JSON.parse(t); } catch (e) { return; }
      if (o.id === id) resolve(o);
    };
    ws.onMsg(onMsg);
    ws.send(JSON.stringify({ id, method, params: params || {} }));
    setTimeout(() => resolve({ timeout: true }), 6000);
  });
}

/* ---------- 主流程 ---------- */
(async () => {
  const argv = process.argv.slice(2);
  let pkg = 'com.tianlei.game';
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--pkg') { pkg = argv[++i]; } else rest.push(argv[i]);
  }

  const sockName = findSocket(pkg);
  if (!sockName) { console.error('✗ 找不到 WebView 调试 socket（App 没开 WebView 调试？）'); process.exit(1); }
  forward(sockName);
  const target = await getTarget();
  if (!target) { console.error('✗ 没有可调试页面（游戏没启动？）'); process.exit(1); }
  if (process.env.TLDBG_VERBOSE) console.error('# target:', target.url);

  const ws = new Ws(target.webSocketDebuggerUrl);
  await ws.connect();

  const mode = rest[0];
  if (mode === '--console') {
    await cdp(ws, 'Runtime.enable');
    console.log('监听 console（5 秒）…');
    ws.onMsg(t => { let o; try { o = JSON.parse(t); } catch (e) { return; } if (o.method === 'Runtime.consoleAPICalled') console.log('[console]', (o.params.args || []).map(a => a.value !== undefined ? a.value : a.description).join(' ')); });
    setTimeout(() => { ws.close(); process.exit(0); }, 5000);
    return;
  }

  const expr = mode === '--shot'
    ? `JSON.stringify({scene:(window.GameState&&GameState.currentScene),worldRunning:!!(window.WorldMgr&&WorldMgr.running),netConnected:!!(window.NetMgr&&NetMgr.connected),isHost:!!(window.NetMgr&&NetMgr.isHost),peers:window.NetMgr?NetMgr.remotePlayers.size:-1,enemies:window.WorldMgr?WorldMgr.enemies.length:-1,simMonsters:window.WorldSim?WorldSim.monsters.filter(m=>m.alive).length:-1,cam:window.WorldMgr?[Math.round(WorldMgr.cam.x),Math.round(WorldMgr.cam.y)]:null,css:window.WorldMgr?[WorldMgr.cssW,WorldMgr.cssH]:null,scale:window.WorldMgr?WorldMgr.scale:null,bgLoaded:window.WorldMgr?Object.values(WorldMgr.bgImages).filter(i=>i.complete&&i.naturalWidth).length:null,err:window.WorldMgr?WorldMgr._drawErr:null,jsErr:window.__lastErr||null})`
    : rest.join(' ');

  if (!expr) {
    // 交互式
    const rl = require('readline').createInterface({ input: process.stdin, output: process.stdout, prompt: 'cdp> ' });
    console.log('输入 JS 表达式，回车执行，exit 退出');
    rl.prompt();
    rl.on('line', async (line) => {
      const t = line.trim();
      if (t === 'exit') { ws.close(); process.exit(0); }
      if (t) { const r = await cdp(ws, 'Runtime.evaluate', { expression: t, returnByValue: true, awaitPromise: true }); printRes(r); }
      rl.prompt();
    });
    return;
  }

  const r = await cdp(ws, 'Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  printRes(r);
  ws.close();
  process.exit(0);
})().catch(e => { console.error('✗', e.message); process.exit(1); });

function printRes(r) {
  if (r.timeout) { console.log('✗ 执行超时'); return; }
  const res = r.result || {};
  if (res.exceptionDetails) { console.log('✗ 异常:', res.exceptionDetails.text, res.exceptionDetails.exception && res.exceptionDetails.exception.description); return; }
  const v = res.result && res.result.value;
  if (v === undefined) console.log('(undefined)');
  else if (typeof v === 'string') console.log(v);
  else console.log(JSON.stringify(v, null, 2));
}
