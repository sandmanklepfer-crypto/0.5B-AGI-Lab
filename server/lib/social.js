'use strict';
/*
 * 交友聊天（匿名社交）
 *
 * 设计要点：
 *  1) 不收集手机号 —— 只用客户端随机生成的匿名 ID（uid），保护隐私
 *  2) 一个公共大厅 + 一对一私聊
 *  3) 陌生人社交必备的安全能力：限流、敏感词、拉黑、举报
 *
 * 存储：JSON 文件
 *   { users:{uid:{...}}, hall:{msgs:[]}, dms:{"a|b":{msgs:[]}}, reports:[], seq }
 */
const fs = require('fs');
const path = require('path');

const MAX_USERS = 3000;
const MAX_HALL = 200;          // 大厅只留最近 200 条
const MAX_DM = 400;            // 每个私聊留最近 400 条
const HALL_RATE = 3000;        // 大厅 3 秒一条
const DM_RATE = 1200;          // 私聊 1.2 秒一条
const MAX_LEN = 300;
const ONLINE_TTL = 45000;      // 45 秒内有心跳算在线

// 交友场景的高危词（防诈骗/引流），商家可再补充
const DEFAULT_BAD = [
  '加微信', '加v', '微信号', '转钱', '汇款', '借钱', '刷单', '兼职',
  '投资', '理财', '博彩', '赌博', '返利', '贷款', '裸聊', '约炮',
];

function createSocial(opts) {
  const file = opts.file;
  const onReport = opts.onReport || (() => {});

  let db = { users: {}, hall: { msgs: [] }, dms: {}, reports: [], seq: 0 };
  try {
    const dir = path.dirname(file);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(file)) db = Object.assign(db, JSON.parse(fs.readFileSync(file, 'utf8') || '{}'));
  } catch (e) { console.warn('[social] 读取失败，重建：' + e.message); }
  if (!db.users) db.users = {};
  if (!db.hall || !Array.isArray(db.hall.msgs)) db.hall = { msgs: [] };
  if (!db.dms) db.dms = {};
  if (!Array.isArray(db.reports)) db.reports = [];
  if (!db.seq) db.seq = 0;

  const lastPost = new Map();   // uid -> ts

  function persist() {
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(db, null, 2));
    fs.renameSync(tmp, file);
  }

  function clean(s, max) {
    return String(s == null ? '' : s).replace(/[\u0000-\u001f\u007f]/g, '').replace(/\s+/g, ' ').trim().slice(0, max || MAX_LEN);
  }

  const normUid = u => String(u == null ? '' : u).replace(/[^\w-]/g, '').slice(0, 32);

  function dmKey(a, b) { return [a, b].sort().join('|'); }

  /* ---------- 用户 ---------- */
  function join({ uid, nick, avatar }) {
    const u = normUid(uid);
    if (u.length < 6) return { ok: false, error: '身份标识无效' };
    const n = clean(nick, 16);
    if (!n) return { ok: false, error: '起个昵称吧' };

    if (!db.users[u] && Object.keys(db.users).length >= MAX_USERS) {
      // 淘汰最久没上线的
      const oldest = Object.entries(db.users).sort((a, b) => (a[1].lastSeen || 0) - (b[1].lastSeen || 0))[0];
      if (oldest) delete db.users[oldest[0]];
    }

    const cur = db.users[u] || {
      uid: u, nick: n, avatar: '🙂', createdAt: Date.now(),
      blocked: [], reports: 0, banned: false,
    };
    if (cur.banned) return { ok: false, error: '这个身份已被封禁' };
    cur.nick = n;
    if (avatar) cur.avatar = clean(avatar, 4) || cur.avatar;
    cur.lastSeen = Date.now();
    db.users[u] = cur;
    persist();
    return { ok: true, user: { uid: u, nick: cur.nick, avatar: cur.avatar } };
  }

  function heartbeat(uid) {
    const u = normUid(uid);
    const t = db.users[u];
    if (t) { t.lastSeen = Date.now(); }
    return { ok: !!t };
  }

  function online(uid, q) {
    const me = normUid(uid);
    const now = Date.now();
    const kw = clean(q, 20);
    const out = [];
    for (const u of Object.values(db.users)) {
      if (u.banned) continue;
      if (now - (u.lastSeen || 0) > ONLINE_TTL) continue;
      if (u.uid === me) continue;
      if (me && (u.blocked || []).includes(me)) continue;
      if (kw && u.nick.indexOf(kw) < 0) continue;
      out.push({
        uid: u.uid, nick: u.nick, avatar: u.avatar,
        online: true,
        blocked: me ? (db.users[me] && (db.users[me].blocked || []).includes(u.uid)) : false,
      });
    }
    out.sort((a, b) => a.nick.localeCompare(b.nick, 'zh'));
    return out.slice(0, 100);
  }

  function myself(uid) {
    const u = db.users[normUid(uid)];
    if (!u) return null;
    return { uid: u.uid, nick: u.nick, avatar: u.avatar, blocked: (u.blocked || []).length };
  }

  /* ---------- 敏感词 ---------- */
  function hitBad(text) {
    const t = text.toLowerCase();
    return DEFAULT_BAD.filter(w => t.includes(w.toLowerCase()));
  }

  /* ---------- 限流 ---------- */
  function allow(uid, ms) {
    const now = Date.now();
    const last = lastPost.get(uid) || 0;
    if (now - last < ms) return false;
    lastPost.set(uid, now);
    return true;
  }

  /* ---------- 公共大厅 ---------- */
  function hallSend(uid, text) {
    const u = normUid(uid);
    const me = db.users[u];
    if (!me) return { ok: false, error: '先设置昵称' };
    if (me.banned) return { ok: false, error: '你已被封禁' };
    if (!allow('h:' + u, HALL_RATE)) return { ok: false, error: '发太快了，慢一点～' };

    const t = clean(text);
    if (!t) return { ok: false, error: '内容不能为空' };
    if (/(https?:\/\/|www\.|\d{6,})/i.test(t)) return { ok: false, error: '不能发链接或联系方式' };
    const bad = hitBad(t);
    if (bad.length) return { ok: false, error: '包含不允许的词：' + bad[0] };

    me.lastSeen = Date.now();
    const msg = { id: ++db.seq, from: { uid: u, nick: me.nick, avatar: me.avatar }, text: t, at: Date.now() };
    db.hall.msgs.push(msg);
    if (db.hall.msgs.length > MAX_HALL) db.hall.msgs = db.hall.msgs.slice(-MAX_HALL);
    persist();
    return { ok: true, msg };
  }

  function hallFetch(uid, since) {
    const u = normUid(uid);
    const me = db.users[u];
    const s = Number(since) || 0;
    const blockSet = new Set((me && me.blocked) || []);
    const list = db.hall.msgs
      .filter(m => m.id > s && !blockSet.has(m.from.uid))
      .slice(-100);
    return { ok: true, messages: list };
  }

  /* ---------- 私聊 ---------- */
  function dmSend(uid, to, text) {
    const u = normUid(uid), t2 = normUid(to);
    const me = db.users[u], peer = db.users[t2];
    if (!me) return { ok: false, error: '先设置昵称' };
    if (!peer) return { ok: false, error: '对方不在了' };
    if ((peer.blocked || []).includes(u)) return { ok: false, error: '对方已把你拉黑' };
    if ((me.blocked || []).includes(t2)) return { ok: false, error: '你先解除拉黑才能发' };
    if (!allow('d:' + u, DM_RATE)) return { ok: false, error: '发太快了' };

    const t = clean(text);
    if (!t) return { ok: false, error: '内容不能为空' };
    if (/(https?:\/\/|www\.|\d{6,})/i.test(t)) return { ok: false, error: '不能发链接或联系方式' };
    const bad = hitBad(t);
    if (bad.length) return { ok: false, error: '包含不允许的词：' + bad[0] };

    me.lastSeen = Date.now();
    const k = dmKey(u, t2);
    if (!db.dms[k]) db.dms[k] = { msgs: [], read: {} };
    const msg = { id: ++db.seq, from: u, text: t, at: Date.now() };
    db.dms[k].msgs.push(msg);
    if (db.dms[k].msgs.length > MAX_DM) db.dms[k].msgs = db.dms[k].msgs.slice(-MAX_DM);
    persist();
    return { ok: true, msg };
  }

  function dmFetch(uid, peer, since, markRead) {
    const u = normUid(uid), p = normUid(peer);
    if (!db.users[u]) return { ok: false, error: '先设置昵称' };
    const k = dmKey(u, p);
    const th = db.dms[k];
    if (!th) return { ok: true, messages: [] };
    if (markRead) { th.read = th.read || {}; th.read[u] = Date.now(); persist(); }
    const s = Number(since) || 0;
    return { ok: true, messages: th.msgs.filter(m => m.id > s).slice(-200) };
  }

  // 会话列表：跟谁聊过、最后一句、未读数
  function dmList(uid) {
    const u = normUid(uid);
    if (!db.users[u]) return [];
    const out = [];
    for (const [k, th] of Object.entries(db.dms)) {
      const parts = k.split('|');
      if (!parts.includes(u)) continue;
      const peer = parts[0] === u ? parts[1] : parts[0];
      const pu = db.users[peer];
      if (!pu) continue;
      const last = th.msgs[th.msgs.length - 1];
      if (!last) continue;
      const seen = (th.read || {})[u] || 0;
      const unread = th.msgs.filter(m => m.from !== u && m.at > seen).length;
      out.push({
        uid: peer, nick: pu.nick, avatar: pu.avatar,
        lastText: last.text, lastAt: last.at, unread,
      });
    }
    out.sort((a, b) => b.lastAt - a.lastAt);
    return out.slice(0, 100);
  }

  /* ---------- 拉黑 / 举报 ---------- */
  function block(uid, target, on) {
    const u = normUid(uid), t = normUid(target);
    const me = db.users[u];
    if (!me) return { ok: false, error: '先设置昵称' };
    me.blocked = me.blocked || [];
    if (on) { if (!me.blocked.includes(t)) me.blocked.push(t); }
    else me.blocked = me.blocked.filter(x => x !== t);
    persist();
    return { ok: true, blocked: me.blocked.length };
  }

  function report(uid, target, text, msgText) {
    const u = normUid(uid), t = normUid(target);
    if (!db.users[u]) return { ok: false, error: '先设置昵称' };
    const rec = {
      id: ++db.seq, by: u, byNick: db.users[u].nick,
      target: t, targetNick: (db.users[t] || {}).nick || t,
      reason: clean(text, 100) || '未说明', msg: clean(msgText, 200),
      at: Date.now(),
    };
    db.reports.push(rec);
    if (db.reports.length > 500) db.reports = db.reports.slice(-500);
    const tu = db.users[t];
    if (tu) tu.reports = (tu.reports || 0) + 1;
    persist();
    try { onReport(rec); } catch (e) { /* 通知失败不影响 */ }
    return { ok: true };
  }

  /* ---------- 管理 ---------- */
  function adminReports() {
    return db.reports.slice(-200).reverse();
  }
  function adminBan(uid, on) {
    const u = db.users[normUid(uid)];
    if (!u) return { ok: false, error: '没有这个人' };
    u.banned = !!on;
    persist();
    return { ok: true };
  }
  function stats() {
    const now = Date.now();
    const onlineN = Object.values(db.users).filter(u => !u.banned && now - (u.lastSeen || 0) <= ONLINE_TTL).length;
    return {
      users: Object.keys(db.users).length,
      online: onlineN,
      hallMsgs: db.hall.msgs.length,
      reports: db.reports.length,
    };
  }

  return {
    join, heartbeat, online, myself,
    hallSend, hallFetch, dmSend, dmFetch, dmList,
    block, report, adminReports, adminBan, stats,
    DEFAULT_BAD,
  };
}

module.exports = { createSocial };
