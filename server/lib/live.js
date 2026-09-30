'use strict';
/*
 * 直播模块（后端）
 *   - 直播配置读写（data/live.json）
 *   - 弹幕/聊天：内存环形缓冲，轮询获取（隧道场景比 SSE 稳）
 *   - 在线人数：按 IP 活跃度估算
 *
 * 视频流本身不经过这里（走 CDN / 自建 SRS），这里只管"状态 + 互动"。
 */
const fs = require('fs');
const path = require('path');

function createLive(opts) {
  const cfgPath = opts.configPath;
  const MAX_CHAT = 300;
  const RATE_MS = 2000;          // 同一 IP 两条消息最短间隔
  const MAX_LEN = 200;
  const VIEWER_TTL = 60000;      // 60 秒内有心跳算在线

  let chat = [];                 // {id, name, text, at, ip}
  let seq = 0;
  const viewers = new Map();     // ip -> lastSeen
  const lastPost = new Map();    // ip -> ts

  /* ---------- 配置 ---------- */
  function readConfig() {
    const def = {
      on: false, title: '直播', notice: '', mode: 'hls', url: '', cover: '',
      startAt: '', chatOn: true, chatNeedName: true, bannedWords: [],
    };
    try {
      const cur = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
      return Object.assign(def, cur || {});
    } catch (e) { return def; }
  }

  function writeConfig(patch) {
    const cur = readConfig();
    const ALLOW = ['on', 'title', 'notice', 'mode', 'url', 'cover', 'startAt', 'chatOn', 'chatNeedName', 'bannedWords'];
    for (const k of ALLOW) {
      if (patch[k] === undefined) continue;
      if (k === 'chatOn' || k === 'chatNeedName' || k === 'on') cur[k] = !!patch[k];
      else if (k === 'bannedWords') cur[k] = Array.isArray(patch[k]) ? patch[k].slice(0, 100) : [];
      else cur[k] = String(patch[k]).slice(0, 500).trim();
    }
    // 校验流地址协议，防止把奇怪的东西塞进来
    if (cur.url && !/^https?:\/\//i.test(cur.url)) cur.url = '';
    if (!['hls', 'flv', 'embed', 'none'].includes(cur.mode)) cur.mode = 'hls';
    const tmp = cfgPath + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(cur, null, 2));
    fs.renameSync(tmp, cfgPath);
    return cur;
  }

  /* ---------- 在线人数 ---------- */
  function heartbeat(ip) {
    const now = Date.now();
    viewers.set(ip, now);
    for (const [k, t] of viewers) if (now - t > VIEWER_TTL) viewers.delete(k);
  }
  function viewerCount() {
    const now = Date.now();
    let n = 0;
    for (const [, t] of viewers) if (now - t <= VIEWER_TTL) n++;
    return n;
  }

  /* ---------- 聊天 ---------- */
  function clean(s) {
    return String(s == null ? '' : s)
      .replace(/[\u0000-\u001f\u007f]/g, '')   // 控制字符
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, MAX_LEN);
  }

  function addChat({ name, text, ip }) {
    const cfg = readConfig();
    if (!cfg.chatOn) return { ok: false, error: '聊天已关闭' };

    const now = Date.now();
    const last = lastPost.get(ip) || 0;
    if (now - last < RATE_MS) return { ok: false, error: '发太快了，慢一点～' };
    lastPost.set(ip, now);

    const txt = clean(text);
    if (!txt) return { ok: false, error: '内容不能为空' };
    if (/(https?:\/\/|www\.)/i.test(txt)) return { ok: false, error: '不能发链接' };
    const bad = (cfg.bannedWords || []).filter(w => w && txt.includes(w));
    if (bad.length) return { ok: false, error: '包含不允许的词' };

    let nm = clean(name).slice(0, 20) || '顾客';
    const msg = { id: ++seq, name: nm, text: txt, at: now };
    chat.push(msg);
    if (chat.length > MAX_CHAT) chat = chat.slice(-MAX_CHAT);
    return { ok: true, msg };
  }

  function getChat(since) {
    const s = Number(since) || 0;
    return chat.filter(m => m.id > s);
  }

  function clearChat() { chat = []; return true; }

  return { readConfig, writeConfig, addChat, getChat, heartbeat, viewerCount, clearChat };
}

module.exports = { createLive };
