#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  brain.js —— 远程端：调用"手机上的 AI"，但永远看不到 key
 *  --------------------------------------------------------------------------
 *  用法：
 *    node brain.js "帮我总结这段话：..."
 *    node brain.js --file report.md "审查这份报告"
 *    node brain.js --provider deepseek "你好"
 *    node brain.js --status            # 看 vault 活着吗、有哪些 provider
 *
 *  ★ 安全性：本进程只发 prompt、收文本。
 *     key 在 vault 那台设备上，通过 MQTT 反向调用，全程不经过这里。
 * ========================================================================== */
const fs = require('fs');
const crypto = require('crypto');
const { MqttWs } = require('./mqttws');

const CHAN = process.env.VAULT_CHAN || '';
const SECRET = process.env.VAULT_HMAC || '';
const BROKER = process.env.VAULT_BROKER || 'wss://broker.hivemq.com:8884/mqtt';
const NS = 'zhz/vault/' + CHAN + '/';
const TIMEOUT = parseInt(process.env.VAULT_TIMEOUT || '90000', 10);

if (!CHAN) { console.error('✗ 必须设置 VAULT_CHAN'); process.exit(2); }

const rid = (p) => p + Date.now().toString(36) + crypto.randomBytes(2).toString('hex');
const sign = (id, provider, ts) => SECRET
  ? crypto.createHmac('sha256', SECRET).update(id + '|' + provider + '|' + ts).digest('hex')
  : '';

/* ------------------------- 连接 ------------------------- */
async function conn() {
  const c = new MqttWs(BROKER, {
    clientId: rid('brain-'), keepalive: 30, connectTimeout: 10000,
  });
  if (!(await c.connect())) throw new Error('连不上 broker');
  return c;
}

/* ------------------------- 查状态 ------------------------- */
async function status() {
  const c = await conn();
  let hb = null;
  c.onMessage((t, p) => {
    if (t === NS + 'hb') { try { hb = JSON.parse(p); } catch (e) {} }
  });
  c.sub(NS + 'hb');
  for (let i = 0; i < 15 && !hb; i++) { await new Promise(r => setTimeout(r, 200)); }
  c.close();
  if (!hb) { console.log('✗ vault 不在线（手机上的 vault.js 没跑？）'); process.exit(3); }
  console.log('✓ vault 在线');
  console.log('  provider : ' + (hb.providers || []).join(', '));
  console.log('  本小时已用: ' + (hb.calls || 0) + ' 次');
  console.log('  限额      : ' + JSON.stringify(hb.limits || {}));
  process.exit(0);
}

/* ------------------------- 提问 ------------------------- */
async function ask(messages, opts = {}) {
  const c = await conn();
  const id = rid('q');
  const provider = opts.provider || '';
  const ts = Date.now();

  let ans = null;
  c.onMessage((t, p) => {
    if (t !== NS + 'ans') return;
    try { const m = JSON.parse(p); if (m.id === id) ans = m; } catch (e) {}
  });
  c.sub(NS + 'ans');
  await new Promise(r => setTimeout(r, 700));    // 等订阅生效

  c.pub(NS + 'ask', JSON.stringify({
    id, provider, messages, ts,
    model: opts.model,
    maxTokens: opts.maxTokens || 800,
    temperature: opts.temperature,
    sig: sign(id, provider, ts),
  }));

  const t0 = Date.now();
  while (Date.now() - t0 < TIMEOUT && !ans) await new Promise(r => setTimeout(r, 150));
  c.close();

  if (!ans) throw new Error('超时（vault 没响应）');
  if (!ans.ok) throw new Error(ans.error || '未知错误');
  return ans;
}

/* ------------------------- CLI ------------------------- */
async function main() {
  const argv = process.argv.slice(2);
  if (!argv.length || argv[0] === '--help' || argv[0] === '-h') {
    console.log('用法:');
    console.log('  node brain.js --status');
    console.log('  node brain.js "你的问题"');
    console.log('  node brain.js --file 文件.md "基于这个文件回答"');
    console.log('  node brain.js --provider deepseek --model deepseek-chat "你好"');
    process.exit(0);
  }
  if (argv[0] === '--status') return status();

  const opts = {};
  let file = null;
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--provider') opts.provider = argv[++i];
    else if (a === '--model') opts.model = argv[++i];
    else if (a === '--max') opts.maxTokens = parseInt(argv[++i], 10);
    else if (a === '--file') file = argv[++i];
    else rest.push(a);
  }

  const question = rest.join(' ') || '请说明你是什么模型。';
  let content = question;
  if (file) {
    if (!fs.existsSync(file)) { console.error('✗ 没有这个文件: ' + file); process.exit(2); }
    const body = fs.readFileSync(file, 'utf8').slice(0, 20000);
    content = '文件《' + file + '》内容如下：\n\n' + body + '\n\n---\n\n' + question;
  }

  const t0 = Date.now();
  const ans = await ask([{ role: 'user', content }], opts);
  console.log(ans.text || '(空响应)');
  console.log('\n--- ' + ans.provider + ' | ' + ans.ms + 'ms | ' +
    JSON.stringify(ans.usage || {}) + ' | 端到端 ' + (Date.now() - t0) + 'ms ---');
}

if (require.main === module) {
  main().catch(e => { console.error('✗ ' + e.message); process.exit(1); });
}

module.exports = { ask, status };
