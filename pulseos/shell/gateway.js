#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  gateway.js —— 极轻量网关：HTTP 入口 → 极简信令
 *  --------------------------------------------------------------------------
 *  它的唯一职责：把外部的 HTTP 请求，翻译成 MQTT 信令，发给目标。
 *
 *      C 端 AI / 浏览器
 *            │  HTTP POST /invoke
 *            ▼
 *      ┌─────────────────┐
 *      │  gateway.js     │  ① 校验 ② 限流 ③ 翻译
 *      └─────────────────┘
 *            │  MQTT（几十字节，只传"路牌"）
 *            ▼
 *      ┌─────────────────┐
 *      │  微内核 / vault  │  执行，回结果
 *      └─────────────────┘
 *
 *  ★ 控制面与数据面分离（这是核心设计）
 *
 *    控制面（MQTT，几 KB）  →  只传 { capability, params, request_id }
 *    数据面（由 params 指定）→  大文件走 url / path / 对象存储
 *
 *    所以网关本身【不搬运大文件】。它只递话。
 *    这就是为什么 1MB 的管道能指挥亿万级算力——因为它只传地址。
 *
 *  用法：
 *      node shell/gateway.js --port 8899 [--mode local|mqtt]
 *
 *      --mode local   直接调本地 PulseOS 运行时（最快，但只能本机）
 *      --mode mqtt    转成 MQTT 信令（跨机，需要 vault 在线）
 * ========================================================================== */
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : d; };

const PORT = parseInt(arg('port', '8899'), 10);
const MODE = arg('mode', 'local');                 // local | mqtt
const CHAN = arg('chan', process.env.PULSE_CHAN || '');
const HMAC = arg('hmac', process.env.PULSE_HMAC || '');
const BROKER = arg('broker', 'wss://broker.hivemq.com:8884/mqtt');

/* 限流 */
const RATE = { max: parseInt(arg('rate', '120'), 10), windowMs: 3600000 };
let hits = [], rateStart = Date.now();

/* 载荷上限 —— ★ 必须与 manifest 的 limits.max_args_bytes 一致，
   否则"文档说不许、实际能过"，AI 会困惑 */
const MANIFEST_PRE = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'pulse.json'), 'utf8'));
const MAX_ARGS = (MANIFEST_PRE.limits && MANIFEST_PRE.limits.max_args_bytes) || 65536;
const MAX_BODY = Math.max(MAX_ARGS * 2, 128 * 1024);   // body 要能装下 JSON 包装

const MANIFEST = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'pulse.json'), 'utf8'));

/* ============================ 本地运行时 ============================ */
let runtime = null;
if (MODE === 'local') {
  const pulse = require('../index');
  runtime = pulse.create({
    root: arg('state', '/tmp/gateway-state'),
    /* ★ 持久化模式：sync 最安全但慢 59x，batch 默认，none 最快 */
    durability: arg('durability', 'batch'),
    batchSize: parseInt(arg('batch', '64'), 10),
    batchMs: parseInt(arg('batch-ms', '20'), 10),
  });
  /* 预装两个示例服务，让 gateway 起来就能用 */
  try {
    runtime.deploy(`
service echo {
  state { n: int = 0 }
  on "ping" { set n = n + 1 return { pong: n, at: now() } }
  on "get" { return n }
}
`);
  } catch (e) { /* 已存在 */ }
}

/* ============================ MQTT 信令 ============================ */
let mq = null;
if (MODE === 'mqtt') {
  if (!CHAN) { console.error('✗ mqtt 模式必须给 --chan'); process.exit(2); }
  const NS = 'zhz/pulse/' + CHAN + '/';
  const { MqttWs: M } = require('../agent/mqttws');
  mq = new M(BROKER, { clientId: 'gw-' + crypto.randomBytes(3).toString('hex'), connectTimeout: 8000 });
  mq.connect().then(ok => {
    if (ok) { mq.sub(NS + 'reply'); console.log('[gw] MQTT 已连接 ' + BROKER); }
    else console.log('[gw] MQTT 连接失败，退回 local');
  });
  mq._ns = NS;
}

/* ============================ 签名 ============================ */
function verifySig(req, capability, requestId) {
  if (!HMAC) return { ok: true, skipped: true };
  const sig = req.headers['x-pulse-signature'];
  if (!sig) return { ok: false, error: '缺少 X-Pulse-Signature' };
  const ts = Number(req.headers['x-pulse-timestamp'] || 0);
  if (Math.abs(Date.now() - ts) > 120000) return { ok: false, error: '时间戳过期（±2 分钟）' };
  const want = crypto.createHmac('sha256', HMAC)
    .update(requestId + '|' + capability + '|' + ts).digest('hex');
  const a = Buffer.from(want), b = Buffer.from(String(sig));
  return { ok: a.length === b.length && crypto.timingSafeEqual(a, b) };
}

/* ============================ 限流 ============================ */
function checkRate() {
  const now = Date.now();
  if (now - rateStart > RATE.windowMs) { hits = []; rateStart = now; }
  if (hits.length >= RATE.max) {
    return { ok: false, error: '超过限制 ' + RATE.max + '/小时', retryAfter: Math.ceil((rateStart + RATE.windowMs - now) / 1000) };
  }
  hits.push(now);
  return { ok: true, remaining: RATE.max - hits.length };
}

/* ============================ 能力分发 ============================ */
async function dispatch(capability, params) {
  const t0 = Date.now();

  /* --- 元能力：不需要微内核 --- */
  if (capability === 'status') {
    if (!runtime) return { ok: false, error: 'local 模式才有 status' };
    return { ok: true, result: runtime.stat(), ms: Date.now() - t0 };
  }
  if (capability === 'list_services') {
    if (!runtime) return { ok: false, error: 'local 模式才有 list_services' };
    return { ok: true, result: runtime.all().map(k => ({
      name: k.name, handlers: k.handlers.map(h => h.op), stateBytes: k.stateBytes, pulses: k.pulses,
    })), ms: Date.now() - t0 };
  }
  if (capability === 'manifest') {
    return { ok: true, result: MANIFEST, ms: Date.now() - t0 };
  }

  /* --- deploy --- */
  if (capability === 'deploy') {
    if (!runtime) return { ok: false, error: 'local 模式才能部署' };
    if (typeof params.src !== 'string') return { ok: false, error: '缺少 params.src' };
    if (params.src.length > 32768) return { ok: false, error: '源码超过 32KB' };
    try {
      const added = runtime.deploy(params.src);
      return { ok: true, result: added, ms: Date.now() - t0 };
    } catch (e) {
      return { ok: false, error: e.message, ms: Date.now() - t0 };
    }
  }

  /* --- invoke --- */
  if (capability === 'invoke') {
    const { service, op, args } = params;
    if (!service || !op) return { ok: false, error: '需要 service 和 op' };

    /* 数据面分离：如果 args 里带了大 url/path，网关只透传指针 */
    const payload = JSON.stringify(args || []);
    if (payload.length > MAX_ARGS) {
      return {
        ok: false,
        error: 'args ' + payload.length + ' 字节，超过上限 ' + MAX_ARGS + '。控制面只传路牌，大数据请走数据面。',
        hint: '把大数据存到 url 或本地路径，args 里只传 { url } 或 { path }',
        limit: MAX_ARGS,
        actual: payload.length,
      };
    }

    if (runtime) {
      const r = runtime.invoke(service, op, args || []);
      return { ok: r.ok, result: r.result, ms: r.ms, error: r.error, stateBytes: r.stateBytes };
    }

    /* MQTT 模式：发信令，等回复 */
    if (mq && mq.ready) {
      const rid = crypto.randomBytes(6).toString('hex');
      const NS = mq._ns;
      return new Promise((resolve) => {
        let done = false;
        const timer = setTimeout(() => {
          if (!done) { done = true; resolve({ ok: false, error: '信令超时（15s）', request_id: rid }); }
        }, 15000);
        const onMsg = (t, p) => {
          try {
            const m = JSON.parse(p);
            if (m.request_id === rid && !done) {
              done = true; clearTimeout(timer);
              resolve({ ok: m.ok, result: m.result, ms: Date.now() - t0, error: m.error });
            }
          } catch (e) {}
        };
        mq.onMessage(onMsg);
        mq.pub(NS + 'invoke', JSON.stringify({ request_id: rid, service, op, args: args || [] }));
      });
    }

    return { ok: false, error: '没有可用的执行端（runtime 未初始化，MQTT 未连接）' };
  }

  /* --- ai_chat：转发给 vault --- */
  if (capability === 'ai_chat') {
    if (!mq || !mq.ready) return { ok: false, error: '需要 MQTT 且 vault 在线' };
    const NS = mq._ns;
    const rid = crypto.randomBytes(6).toString('hex');
    const ts = Date.now();
    const sig = HMAC ? crypto.createHmac('sha256', HMAC).update(rid + '|' + (params.provider || '') + '|' + ts).digest('hex') : '';
    return new Promise((resolve) => {
      let done = false;
      const timer = setTimeout(() => { if (!done) { done = true; resolve({ ok: false, error: 'AI 超时（60s）' }); } }, 60000);
      mq.onMessage((t, p) => {
        if (t !== NS + 'ans') return;
        try {
          const m = JSON.parse(p);
          if (m.id === rid && !done) {
            done = true; clearTimeout(timer);
            resolve({ ok: m.ok, result: m.text, provider: m.provider, usage: m.usage, ms: Date.now() - t0, error: m.error });
          }
        } catch (e) {}
      });
      mq.pub(NS + 'ask', JSON.stringify({
        id: rid, provider: params.provider || '', messages: params.messages || [],
        maxTokens: params.maxTokens || 800, ts, sig,
      }));
    });
  }

  return { ok: false, error: '未知能力: ' + capability + '（可用: ' + MANIFEST.capabilities.map(c => c.id).join(', ') + '）' };
}

/* ============================ HTTP 服务 ============================ */
function send(res, code, obj) {
  const body = JSON.stringify(obj, null, 2);
  res.writeHead(code, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Pulse-Signature, X-Pulse-Timestamp',
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let n = 0;
    req.on('data', d => {
      n += d.length;
      if (n > MAX_BODY) { reject(new Error('body 超过 ' + MAX_BODY + ' 字节')); req.destroy(); return; }
      chunks.push(d);
    });
    req.on('end', () => {
      const t = Buffer.concat(chunks).toString('utf8');
      if (!t) return resolve({});
      try { resolve(JSON.parse(t)); } catch (e) { reject(new Error('JSON 解析失败')); }
    });
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  const p = u.pathname;

  if (req.method === 'OPTIONS') return send(res, 204, {});

  /* 健康检查（AI 应该先调这个） */
  if (p === '/health' || p === '/healthz') {
    return send(res, 200, {
      ok: true,
      online: true,
      mode: MODE,
      mqtt: mq ? !!mq.ready : false,
      services: runtime ? runtime.services() : [],
      rate: { used: hits.length, max: RATE.max },
      manifest: '/manifest',
    });
  }

  /* 显式落盘（batch 模式下想强一致时调） */
  if (p === '/flush' && req.method === 'POST') {
    if (!runtime) return send(res, 200, { ok: false, error: 'local 模式才有 flush' });
    const f = runtime.flush();
    return send(res, 200, Object.assign({ ok: f.ok }, f));
  }

  /* 能力清单（AI 读这个） */
  if (p === '/manifest' || p === '/.well-known/pulse.json') {
    return send(res, 200, MANIFEST);
  }

  /* ==================== 批量调用 ====================
     AI 应该把"要做的 N 件事"打包成一个数组，一次 POST 过来。
     不要逐条调用 —— 每条都要一次网络往返 + AI 重新思考。
     ★ 关键：批量是【顺序执行】的，因为 PulseScript 的状态有因果依赖。
        真正并行需要 service 之间互不依赖，那要另一套语义。 */
  if (p === '/invoke_batch' && req.method === 'POST') {
    let body;
    try { body = await readBody(req); }
    catch (e) { return send(res, 413, { ok: false, error: e.message }); }

    const ops = body.ops;
    if (!Array.isArray(ops)) {
      return send(res, 400, {
        ok: false, error: '需要 ops 数组',
        example: { ops: [
          { capability: 'invoke', params: { service: 'echo', op: 'ping' } },
          { capability: 'invoke', params: { service: 'calc', op: 'add', args: [1, 2] } },
        ] },
      });
    }
    if (ops.length > 1000) {
      return send(res, 400, { ok: false, error: '单批最多 1000 条，收到 ' + ops.length });
    }

    const sig = verifySig(req, 'batch', body.request_id || 'batch');
    if (!sig.ok) return send(res, 401, { ok: false, error: sig.error });

    const rl = checkRate();
    if (!rl.ok) return send(res, 429, { ok: false, error: rl.error, retry_after: rl.retryAfter });

    const t0 = process.hrtime.bigint();
    const results = [];
    let okCount = 0, failCount = 0;

    for (let i = 0; i < ops.length; i++) {
      const op = ops[i];
      if (!op || !op.capability) {
        results.push({ index: i, ok: false, error: '缺少 capability' });
        failCount++; continue;
      }
      try {
        const r = await dispatch(op.capability, op.params || {});
        results.push({ index: i, ok: r.ok, result: r.result, ms: r.ms, error: r.error });
        if (r.ok) okCount++; else failCount++;
      } catch (e) {
        results.push({ index: i, ok: false, error: String(e.message) });
        failCount++;
      }
    }

    const totalMs = Number(process.hrtime.bigint() - t0) / 1e6;
    return send(res, 200, {
      ok: failCount === 0,
      total: ops.length,
      okCount, failCount,
      totalMs: +totalMs.toFixed(3),
      avgMs: +(totalMs / ops.length).toFixed(4),
      results,
    });
  }

  /* 统一调用入口 */
  if (p === '/invoke' && req.method === 'POST') {
    let body;
    try { body = await readBody(req); }
    catch (e) { return send(res, 413, { ok: false, error: e.message }); }

    const capability = body.capability;
    const params = body.params || {};
    const requestId = body.request_id || crypto.randomBytes(6).toString('hex');

    if (!capability) return send(res, 400, { ok: false, error: '缺少 capability' });

    /* 签名 */
    const sig = verifySig(req, capability, requestId);
    if (!sig.ok) return send(res, 401, { ok: false, error: sig.error, request_id: requestId });

    /* 限流 */
    const rl = checkRate();
    if (!rl.ok) return send(res, 429, { ok: false, error: rl.error, retry_after: rl.retryAfter });

    /* 分发 */
    let out;
    try { out = await dispatch(capability, params); }
    catch (e) { out = { ok: false, error: String(e.message) }; }

    return send(res, 200, Object.assign({ request_id: requestId, capability }, out));
  }

  send(res, 404, {
    ok: false,
    error: '未知路径 ' + p,
    available: ['GET /health', 'GET /manifest', 'POST /invoke', 'POST /invoke_batch', 'POST /flush'],
  });
});

server.listen(PORT, '0.0.0.0', () => {
  console.log('');
  console.log('  ◈ PulseOS Gateway');
  console.log('  ─────────────────────────────────────');
  console.log('  模式      ' + MODE);
  console.log('  监听      http://0.0.0.0:' + PORT);
  if (MODE === 'mqtt') console.log('  MQTT      ' + BROKER + '  chan=' + CHAN);
  if (runtime) {
    console.log('  服务      ' + (runtime.services().join(', ') || '(无)'));
    console.log('  持久化    ' + runtime.durability + (runtime.durability === 'batch' ? ' (每 ' + runtime.batchSize + ' 次或 ' + runtime.batchMs + 'ms)' : ''));
  }
  console.log('  限流      ' + RATE.max + ' 次/小时');
  console.log('  签名      ' + (HMAC ? '已启用' : '未启用'));
  console.log('  ─────────────────────────────────────');
  console.log('  GET  /health     健康检查');
  console.log('  GET  /manifest   能力清单');
  console.log('  POST /invoke        单次调用');
  console.log('  POST /invoke_batch  ★ 批量调用（AI 应该用这个）');
  console.log('');
});
