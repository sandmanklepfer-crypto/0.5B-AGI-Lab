'use strict';
/*
 * 卤味小店 · 支付服务器
 *   - 顾客端下单 → 服务端按 data/*.json 重新算钱 → 生成微信 Native 支付码
 *   - 微信服务器回调 /api/pay/notify → 验签解密 → 标记已付款 → 通知老板
 */
const fs = require('fs');
const path = require('path');
const { URL } = require('url');
const { cfg, summary } = require('./lib/config');
const { createStore } = require('./lib/store');
const { WxPay, fromConfig } = require('./lib/wxpay');
const { json, text, match, readJson, readBody, serveStatic } = require('./lib/http');
const { pushToMerchant, pushChatToMerchant } = require('./lib/notify');
const { createLive } = require('./lib/live');
const { createChat } = require('./lib/chat');
const { createSocial } = require('./lib/social');
const qrcode = require('./vendor/qrcode.js');

const store = createStore(cfg);
const wx = fromConfig(cfg);
const live = createLive({ configPath: path.join(cfg.SHOP_ROOT, 'data', 'live.json') });
const chat = createChat({
  file: path.join(cfg.ROOT, 'data', 'chat.json'),
  onNewMessage: (thread, msg) => { pushChatToMerchant(thread, msg).catch(() => {}); },
});
const social = createSocial({
  file: path.join(cfg.ROOT, 'data', 'social.json'),
  onReport: (r) => { console.log('[social] 举报：' + r.byNick + ' → ' + r.targetNick + ' 理由：' + r.reason); },
});

/* ---------------- 读取店铺数据 ---------------- */
function readShop(p, fallback) {
  try { return JSON.parse(fs.readFileSync(path.join(cfg.SHOP_ROOT, 'data', p), 'utf8')); }
  catch (e) { return fallback; }
}
const loadProducts = () => readShop('products.json', { items: [], categories: [] });
const loadCoupons = () => readShop('coupons.json', { items: [] });
function loadSettings() {
  const def = { deliveryFee: 0, freeDeliveryOver: 0, minOrder: 0, acceptCash: true, shopName: '卤味小店' };
  return Object.assign(def, readShop('settings.json', {}));
}

/* ---------------- 服务端算钱（防止前端改价） ---------------- */
function calcOrder(payload) {
  const products = loadProducts();
  const coupons = loadCoupons();
  const settings = loadSettings();
  const items = [];
  let sub = 0;

  for (const line of (payload.items || [])) {
    const p = (products.items || []).find(x => x.id === line.id);
    if (!p || p.on === false) throw new Error('商品不存在或已下架：' + line.id);
    const qty = Math.max(1, Math.min(999, parseInt(line.qty, 10) || 0));
    if (Number(p.stock) > 0 && qty > Number(p.stock)) throw new Error(`「${p.name}」库存不足`);
    const sum = Math.round(Number(p.price) * qty * 100) / 100;
    items.push({ id: p.id, name: p.name, unit: p.unit || '份', price: Number(p.price), qty, sum });
    sub += sum;
  }
  if (!items.length) throw new Error('购物车是空的');
  sub = Math.round(sub * 100) / 100;

  const minOrder = Number(settings.minOrder) || 0;
  if (sub < minOrder) throw new Error(`满 ¥${minOrder} 才起送`);

  // 配送费
  let fee = Number(settings.deliveryFee) || 0;
  if (Number(settings.freeDeliveryOver) > 0 && sub >= Number(settings.freeDeliveryOver)) fee = 0;

  // 优惠券
  let dis = 0, couponCode = '';
  if (payload.coupon) {
    const cp = (coupons.items || []).find(c => String(c.code).toUpperCase() === String(payload.coupon).toUpperCase());
    if (cp && cp.on !== false) {
      const today = new Date().toISOString().slice(0, 10);
      const okDate = (!cp.start || today >= cp.start) && (!cp.end || today <= cp.end);
      const okMin = sub >= (Number(cp.min) || 0);
      const okTotal = !cp.total || Number(cp.used || 0) < Number(cp.total);
      if (okDate && okMin && okTotal) {
        if (cp.type === 'percent') dis = sub * (1 - (Number(cp.value) || 100) / 100);
        else if (cp.type === 'freeship') { dis = fee; fee = 0; }
        else dis = Math.min(Number(cp.value) || 0, sub);
        dis = Math.round(dis * 100) / 100;
        couponCode = cp.code;
      }
    }
  }

  const total = Math.round(Math.max(0, sub + fee - dis) * 100) / 100;
  if (!(total > 0)) throw new Error('金额不正确');
  return { items, sub, fee, dis, total, coupon: couponCode, shop: settings.shopName, want: payload.want || '' };
}

async function newOutTradeNo() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  let no;
  do {
    no = 'LH' + String(d.getFullYear()).slice(2) + p(d.getMonth() + 1) + p(d.getDate()) +
      p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds()) +
      String(Math.floor(Math.random() * 9000) + 1000);
  } while (await store.get(no));
  return no;
}

/* ---------------- 二维码 SVG ---------------- */
function qrSvg(data, cell = 6, margin = 8) {
  const qr = qrcode(0, 'M');
  qr.addData(data);
  qr.make();
  return qr.createSvgTag({ cellSize: cell, margin, scalable: true });
}

/* ---------------- 微信回调处理 ---------------- */
let notifyInFlight = false;
async function handleNotify(req, res) {
  const raw = await readBody(req, 1024 * 1024);

  /* 1) 验签 —— 不通过直接 401，微信会重试 */
  let result;
  try {
    result = wx.verifyNotify(req.headers, raw);
  } catch (e) {
    console.error('[notify] 验签失败：', e.message);
    json(res, 401, { code: 'FAIL', message: e.message });
    return;
  }

  const d = result.decrypted;
  if (!d || result.event.event_type !== 'TRANSACTION.SUCCESS') {
    json(res, 200, { code: 'SUCCESS', message: 'OK' });   // 非成功事件，收了就行
    return;
  }

  /* 2) 先落库，再应答 —— 避免"应答了但没存上"导致丢单 */
  const no = d.out_trade_no;
  let updated = null;
  try {
    const order = await store.get(no);
    if (!order) {
      console.warn('[notify] 未找到订单 ' + no + '（可能已被清理）');
    } else if (order.status === 'PAID') {
      // 幂等：重复回调不重复处理
    } else {
      const paidFen = (d.amount && d.amount.payer_total) || (d.amount && d.amount.total) || 0;
      const expectFen = Math.round(order.total * 100);
      if (paidFen !== expectFen) {
        console.error(`[notify] ⚠️ 金额不一致！订单 ${no} 应付 ${expectFen} 实付 ${paidFen}`);
        await store.update(no, { status: 'AMOUNT_MISMATCH', paidFen, raw: d });
      } else {
        updated = await store.update(no, {
          status: 'PAID',
          paidAt: Date.now(),
          transactionId: d.transaction_id,
          paidFen,
          payerOpenid: d.payer && d.payer.openid,
        });
        console.log(`[notify] ✅ 订单 ${no} 已付款 ¥${(paidFen / 100).toFixed(2)}`);
      }
    }
  } catch (e) {
    // 存储失败 → 返回失败让微信重试，别丢单
    console.error('[notify] 落库失败，让微信重试：', e.message);
    json(res, 500, { code: 'FAIL', message: 'store error' });
    return;
  }

  json(res, 200, { code: 'SUCCESS', message: 'OK' });

  /* 3) 通知老板（异步，不影响应答） */
  if (updated) pushToMerchant(updated).catch(e => console.warn('[notify] 通知失败', e.message));
}

/* ---------------- 路由 ---------------- */
const { Buffer: B } = require('buffer');

function clientIp(req) {
  const xf = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  return xf || (req.socket && req.socket.remoteAddress) || 'unknown';
}

function isAdmin(req) {
  const auth = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  return !!(cfg.adminToken && auth === cfg.adminToken);
}

async function route(req, res) {
  const u = new URL(req.url, 'http://localhost');
  const p = u.pathname;
  const method = req.method.toUpperCase();

  // CORS 预检
  if (method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type,Authorization',
      'Access-Control-Max-Age': '86400',
    });
    res.end(); return true;
  }

  /* --- 健康检查 --- */
  if (p === '/api/health') { json(res, 200, { ok: true, ...summary(), time: Date.now() }); return true; }

  /* --- 生成二维码图片（给前端展示 code_url 用） --- */
  if (p === '/api/qr.svg') {
    const data = u.searchParams.get('text') || '';
    const cell = Math.min(14, Math.max(3, Number(u.searchParams.get('cell')) || 6));
    if (!data) { text(res, 400, 'missing text'); return true; }
    res.writeHead(200, { 'Content-Type': 'image/svg+xml', 'Cache-Control': 'public, max-age=86400' });
    res.end(qrSvg(data, cell));
    return true;
  }

  /* --- 下单 --- */
  if (p === '/api/orders/create' && method === 'POST') {
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    if (!body.name || !/^1[3-9]\d{9}$/.test(String(body.phone || ''))) {
      json(res, 400, { ok: false, error: '收货人或手机号不正确' }); return true;
    }
    if (!body.address || String(body.address).trim().length < 5) {
      json(res, 400, { ok: false, error: '地址写详细一点' }); return true;
    }
    let calc;
    try { calc = calcOrder(body); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }

    const outTradeNo = await newOutTradeNo();
    const order = Object.assign({
      outTradeNo,
      status: 'PENDING',
      createdAt: Date.now(),
      name: String(body.name).trim(),
      phone: String(body.phone).trim(),
      address: String(body.address).trim(),
      want: String(body.want || '').trim(),
      note: String(body.note || '').trim(),
      payMethod: 'wechat',
    }, calc);
    await store.create(order);
    console.log(`[order] 新建 ${outTradeNo} ¥${order.total}`);

    const base = cfg.publicBaseUrl || ('http://' + (req.headers.host || ('localhost:' + cfg.port)));
    json(res, 200, { ok: true, outTradeNo, total: order.total, payUrl: base + '/pay.html?no=' + outTradeNo });
    return true;
  }

  /* --- 查订单 --- */
  let m = match('/api/orders/:no', p);
  if (m && method === 'GET') {
    const o = await store.get(m.no);
    if (!o) { json(res, 404, { ok: false, error: '订单不存在' }); return true; }
    json(res, 200, {
      ok: true,
      order: {
        outTradeNo: o.outTradeNo, status: o.status, total: o.total,
        items: o.items, sub: o.sub, fee: o.fee, dis: o.dis,
        name: o.name, want: o.want, shop: o.shop, createdAt: o.createdAt,
        paidAt: o.paidAt || null,
      },
    });
    return true;
  }

  /* --- 生成支付码（Native 下单） --- */
  if (p === '/api/pay/prepay' && method === 'POST') {
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const o = await store.get(body.outTradeNo);
    if (!o) { json(res, 404, { ok: false, error: '订单不存在' }); return true; }
    if (o.status === 'PAID') { json(res, 200, { ok: true, paid: true, status: o.status }); return true; }
    if (o.codeUrl) { json(res, 200, { ok: true, codeUrl: o.codeUrl, paid: false, status: o.status, total: o.total }); return true; }

    if (cfg.mock) {
      const codeUrl = 'weixin://wxpay/bizpayurl?pr=MOCK' + o.outTradeNo.slice(-8);
      await store.update(o.outTradeNo, { codeUrl });
      json(res, 200, { ok: true, codeUrl, paid: false, mock: true, total: o.total });
      return true;
    }

    try {
      const r = await wx.nativeTransaction({
        description: (o.shop || '卤味小店') + ' - ' + o.items.map(i => i.name + '×' + i.qty).join(' '),
        outTradeNo: o.outTradeNo,
        amountFen: Math.round(o.total * 100),
        notifyUrl: cfg.notifyUrl,
        attach: 'luhuo',
      });
      if (!r || !r.code_url) throw new Error('微信未返回 code_url');
      await store.update(o.outTradeNo, { codeUrl: r.code_url });
      json(res, 200, { ok: true, codeUrl: r.code_url, paid: false, status: o.status, total: o.total });
    } catch (e) {
      console.error('[prepay] 失败', e.message, e.data || '');
      json(res, 500, { ok: false, error: '生成支付码失败：' + e.message, detail: e.data || null });
    }
    return true;
  }

  /* --- 轮询支付状态（顺带主动查单兜底） --- */
  if (p === '/api/pay/status' && method === 'GET') {
    const o = await store.get(u.searchParams.get('outTradeNo') || '');
    if (!o) { json(res, 404, { ok: false, error: '订单不存在' }); return true; }
    // 兜底：万一回调没到，顾客轮询时主动向微信查一次单
    if (o.status === 'PENDING' && !cfg.mock && o.codeUrl && !notifyInFlight) {
      notifyInFlight = true;
      wx.queryByOutTradeNo(o.outTradeNo).then(async q => {
        if (q && q.trade_state === 'SUCCESS') {
          const paidFen = (q.amount && (q.amount.payer_total || q.amount.total)) || 0;
          if (paidFen === Math.round(o.total * 100)) {
            const up = await store.update(o.outTradeNo, { status: 'PAID', paidAt: Date.now(), transactionId: q.transaction_id, paidFen });
            if (up) pushToMerchant(up).catch(() => {});
          }
        }
      }).catch(() => {}).finally(() => { notifyInFlight = false; });
    }
    json(res, 200, { ok: true, status: o.status, total: o.total, paidAt: o.paidAt || null });
    return true;
  }

  /* --- 微信支付回调 --- */
  if (p === cfg.notifyPath && method === 'POST') {
    await handleNotify(req, res);
    return true;
  }

  /* --- 演示模式：手动标记已付 --- */
  if (p === '/api/pay/mock' && method === 'POST') {
    if (!cfg.mock) { json(res, 403, { ok: false, error: '仅演示模式可用' }); return true; }
    const body = await readJson(req);
    const o = await store.get(body.outTradeNo);
    if (!o) { json(res, 404, { ok: false, error: '订单不存在' }); return true; }
    const up = await store.update(o.outTradeNo, { status: 'PAID', paidAt: Date.now(), transactionId: 'MOCK' + Date.now() });
    if (up) pushToMerchant(up).catch(() => {});
    json(res, 200, { ok: true, status: 'PAID' });
    return true;
  }

  /* ================= 直播 ================= */

  /* --- 直播配置（公开，前端要用） --- */
  if (p === '/api/live/config' && method === 'GET') {
    const c = live.readConfig();
    json(res, 200, { ok: true, live: c, viewers: live.viewerCount() });
    return true;
  }

  /* --- 心跳（算在线人数） --- */
  if (p === '/api/live/ping' && method === 'POST') {
    live.heartbeat(clientIp(req));
    json(res, 200, { ok: true, viewers: live.viewerCount() });
    return true;
  }

  /* --- 拉取聊天 --- */
  if (p === '/api/live/chat' && method === 'GET') {
    live.heartbeat(clientIp(req));
    json(res, 200, {
      ok: true,
      messages: live.getChat(u.searchParams.get('since')),
      viewers: live.viewerCount(),
    });
    return true;
  }

  /* --- 发聊天 --- */
  if (p === '/api/live/chat' && method === 'POST') {
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = live.addChat({ name: body.name, text: body.text, ip: clientIp(req) });
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* ================= 交友聊天（匿名社交） ================= */

  /* --- 进入 / 改昵称 --- */
  if (p === '/api/social/join' && method === 'POST') {
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = social.join({ uid: b.uid, nick: b.nick, avatar: b.avatar });
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 心跳 + 在线列表 --- */
  if (p === '/api/social/online' && method === 'GET') {
    const uid = u.searchParams.get('uid') || '';
    social.heartbeat(uid);
    json(res, 200, {
      ok: true,
      me: social.myself(uid),
      list: social.online(uid, u.searchParams.get('q')),
      stats: social.stats(),
    });
    return true;
  }

  /* --- 大厅：拉取 --- */
  if (p === '/api/social/hall' && method === 'GET') {
    social.heartbeat(u.searchParams.get('uid') || '');
    const r = social.hallFetch(u.searchParams.get('uid'), u.searchParams.get('since'));
    json(res, 200, Object.assign(r, { stats: social.stats() }));
    return true;
  }

  /* --- 大厅：发言 --- */
  if (p === '/api/social/hall' && method === 'POST') {
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    social.heartbeat(b.uid);
    const r = social.hallSend(b.uid, b.text);
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 私聊：会话列表 --- */
  if (p === '/api/social/dms' && method === 'GET') {
    social.heartbeat(u.searchParams.get('uid') || '');
    json(res, 200, { ok: true, list: social.dmList(u.searchParams.get('uid')) });
    return true;
  }

  /* --- 私聊：拉取 --- */
  if (p === '/api/social/dm' && method === 'GET') {
    social.heartbeat(u.searchParams.get('uid') || '');
    const r = social.dmFetch(u.searchParams.get('uid'), u.searchParams.get('peer'),
      u.searchParams.get('since'), u.searchParams.get('read') !== '0');
    json(res, 200, r);
    return true;
  }

  /* --- 私聊：发送 --- */
  if (p === '/api/social/dm' && method === 'POST') {
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    social.heartbeat(b.uid);
    const r = social.dmSend(b.uid, b.to, b.text);
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 拉黑 --- */
  if (p === '/api/social/block' && method === 'POST') {
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = social.block(b.uid, b.target, b.on !== false);
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 举报 --- */
  if (p === '/api/social/report' && method === 'POST') {
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = social.report(b.uid, b.target, b.reason, b.msg);
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 老板：看举报 --- */
  if (p === '/api/admin/social/reports' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    json(res, 200, { ok: true, reports: social.adminReports(), stats: social.stats() });
    return true;
  }

  /* --- 老板：封禁/解封 --- */
  if (p === '/api/admin/social/ban' && method === 'POST') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    let b; try { b = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    json(res, 200, social.adminBan(b.uid, b.on !== false));
    return true;
  }

  /* ================= 私域聊天 ================= */

  /* --- 顾客：拉自己的消息 --- */
  if (p === '/api/chat' && method === 'GET') {
    const phone = u.searchParams.get('phone') || '';
    const r = chat.customerFetch(phone, u.searchParams.get('since'));
    json(res, 200, r);
    return true;
  }

  /* --- 顾客：发消息 --- */
  if (p === '/api/chat' && method === 'POST') {
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = chat.customerSend({ phone: body.phone, name: body.name, text: body.text, ip: clientIp(req) });
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 老板：会话列表 --- */
  if (p === '/api/admin/chat/threads' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    json(res, 200, { ok: true, threads: chat.merchantThreads(), unread: chat.totalUnread() });
    return true;
  }

  /* --- 老板：读某个会话 --- */
  if (p === '/api/admin/chat/thread' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    const t = chat.merchantThread(
      u.searchParams.get('phone'),
      u.searchParams.get('read') !== '0',
      u.searchParams.get('since')
    );
    if (!t) { json(res, 404, { ok: false, error: '没有这个会话' }); return true; }
    json(res, 200, { ok: true, thread: t });
    return true;
  }

  /* --- 老板：回复 --- */
  if (p === '/api/admin/chat/reply' && method === 'POST') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    const r = chat.merchantSend({ phone: body.phone, text: body.text });
    json(res, r.ok ? 200 : 400, r);
    return true;
  }

  /* --- 老板：删会话 --- */
  if (p === '/api/admin/chat/thread' && method === 'DELETE') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    chat.clearThread(u.searchParams.get('phone'));
    json(res, 200, { ok: true });
    return true;
  }

  /* --- 老板：改直播设置 --- */
  if (p === '/api/admin/live' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    json(res, 200, { ok: true, live: live.readConfig(), viewers: live.viewerCount() });
    return true;
  }
  if (p === '/api/admin/live' && method === 'POST') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }
    try {
      const c = live.writeConfig(body);
      console.log('[live] 设置已更新：on=' + c.on + ' mode=' + c.mode);
      json(res, 200, { ok: true, live: c });
    } catch (e) {
      json(res, 500, { ok: false, error: '保存失败：' + e.message });
    }
    return true;
  }

  /* --- 老板：清空聊天 --- */
  if (p === '/api/admin/live/chat' && method === 'DELETE') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    live.clearChat();
    json(res, 200, { ok: true });
    return true;
  }

  /* --- 老板查订单（需要 ADMIN_TOKEN） --- */
  if (p === '/api/admin/orders' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    json(res, 200, { ok: true, orders: await store.list() });
    return true;
  }

  /* --- 老板改店铺设置（联系方式等，直接写服务器上的 settings.json） ---
     这样不用 GitHub Token 也能改联系方式。 */
  if (p === '/api/admin/settings' && method === 'GET') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    json(res, 200, { ok: true, settings: loadSettings() });
    return true;
  }
  if (p === '/api/admin/settings' && method === 'POST') {
    if (!isAdmin(req)) { json(res, 403, { ok: false, error: '无权限' }); return true; }
    let body;
    try { body = await readJson(req); } catch (e) { json(res, 400, { ok: false, error: e.message }); return true; }

    // 只允许改这些"展示用"字段，避免改坏价格/库存
    const ALLOW = ['shopName', 'slogan', 'notice', 'phone', 'wechat', 'hours',
      'deliveryArea', 'deliveryFee', 'freeDeliveryOver', 'minOrder',
      'deliveryTimeOptions', 'payNote', 'acceptCash'];
    const file = path.join(cfg.SHOP_ROOT, 'data', 'settings.json');
    let cur = {};
    try { cur = JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { cur = {}; }

    const changed = [];
    for (const k of ALLOW) {
      if (body[k] === undefined) continue;
      let v = body[k];
      if (['deliveryFee', 'freeDeliveryOver', 'minOrder'].indexOf(k) >= 0) v = Number(v) || 0;
      if (k === 'deliveryTimeOptions' && typeof v === 'string') {
        v = v.split(/[,，]/).map(x => x.trim()).filter(Boolean);
      }
      if (k === 'acceptCash') v = !!v;
      if (typeof v === 'string') v = v.trim();
      cur[k] = v;
      changed.push(k);
    }

    // 手机号做基本校验，避免填错导致顾客打不通
    if (cur.phone && !/^[\d\-+() ]{5,20}$/.test(cur.phone)) {
      json(res, 400, { ok: false, error: '电话号码格式看着不对' }); return true;
    }
    if (!cur.phone && !cur.wechat) {
      json(res, 400, { ok: false, error: '电话和微信至少要填一个，不然顾客联系不上你' }); return true;
    }

    try {
      const tmp = file + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(cur, null, 2));
      fs.renameSync(tmp, file);
    } catch (e) {
      json(res, 500, { ok: false, error: '保存失败：' + e.message });
      return true;
    }
    console.log('[admin] 店铺设置已更新：' + changed.join(', '));
    json(res, 200, { ok: true, settings: cur, changed });
    return true;
  }

  return false;
}

module.exports = { route, store, summary, cfg, calcOrder, qrSvg };
