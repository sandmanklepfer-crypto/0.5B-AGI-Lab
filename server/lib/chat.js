'use strict';
/*
 * 私域聊天（顾客 ↔ 商家）
 *
 * 身份：用手机号当会话 ID —— 顾客下单时已经填过，且被记住了。
 *      不用注册、不用登录，顾客无感。
 *
 * 存储：JSON 文件（和订单一样，可切 GitHub）
 *   { threads: { "13800138000": {phone,name,msgs:[],unread,lastAt,lastText} } }
 *
 * 消息：{ id, from:'c'|'m', text, at, read }
 *   from='c' 顾客发的，from='m' 商家发的
 */
const fs = require('fs');
const path = require('path');

const MAX_THREADS = 800;
const MAX_PER_THREAD = 400;
const RATE_MS = 1500;        // 同一人两条消息最短间隔
const MAX_LEN = 500;
const WELCOME = '你好～我是老板，有什么想问的直接说，看到就回你 👋';

function createChat(opts) {
  const file = opts.file;
  const onNewMessage = opts.onNewMessage || (() => {});

  let data = { threads: {} };
  try {
    const dir = path.dirname(file);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(file)) data = JSON.parse(fs.readFileSync(file, 'utf8') || '{"threads":{}}');
  } catch (e) { console.warn('[chat] 读取失败，重建：' + e.message); }
  if (!data.threads) data.threads = {};
  if (!data.seq) data.seq = 0;

  function persist() {
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
    fs.renameSync(tmp, file);
  }

  const lastPost = new Map();   // phone -> ts

  function normPhone(p) {
    return String(p == null ? '' : p).replace(/[^\d]/g, '').slice(0, 20);
  }

  function clean(s, max) {
    return String(s == null ? '' : s)
      .replace(/[\u0000-\u001f\u007f]/g, '')
      .replace(/\r/g, '')
      .trim()
      .slice(0, max || MAX_LEN);
  }

  function getThread(phone, create) {
    const k = normPhone(phone);
    if (!k) return null;
    if (!data.threads[k]) {
      if (!create) return null;
      // 会话数上限，防止被刷爆
      const n = Object.keys(data.threads).length;
      if (n >= MAX_THREADS) {
        // 淘汰最久没说话的
        const oldest = Object.entries(data.threads)
          .sort((a, b) => (a[1].lastAt || 0) - (b[1].lastAt || 0))[0];
        if (oldest) delete data.threads[oldest[0]];
      }
      data.threads[k] = {
        phone: k, name: '', msgs: [], unread: 0,
        lastAt: Date.now(), lastText: '', createdAt: Date.now(),
      };
      // 首条欢迎语
      data.threads[k].msgs.push({ id: ++data.seq, from: 'm', text: WELCOME, at: Date.now(), read: true });
    }
    return data.threads[k];
  }

  /* ---------- 顾客发消息 ---------- */
  function customerSend({ phone, name, text, ip }) {
    const k = normPhone(phone);
    if (!/^\d{6,20}$/.test(k)) return { ok: false, error: '手机号不对' };

    const now = Date.now();
    const last = lastPost.get(k) || 0;
    if (now - last < RATE_MS) return { ok: false, error: '发太快了，慢一点～' };
    lastPost.set(k, now);

    const t = clean(text);
    if (!t) return { ok: false, error: '内容不能为空' };
    if (/(https?:\/\/|www\.)/i.test(t)) return { ok: false, error: '不能发链接' };

    const th = getThread(k, true);
    if (name) th.name = clean(name, 20);
    // 时间戳取"建会话之后"，保证欢迎语排在最前
    const at = Math.max(now, Date.now());
    const msg = { id: ++data.seq, from: 'c', text: t, at, read: false };
    th.msgs.push(msg);
    if (th.msgs.length > MAX_PER_THREAD) th.msgs = th.msgs.slice(-MAX_PER_THREAD);
    th.unread = (th.unread || 0) + 1;
    th.lastAt = at;
    th.lastText = t.slice(0, 60);
    persist();

    try { onNewMessage(th, msg); } catch (e) { /* 通知失败不影响 */ }
    return { ok: true, msg };
  }

  /* ---------- 商家回复 ---------- */
  function merchantSend({ phone, text }) {
    const th = getThread(phone, false);
    if (!th) return { ok: false, error: '没有这个会话' };
    const t = clean(text);
    if (!t) return { ok: false, error: '内容不能为空' };
    const msg = { id: ++data.seq, from: 'm', text: t, at: Date.now(), read: true };
    th.msgs.push(msg);
    if (th.msgs.length > MAX_PER_THREAD) th.msgs = th.msgs.slice(-MAX_PER_THREAD);
    th.lastAt = msg.at;
    th.lastText = t.slice(0, 60);
    persist();
    return { ok: true, msg };
  }

  /* ---------- 读会话（顾客侧） ---------- */
  function customerFetch(phone, since) {
    const th = getThread(phone, false);
    if (!th) return { ok: true, messages: [], has: false };
    const s = Number(since) || 0;
    const list = th.msgs.filter(m => m.id > s);
    // 顾客看了，把商家的消息标记已读（顾客侧无未读概念，这里只记录）
    return { ok: true, messages: list, has: true, name: th.name };
  }

  /* ---------- 读会话（商家侧） ---------- */
  function merchantThreads() {
    return Object.values(data.threads)
      .map(t => ({
        phone: t.phone, name: t.name || '', unread: t.unread || 0,
        lastAt: t.lastAt || 0, lastText: t.lastText || '',
        count: (t.msgs || []).length,
      }))
      .sort((a, b) => (b.lastAt || 0) - (a.lastAt || 0));
  }

  function merchantThread(phone, markRead, since) {
    const th = getThread(phone, false);
    if (!th) return null;
    if (markRead && th.unread) { th.unread = 0; persist(); }
    const s = Number(since) || 0;
    // 传了 since 就只给增量，省流量（隧道场景很重要）
    const msgs = s > 0
      ? th.msgs.filter(m => (m.id || 0) > s)
      : th.msgs.slice(-MAX_PER_THREAD);
    // 增量模式下也把"已读"回应一下，方便前端知道全量状态
    return { phone: th.phone, name: th.name || '', msgs, unread: th.unread || 0, since: s };
  }

  function totalUnread() {
    return Object.values(data.threads).reduce((a, t) => a + (t.unread || 0), 0);
  }

  function clearThread(phone) {
    const th = getThread(phone, false);
    if (!th) return false;
    delete data.threads[normPhone(phone)];
    persist();
    return true;
  }

  return {
    customerSend, merchantSend, customerFetch,
    merchantThreads, merchantThread, totalUnread, clearThread,
    WELCOME,
  };
}

module.exports = { createChat };
