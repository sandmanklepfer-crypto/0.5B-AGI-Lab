#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  snapshot.js —— 「门里」的那个机器人
 *  --------------------------------------------------------------------------
 *  这文件就是 GitHub Actions 每 5 分钟跑一次的东西。
 *
 *  它做的事：
 *    ① 连 MQTT，读 zhz/pulse/hello 看谁在线
 *    ② 对每个在线的 worker 发一次 list_services + status
 *    ③ 把结果写成 result.json（带时间戳 + 数据年龄）
 *    ④ Actions 再把它 commit 进仓库
 *
 *  → 下次任何人（或爬虫）访问网页，读到的 result.json 就是【真实的】数据
 *  → 这就是「敲门 → 门里处理 → 敲门声回传」里的「门里」
 *
 *  ★ 和 demo.html 的分工
 *    demo.html  = 门铃（给人看、给会跑 JS 的浏览器用）
 *    result.json = 回声（给爬虫、纯文本 AI 读）
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { MqttWs } = require('../agent/mqttws');

const CHAN = process.env.PULSE_CHAN || 'live7k';
const BROKER = process.env.PULSE_BROKER || 'wss://broker.hivemq.com:8884/mqtt';
const OUT = process.env.OUT_FILE || path.join(__dirname, '..', 'result.json');
const NS = 'zhz/pulse/' + CHAN + '/';
const HELLO = 'zhz/pulse/hello';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const rid = () => crypto.randomBytes(5).toString('hex');

/* 发一条命令并等回复 */
function ask(c, payload, timeoutMs) {
  return new Promise((resolve) => {
    const id = rid();
    payload.request_id = id;
    let done = null;
    const onMsg = (t, p) => {
      if (t !== NS + 'reply') return;
      try { const o = JSON.parse(p); if (o.request_id === id) done = o; } catch (e) {}
    };
    c.onMessage(onMsg);
    const topic = NS + (Array.isArray(payload.ops) ? 'batch' : 'invoke');
    c.pub(topic, JSON.stringify(payload));
    const t0 = Date.now();
    const iv = setInterval(() => {
      if (done) { clearInterval(iv); resolve(done); }
      else if (Date.now() - t0 > (timeoutMs || 12000)) {
        clearInterval(iv);
        resolve({ ok: false, error: 'timeout ' + (timeoutMs || 12000) + 'ms' });
      }
    }, 50);
  });
}

async function main() {
  const t0 = Date.now();
  const snap = {
    channel: CHAN,
    generated_at: new Date().toISOString(),
    generated_ms: t0,
    broker: BROKER,
    note: '此文件由 GitHub Actions 定时生成。数据是【生成时刻】的，不是访问时刻的。',
    online: false,
    workers: [],
    probes: {},
    errors: [],
  };

  const c = new MqttWs(BROKER, {
    clientId: 'snap-' + crypto.randomBytes(3).toString('hex'),
    keepalive: 30, connectTimeout: 12000,
  });

  if (!(await c.connect())) {
    snap.errors.push('MQTT 连接失败');
    writeOut(snap);
    return;
  }

  /* ① 读 hello（retained），看谁在线 */
  const hellos = {};
  c.onMessage((t, p) => {
    if (t === HELLO) { try { const o = JSON.parse(p); if (o.chan === CHAN) hellos[o.name] = o; } catch (e) {} }
  });
  c.sub(HELLO);
  await sleep(3500);

  const now = Date.now();
  for (const w of Object.values(hellos)) {
    const age = w.ts ? Math.round((now - w.ts) / 1000) : null;
    snap.workers.push({
      name: w.name,
      services: w.services || [],
      durability: w.durability,
      allow: w.allow,
      heartbeat_age_s: age,
      /* ★ 心跳超过 120 秒就判定为「可能已死」 */
      alive: age !== null && age < 120,
    });
  }

  /* ② 对每个「心跳新鲜」的 worker 探一次 */
  const live = snap.workers.filter(w => w.alive);
  snap.online = live.length > 0;

  if (live.length) {
    c.sub(NS + 'reply');
    await sleep(1200);

    /* status */
    const st = await ask(c, { capability: 'status', params: {} });
    if (st && st.ok) {
      snap.probes.status = { ok: true, result: st.result, worker: st.worker, ms: st.ms };
    } else {
      snap.probes.status = { ok: false, error: (st && st.error) || 'no reply' };
      snap.errors.push('status 探测失败: ' + snap.probes.status.error);
    }

    /* list_services */
    const ls = await ask(c, { capability: 'list_services', params: {} });
    if (ls && ls.ok) {
      snap.probes.services = { ok: true, result: ls.result, worker: ls.worker };
    } else {
      snap.probes.services = { ok: false, error: (ls && ls.error) || 'no reply' };
    }

    /* echo.ping */
    const pg = await ask(c, { capability: 'invoke', params: { service: 'echo', op: 'ping' } });
    if (pg && pg.ok) {
      snap.probes.ping = { ok: true, result: pg.result, ms: pg.ms };
    } else {
      snap.probes.ping = { ok: false, error: (pg && pg.error) || 'no reply' };
      snap.errors.push('ping 探测失败: ' + snap.probes.ping.error);
    }
  } else {
    snap.errors.push('没有心跳新鲜的 worker —— 需要有人在设备上跑 worker.js');
  }

  snap.elapsed_ms = Date.now() - t0;
  c.close();
  writeOut(snap);
}

function writeOut(snap) {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(snap, null, 2) + '\n');
  console.log('[snapshot] → ' + OUT);
  console.log('  online: ' + snap.online);
  console.log('  workers: ' + snap.workers.map(w => w.name + '(' + (w.alive ? '活' : '假死') + ')').join(', ') || '无');
  console.log('  status: ' + JSON.stringify(snap.probes.status || null).slice(0, 100));
  console.log('  ping: ' + JSON.stringify(snap.probes.ping || null).slice(0, 100));
  if (snap.errors.length) console.log('  errors: ' + snap.errors.join(' | '));
}

main().catch(e => {
  console.error('[snapshot] 崩了: ' + e.message);
  writeOut({
    channel: CHAN, generated_at: new Date().toISOString(), generated_ms: Date.now(),
    online: false, workers: [], probes: {}, errors: ['脚本异常: ' + e.message],
  });
  process.exit(0);   /* ★ 不让 Actions 变红 —— 数据缺失也要产出文件 */
});
