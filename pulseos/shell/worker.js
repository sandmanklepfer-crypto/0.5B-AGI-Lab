#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  worker.js —— 纯 MQTT 执行端（不需要任何入站端口）
 *  --------------------------------------------------------------------------
 *  ★ 为什么这个文件是天泪纪元模式的复刻
 *
 *    天泪纪元：
 *      GitHub Pages 发静态文件
 *      每个浏览器【主动出站】连 broker
 *      没有任何人 listen 端口
 *      → 所以不需要隧道、不需要公网 IP、随意扩散
 *
 *    这个 worker 一样：
 *      主动出站连 broker，订阅 zhz/pulse/<CH>/invoke
 *      执行后发布到 zhz/pulse/<CH>/reply
 *      全程不 listen 任何端口
 *      → 同样不需要隧道
 *
 *  ★ 和 gateway.js 的区别
 *
 *      gateway.js  = HTTP 服务，需要被外部【调用】 → 要入站端口 → 要隧道
 *      worker.js   = MQTT 客户端，主动【连出去】   → 零入站端口 → 零隧道
 *
 *  用法：
 *      node shell/worker.js --chan mychan --name 我的手机
 *
 *      可选：--state ./state --durability batch --allow invoke,deploy,status
 * ========================================================================== */
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const pulse = require('../index');
const { MqttWs } = require('../agent/mqttws');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };

const CHAN = arg('chan', process.env.PULSE_CHAN || '');
if (!CHAN) {
  console.error('✗ 必须给 --chan（频道名，两端要一致）');
  process.exit(2);
}

const NAME = arg('name', 'worker-' + crypto.randomBytes(2).toString('hex'));
const STATE = arg('state', path.join('/tmp', 'pulse-worker-' + CHAN));
const DUR = arg('durability', 'batch');
const BROKER = arg('broker', 'wss://broker.hivemq.com:8884/mqtt');
const HMAC = arg('hmac', process.env.PULSE_HMAC || '');
const ALLOW = (arg('allow', '') || '').split(',').filter(Boolean);   // 空 = 全部

const NS = 'zhz/pulse/' + CHAN + '/';
const HELLO = 'zhz/pulse/hello';

/* ---------------- 运行时 ---------------- */
const rt = pulse.create({ root: STATE, durability: DUR });

/* 启动时预装 echo，让第一次连接就能测通 */
const ECHO_SRC = `
service echo {
  state { n: int = 0 }
  on "ping" { set n = n + 1 return { pong: n, at: now() } }
  on "get" { return n }
}
`;
try { rt.deploy(ECHO_SRC); } catch (e) { /* 已存在 */ }

/* ---------------- 签名 ---------------- */
function verify(msg) {
  if (!HMAC) return { ok: true, skipped: true };
  if (!msg.sig) return { ok: false, error: '缺少 sig（服务端启用了 HMAC）' };
  const ts = Number(msg.ts || 0);
  if (Math.abs(Date.now() - ts) > 120000) return { ok: false, error: '时间戳过期（±2 分钟）' };
  const want = crypto.createHmac('sha256', HMAC)
    .update(msg.request_id + '|' + msg.capability + '|' + ts).digest('hex');
  const a = Buffer.from(want), b = Buffer.from(String(msg.sig));
  return { ok: a.length === b.length && crypto.timingSafeEqual(a, b) };
}

/* ---------------- 能力分发 ---------------- */
function dispatch(capability, params) {
  const t0 = Date.now();
  if (ALLOW.length && !ALLOW.includes(capability)) {
    return { ok: false, error: '此 worker 不允许 ' + capability + '（只允许 ' + ALLOW.join(',') + '）' };
  }

  if (capability === 'status') {
    return { ok: true, result: Object.assign(rt.stat(), { worker: NAME }), ms: Date.now() - t0 };
  }
  if (capability === 'list_services') {
    return {
      ok: true,
      result: rt.all().map(k => ({
        name: k.name, handlers: k.handlers.map(h => h.op),
        stateBytes: k.stateBytes, pulses: k.pulses,
      })),
      ms: Date.now() - t0,
    };
  }
  if (capability === 'deploy') {
    if (typeof params.src !== 'string') return { ok: false, error: '缺少 params.src' };
    if (params.src.length > 32768) return { ok: false, error: '源码超过 32KB' };
    try {
      const added = rt.deploy(params.src);
      return { ok: true, result: added, ms: Date.now() - t0 };
    } catch (e) { return { ok: false, error: e.message, ms: Date.now() - t0 }; }
  }
  if (capability === 'invoke') {
    const { service, op, args = [] } = params;
    if (!service || !op) return { ok: false, error: '需要 service 和 op' };
    const payload = JSON.stringify(args);
    if (payload.length > 65536) {
      return {
        ok: false,
        error: 'args ' + payload.length + ' 字节超过 64KB。控制面只传路牌，大数据请走数据面。',
        hint: '大文件存到 url 或本地路径，args 里只传 { url } 或 { path }',
      };
    }
    const r = rt.invoke(service, op, args);
    return { ok: r.ok, result: r.result, ms: r.ms, stateBytes: r.stateBytes, error: r.error };
  }
  if (capability === 'flush') {
    const f = rt.flush();
    return { ok: f.ok, result: f, ms: Date.now() - t0 };
  }

  return { ok: false, error: '未知能力: ' + capability };
}

/* ---------------- 连接 ---------------- */
let mq = null;
let connected = false;

function connectLoop() {
  const c = new MqttWs(BROKER, {
    clientId: 'pw-' + CHAN.slice(0, 8) + '-' + crypto.randomBytes(3).toString('hex'),
    keepalive: 30,
    connectTimeout: 8000,
  });

  c.onMessage(onMsg);

  c.connect().then((ok) => {
    if (!ok) {
      console.log('[worker] 连接失败，2s 后重试');
      setTimeout(connectLoop, 2000);
      return;
    }
    mq = c;
    connected = true;
    [NS + 'invoke', NS + 'batch'].forEach(t => c.sub(t));

    /* 保留消息：告诉外面"我在，我叫什么，有什么服务" */
    c.pub(HELLO, JSON.stringify({
      chan: CHAN,
      name: NAME,
      services: rt.services(),
      durability: DUR,
      allow: ALLOW.length ? ALLOW : 'all',
      ts: Date.now(),
    }), true);

    console.log('[worker] 已连上 ' + BROKER);
    console.log('         频道 ' + CHAN + '   名字 ' + NAME);
    console.log('         服务 ' + (rt.services().join(', ') || '(无)'));
    console.log('         订阅 ' + NS + 'invoke');

    /* 心跳 + 假死检测
       ★ 关键：socket 可能静默死亡（对端没了但本地 ready 还是 true）。
          所以不只看 ready，还看「多久没收到 PINGRESP」。 */
    const KEEP = 30;                     // 与 constructor 的 keepalive 一致
    const DEAD_MS = KEEP * 2500;         // 2.5 倍 keepalive 没声音 = 假死
    const hb = setInterval(() => {
      const now = Date.now();
      const lastPong = c.lastPongAt || c.lastInboundAt || 0;
      const silent = lastPong ? (now - lastPong) : 0;

      if (c.ready && silent > DEAD_MS) {
        console.log('[worker] ⚠ 连接假死（' + Math.round(silent / 1000) + 's 无响应），强制重连');
        clearInterval(hb);
        connected = false;
        try { c.close(); } catch (e) {}
        mq = null;
        setTimeout(connectLoop, 1500);
        return;
      }

      if (c.ready) {
        c.pub(HELLO, JSON.stringify({
          chan: CHAN, name: NAME, services: rt.services(),
          durability: DUR, allow: ALLOW.length ? ALLOW : 'all', ts: now,
        }), true);
      } else {
        clearInterval(hb);
        connected = false;
        try { c.close(); } catch (e) {}
        mq = null;
        setTimeout(connectLoop, 2000);
      }
    }, 15000);
    if (hb.unref) hb.unref();
  });
}

/* ---------------- 消息处理 ---------------- */
function onMsg(topic, payload) {
  if (mq) mq.lastInboundAt = Date.now();
  let m;
  try { m = JSON.parse(payload); } catch (e) { return; }

  if (topic === NS + 'invoke') {
    const rid = m.request_id || crypto.randomBytes(6).toString('hex');

    const sig = verify(m);
    if (!sig.ok) {
      return mq.pub(NS + 'reply', JSON.stringify({ request_id: rid, ok: false, error: sig.error, worker: NAME }));
    }

    let out;
    try { out = dispatch(m.capability, m.params || {}); }
    catch (e) { out = { ok: false, error: String(e.message) }; }

    mq.pub(NS + 'reply', JSON.stringify(Object.assign({ request_id: rid, worker: NAME }, out)));
    return;
  }

  if (topic === NS + 'batch') {
    const rid = m.request_id || crypto.randomBytes(6).toString('hex');
    const ops = Array.isArray(m.ops) ? m.ops : [];
    if (ops.length > 1000) {
      return mq.pub(NS + 'reply', JSON.stringify({ request_id: rid, ok: false, error: '单批最多 1000 条', worker: NAME }));
    }

    const t0 = Date.now();
    const results = [];
    let okCount = 0, failCount = 0;
    for (let i = 0; i < ops.length; i++) {
      const op = ops[i] || {};
      try {
        const r = dispatch(op.capability, op.params || {});
        results.push({ index: i, ok: r.ok, result: r.result, ms: r.ms, error: r.error });
        if (r.ok) okCount++; else failCount++;
      } catch (e) {
        results.push({ index: i, ok: false, error: String(e.message) });
        failCount++;
      }
    }
    mq.pub(NS + 'reply', JSON.stringify({
      request_id: rid, worker: NAME, ok: failCount === 0,
      total: ops.length, okCount, failCount,
      totalMs: Date.now() - t0, results,
    }));
    return;
  }
}

/* ---------------- 启动 ---------------- */
console.log('');
console.log('  ◈ PulseOS Worker（纯 MQTT，零入站端口）');
console.log('  ─────────────────────────────────────');
console.log('  频道      ' + CHAN);
console.log('  名前      ' + NAME);
console.log('  状态目录  ' + STATE);
console.log('  持久化    ' + DUR);
console.log('  Broker    ' + BROKER);
console.log('  签名      ' + (HMAC ? '已启用' : '未启用'));
console.log('  允许能力  ' + (ALLOW.length ? ALLOW.join(',') : '全部'));
console.log('  ─────────────────────────────────────');
console.log('  ★ 本进程【不监听任何端口】，只主动出站');
console.log('');

connectLoop();

process.on('SIGINT', () => {
  console.log('\n[worker] 退出，落盘…');
  try { rt.close(); } catch (e) {}
  process.exit(0);
});
