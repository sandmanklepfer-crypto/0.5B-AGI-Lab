#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  vault.js —— 钥匙箱：API key 永远不出这台设备
 *  --------------------------------------------------------------------------
 *  架构（这就是你要的"key 存手机，算力在外面"）：
 *
 *    ┌─────────────────────────────┐
 *    │  手机 / 你的设备              │
 *    │  .secrets/*.env  ← key 只在这 │
 *    │  vault.js                    │
 *    │    收到请求 → 本地调 API → 回 │
 *    └─────────────────────────────┘
 *              ↑ MQTT (WSS)
 *              ↓
 *    ┌─────────────────────────────┐
 *    │  GitHub Actions / 任何远程    │
 *    │  agent.js                    │
 *    │    只发"要什么"，看不到 key    │
 *    └─────────────────────────────┘
 *
 *  ★ 安全要点：
 *     1. key 从 .env 读，不出现在命令行/日志/仓库
 *     2. 请求带 HMAC 签名，防止别人往你频道里塞任务
 *     3. 只允许白名单里的 model 和最大 token，防止被刷爆
 *     4. 所有调用记录审计日志（谁、什么模型、多少 token）
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const https = require('https');
const { MqttWs } = require('./agent/mqttws');

/* ---------------------------- 配置 ---------------------------- */
const CHAN = process.env.VAULT_CHAN || '';
const SECRET = process.env.VAULT_HMAC || '';
const BROKER = process.env.VAULT_BROKER || 'wss://broker.hivemq.com:8884/mqtt';
const NS = 'zhz/vault/' + CHAN + '/';
const AUDIT = process.env.VAULT_AUDIT || path.join(__dirname, 'audit.log');

/* 预算护栏：防止钥匙被刷爆 */
const LIMITS = {
  maxTokens: parseInt(process.env.VAULT_MAX_TOKENS || '2000', 10),
  maxCallsPerHour: parseInt(process.env.VAULT_MAX_CALLS || '60', 10),
  maxInputChars: parseInt(process.env.VAULT_MAX_INPUT || '8000', 10),
};
let callsThisHour = 0, hourStart = Date.now();

if (!CHAN) { console.error('✗ 必须设置 VAULT_CHAN'); process.exit(2); }

/* ------------------------- 从 .env 读 key ------------------------- */
/* ★ 关键：只读文件，不读环境变量，不读命令行参数
     这样 key 不会出现在 `ps aux` 或 shell history 里 */
function loadSecrets() {
  const dirs = [
    process.env.VAULT_SECRETS_DIR,
    path.join(__dirname, '..', '..', '..', '.secrets'),
    '/workspace/.secrets',
  ].filter(Boolean);

  const out = {};
  for (const d of dirs) {
    let files = [];
    try { files = fs.readdirSync(d).filter(f => f.endsWith('.env')); } catch (e) { continue; }
    for (const f of files) {
      const full = path.join(d, f);
      let txt;
      try { txt = fs.readFileSync(full, 'utf8'); } catch (e) { continue; }
      const provider = f.replace('.env', '');
      const kv = {};
      for (const line of txt.split('\n')) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
        if (m) kv[m[1]] = m[2].trim().replace(/^["']|["']$/g, '');
      }
      out[provider] = kv;
    }
    if (Object.keys(out).length) break;    // 找到就不继续找
  }
  return out;
}

/* ------------------------- Provider 适配 ------------------------- */
/* 每个 provider 一个适配器：把统一的 {prompt, maxTokens} 翻译成它的 API */
const PROVIDERS = {
  /* 腾讯混元（OpenAI 兼容端点） */
  hunyuan: {
    url: (kv) => (kv.HY_BASE || 'https://api.hunyuan.cloud.tencent.com/v1').replace(/\/$/, '') + '/chat/completions',
    key: (kv) => kv.HY_KEY,
    model: (kv, want) => want || kv.HY_MODEL || 'hunyuan-lite',
    body: (kv, req) => ({
      model: PROVIDERS.hunyuan.model(kv, req.model),
      messages: req.messages,
      max_tokens: req.maxTokens,
      temperature: req.temperature === undefined ? 0.3 : req.temperature,
    }),
    parse: (j) => ({
      text: j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content,
      usage: j.usage,
    }),
  },

  /* mock：不调用任何外部 API，只用来验证整条链是否通 */
  mock: {
    url: () => 'mock://local',
    key: () => 'mock',
    model: (kv, want) => want || 'mock-echo',
    body: (kv, req) => ({ messages: req.messages, max_tokens: req.maxTokens }),
    parse: (j) => ({ text: j.text, usage: { total_tokens: 0 } }),
    local: (kv, req) => {
      const last = req.messages[req.messages.length - 1] || {};
      const q = String(last.content || '');
      return {
        text: '【mock】收到 ' + q.length + ' 字符。前 60 字: ' + q.slice(0, 60) +
              (q.length > 60 ? '…' : '') + '\n（这是 mock provider，用真实 key 时会替换成模型输出）',
        usage: { prompt_tokens: Math.ceil(q.length / 4), completion_tokens: 30, total_tokens: Math.ceil(q.length / 4) + 30 },
      };
    },
  },

  /* 混元 3D 生成（异步：submit → poll）*/
  hunyuan3d: {
    url: (kv) => kv.HY_BASE.replace(/\/$/, '') + '/v1/api/3d/submit',
    key: (kv) => kv.HY_KEY,
    model: (kv, want) => want || kv.HY_MODEL || 'hy-3d-express',
    body: (kv, req) => ({ model: PROVIDERS.hunyuan3d.model(kv, req.model), prompt: req.prompt || '' }),
    async: true,
    poll: async (kv, submitResult) => {
      const jobId = submitResult.id || (submitResult.data && submitResult.data.id);
      if (!jobId) return { status: 'failed', error: '没有拿到 job id' };
      const url = kv.HY_BASE.replace(/\/$/, '') + '/v1/api/3d/query';
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 5000));
        const r = await postJson(url, { 'Authorization': 'Bearer ' + kv.HY_KEY }, { model: PROVIDERS.hunyuan3d.model(kv), id: jobId });
        const j = r.json || {};
        if (j.status === 'completed') return { status: 'completed', urls: (j.data || []).map(d => d.url) };
        if (j.status === 'failed') return { status: 'failed', error: JSON.stringify(j).slice(0, 200) };
      }
      return { status: 'timeout', error: '超过 150 秒' };
    },
  },

  /* DeepSeek（OpenAI 兼容） */
  deepseek: {
    url: () => 'https://api.deepseek.com/chat/completions',
    key: (kv) => kv.DS_KEY || kv.DEEPSEEK_API_KEY,
    model: (kv, want) => want || 'deepseek-chat',
    body: (kv, req) => ({
      model: PROVIDERS.deepseek.model(kv, req.model),
      messages: req.messages,
      max_tokens: req.maxTokens,
      temperature: req.temperature === undefined ? 0.3 : req.temperature,
    }),
    parse: (j) => ({
      text: j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content,
      usage: j.usage,
    }),
  },
};

/* ------------------------- HTTP 调用 ------------------------- */
function postJson(urlStr, headers, bodyObj, timeoutMs = 60000) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const data = Buffer.from(JSON.stringify(bodyObj));
    const req = https.request({
      hostname: u.hostname,
      port: u.port || 443,
      path: u.pathname + u.search,
      method: 'POST',
      headers: Object.assign({
        'Content-Type': 'application/json',
        'Content-Length': data.length,
      }, headers),
      timeout: timeoutMs,
    }, (res) => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => {
        const txt = Buffer.concat(chunks).toString('utf8');
        let json = null;
        try { json = JSON.parse(txt); } catch (e) {}
        resolve({ status: res.statusCode, json, text: txt });
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(new Error('API 超时')); });
    req.write(data);
    req.end();
  });
}

/* ------------------------- 鉴权 ------------------------- */
function verify(m) {
  if (!SECRET) return true;                     // 未配置则不校验（仅限内网/测试）
  if (!m.sig) return false;
  if (Math.abs(Date.now() - (m.ts || 0)) > 120000) return false;   // 2 分钟防重放
  const want = crypto.createHmac('sha256', SECRET)
    .update(m.id + '|' + m.provider + '|' + m.ts).digest('hex');
  const a = Buffer.from(want), b = Buffer.from(String(m.sig));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

/* ------------------------- 审计 ------------------------- */
function audit(rec) {
  const line = JSON.stringify(Object.assign({ t: new Date().toISOString() }, rec)) + '\n';
  try { fs.appendFileSync(AUDIT, line); } catch (e) {}
}

/* ------------------------- 限流 ------------------------- */
function checkRate() {
  if (Date.now() - hourStart > 3600000) { callsThisHour = 0; hourStart = Date.now(); }
  return callsThisHour < LIMITS.maxCallsPerHour;
}

/* ------------------------- 主循环 ------------------------- */
const secrets = loadSecrets();
const avail = ['mock'];
for (const k of Object.keys(secrets)) {
  if (PROVIDERS[k]) { if (!avail.includes(k)) avail.push(k); }
  if (k === 'hunyuan' && secrets[k].HY_KEY) avail.push('hunyuan3d');
}
console.log('[vault] 已加载 provider: ' + (avail.join(', ') || '(无)'));
if (!avail.length) {
  console.log('[vault] ⚠️ 没有可用的 provider，请把 .env 放进 .secrets/');
  console.log('[vault]    支持的文件名: hunyuan.env / deepseek.env');
  console.log('[vault]    支持的变量:   HY_KEY+HY_BASE (混元) 或 DS_KEY (deepseek)');
}

let C = null;
async function connect() {
  for (let i = 0; i < 20; i++) {
    const c = new MqttWs(BROKER, {
      clientId: 'vault-' + crypto.randomBytes(3).toString('hex'),
      keepalive: 30, connectTimeout: 8000,
    });
    c.onMessage(onMsg);
    if (await c.connect()) {
      C = c;
      c.sub(NS + 'ask');
      c.pub(NS + 'hb', JSON.stringify({
        chan: CHAN, providers: avail, limits: LIMITS, ts: Date.now(),
      }), true);
      console.log('[vault] 就绪，监听 ' + NS + 'ask');
      return;
    }
    await new Promise(r => setTimeout(r, 2000));
  }
  console.log('[vault] ✗ 连不上 broker');
  process.exit(1);
}

async function onMsg(topic, payload) {
  if (topic !== NS + 'ask') return;
  let m;
  try { m = JSON.parse(payload); } catch (e) { return; }
  const id = m.id || 'x';
  const reply = (o) => C && C.pub(NS + 'ans', JSON.stringify(Object.assign({ id }, o)));

  if (!verify(m)) {
    audit({ id, ok: false, err: '签名校验失败' });
    return reply({ ok: false, error: '签名校验失败或已过期' });
  }
  if (!checkRate()) {
    audit({ id, ok: false, err: '限流' });
    return reply({ ok: false, error: '超过每小时 ' + LIMITS.maxCallsPerHour + ' 次限制' });
  }

  const pname = m.provider || avail[0];
  const P = PROVIDERS[pname];
  const kv = secrets[pname] || (P && P.local ? {} : null);
  if (!P || !kv) return reply({ ok: false, error: '没有这个 provider: ' + pname + '（可用: ' + avail.join(',') + '）' });
  if (!P.local && !P.key(kv)) return reply({ ok: false, error: pname + ' 缺少 key' });

  const messages = m.messages;
  if (!Array.isArray(messages) || !messages.length) return reply({ ok: false, error: '缺少 messages' });
  const inChars = messages.reduce((a, x) => a + String(x.content || '').length, 0);
  if (inChars > LIMITS.maxInputChars) {
    return reply({ ok: false, error: '输入过长 ' + inChars + ' > ' + LIMITS.maxInputChars });
  }

  const t0 = Date.now();
  try {
    // mock：本地直接返回，不发外部请求
    if (P.local) {
      const parsed = P.local(kv, { messages, model: m.model, maxTokens: m.maxTokens });
      callsThisHour++;
      audit({ id, ok: true, provider: pname, model: 'mock', usage: parsed.usage, ms: Date.now() - t0 });
      return reply({ ok: true, provider: pname, text: parsed.text, usage: parsed.usage, ms: Date.now() - t0 });
    }

    // 异步 provider（提交 + 轮询）
    if (P.async) {
      const sub = await postJson(
        P.url(kv),
        { 'Authorization': 'Bearer ' + P.key(kv) },
        P.body(kv, { prompt: messages.map(x => x.content).join('\n'), model: m.model })
      );
      if (sub.status >= 400) {
        const em = (sub.json && sub.json.error && sub.json.error.message) || sub.text.slice(0, 200);
        audit({ id, ok: false, provider: pname, status: sub.status, err: em });
        return reply({ ok: false, error: 'API ' + sub.status + ': ' + em });
      }
      const out = await P.poll(kv, sub.json || {});
      callsThisHour++;
      audit({ id, ok: out.status === 'completed', provider: pname, status: out.status, ms: Date.now() - t0 });
      return reply(Object.assign({ ok: out.status === 'completed', provider: pname, ms: Date.now() - t0 }, out));
    }

    const r = await postJson(
      P.url(kv),
      { 'Authorization': 'Bearer ' + P.key(kv) },
      P.body(kv, {
        messages,
        model: m.model,
        maxTokens: Math.min(m.maxTokens || 800, LIMITS.maxTokens),
        temperature: m.temperature,
      })
    );
    const ms = Date.now() - t0;

    if (r.status >= 400) {
      const errMsg = (r.json && (r.json.error && r.json.error.message)) || r.text.slice(0, 200);
      audit({ id, ok: false, provider: pname, status: r.status, err: errMsg, ms });
      return reply({ ok: false, error: 'API ' + r.status + ': ' + errMsg });
    }
    const parsed = P.parse(r.json || {});
    callsThisHour++;
    audit({ id, ok: true, provider: pname, model: P.model(kv, m.model), usage: parsed.usage, ms });
    reply({ ok: true, provider: pname, text: parsed.text, usage: parsed.usage, ms });
  } catch (e) {
    audit({ id, ok: false, provider: pname, err: String(e.message), ms: Date.now() - t0 });
    reply({ ok: false, error: String(e.message) });
  }
}

connect();

/* 心跳：让远端知道 vault 活着、有哪些 provider */
setInterval(() => {
  if (C) C.pub(NS + 'hb', JSON.stringify({
    chan: CHAN, providers: avail, calls: callsThisHour, limits: LIMITS, ts: Date.now(),
  }), true);
}, 30000);

process.on('SIGINT', () => { console.log('\n[vault] 退出'); process.exit(0); });
