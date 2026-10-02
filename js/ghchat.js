/*
 * 用 GitHub 仓库当聊天数据库（和卤味后台同一套路）
 *
 * 为什么可行：GitHub 仓库本身就是"永久 + 跨设备"的存储。
 *   读：公开仓库无需 Token
 *   写：需要 Token（存浏览器本地，和 lh.js 一样）
 *
 * 存储布局（放在仓库的 social/ 目录下）：
 *   social/hall.json              大厅消息（只留最近 N 条）
 *   social/users.json             用户昵称头像
 *   social/dm/<a>__<b>.json       一对一消息
 *   social/img/<id>.jpg           图片
 *
 * 并发处理：消息是"只增不改"的，用 id 去重合并；
 *          写冲突（409）时重新拉取再合并重试 —— 不会丢消息。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.GHChat = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const CFG_KEY = 'yh_gh';
  const DEF = { owner: '', repo: '', branch: 'main', token: '', path: 'social' };
  const HALL_MAX = 400;      // 大厅最多留多少条
  const DM_MAX = 400;

  /* ---------- 配置 ---------- */
  function cfg() {
    try { return Object.assign({}, DEF, JSON.parse(localStorage.getItem(CFG_KEY) || '{}')); }
    catch (e) { return Object.assign({}, DEF); }
  }
  function saveCfg(c) {
    const n = Object.assign(cfg(), c);
    try { localStorage.setItem(CFG_KEY, JSON.stringify(n)); } catch (e) {}
    return n;
  }
  function clearCfg() { try { localStorage.removeItem(CFG_KEY); } catch (e) {} }
  function ready() { const c = cfg(); return !!(c.owner && c.repo && c.token); }

  /* ---------- 编解码 ---------- */
  const b64enc = s => {
    if (typeof btoa === 'function') return btoa(unescape(encodeURIComponent(s)));
    return Buffer.from(String(s), 'utf8').toString('base64');
  };
  const b64dec = b => {
    const clean = String(b).replace(/\s/g, '');
    if (typeof atob === 'function') return decodeURIComponent(escape(atob(clean)));
    return Buffer.from(clean, 'base64').toString('utf8');
  };

  const now = () => Date.now();
  function uid16() {
    let s = '';
    const AB = 'abcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 10; i++) s += AB[Math.floor(Math.random() * AB.length)];
    return now().toString(36) + '-' + s;
  }
  const clean = (s, max) => String(s == null ? '' : s)
    .replace(/[\u0000-\u001f\u007f]/g, '').replace(/\r/g, '').trim().slice(0, max || 300);

  /* ---------- API ---------- */
  function api(path, opts) {
    const c = cfg();
    opts = opts || {};
    const headers = Object.assign({
      'Authorization': 'Bearer ' + c.token,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    }, opts.headers || {});
    return fetch('https://api.github.com' + path, Object.assign({}, opts, { headers }))
      .then(r => r.text().then(t => {
        let d = null;
        try { d = t ? JSON.parse(t) : null; } catch (e) { d = { raw: t }; }
        if (!r.ok) {
          const err = new Error((d && d.message) || ('HTTP ' + r.status));
          err.status = r.status; err.data = d;
          throw err;
        }
        return d;
      }));
  }

  const full = p => {
    const c = cfg();
    const base = (c.path || '').replace(/^\/|\/$/g, '');
    return (base ? base + '/' : '') + p.replace(/^\//, '');
  };

  /* ---------- 读文件（返回 {data, sha}，不存在返回 {data:null}） ---------- */
  async function getJSON(rel) {
    const c = cfg();
    try {
      const d = await api('/repos/' + c.owner + '/' + c.repo + '/contents/' + full(rel) +
        '?ref=' + encodeURIComponent(c.branch) + '&t=' + now());
      const text = d.content ? b64dec(d.content) : '';
      let parsed = null;
      try { parsed = text ? JSON.parse(text) : null; } catch (e) { parsed = null; }
      return { data: parsed, sha: d.sha };
    } catch (e) {
      if (e.status === 404) return { data: null, sha: null };
      throw e;
    }
  }

  /* ---------- 写文件 ---------- */
  async function putJSON(rel, data, message, knownSha) {
    const c = cfg();
    let sha = knownSha;
    if (sha === undefined) {
      const cur = await getJSON(rel).catch(() => ({ sha: null }));
      sha = cur.sha;
    }
    const body = {
      message: message || ('更新 ' + rel),
      content: b64enc(JSON.stringify(data, null, 2)),
      branch: c.branch,
    };
    if (sha) body.sha = sha;
    return api('/repos/' + c.owner + '/' + c.repo + '/contents/' + full(rel), {
      method: 'PUT', body: JSON.stringify(body),
    });
  }

  /* ---------- 追加消息（并发安全：冲突就重拉再合并） ---------- */
  async function appendMsg(rel, msg, cap) {
    const MAX = cap || HALL_MAX;
    for (let attempt = 0; attempt < 5; attempt++) {
      const cur = await getJSON(rel);
      const list = (cur.data && Array.isArray(cur.data.msgs)) ? cur.data.msgs : [];
      // 按 id 去重（别人可能刚加过同样的）
      if (list.some(m => m.id === msg.id)) return { ok: true, dup: true };
      list.push(msg);
      if (list.length > MAX) list.splice(0, list.length - MAX);
      try {
        await putJSON(rel, { msgs: list, updatedAt: now() }, '聊天 ' + msg.id, cur.sha);
        return { ok: true };
      } catch (e) {
        if (e.status === 409 || e.status === 422) {
          await new Promise(r => setTimeout(r, 250 * (attempt + 1)));
          continue;                 // sha 过期，重新拉取合并
        }
        throw e;
      }
    }
    return { ok: false, error: '保存失败，重试几次都不行' };
  }

  /* ---------- 合并多条（批量写） ---------- */
  async function mergeMsgs(rel, newMsgs, cap) {
    const MAX = cap || HALL_MAX;
    const cur = await getJSON(rel);
    const list = (cur.data && Array.isArray(cur.data.msgs)) ? cur.data.msgs : [];
    const seen = new Set(list.map(m => m.id));
    for (const m of newMsgs) if (!seen.has(m.id)) { list.push(m); seen.add(m.id); }
    list.sort((a, b) => (a.at || 0) - (b.at || 0));
    if (list.length > MAX) list.splice(0, list.length - MAX);
    await putJSON(rel, { msgs: list, updatedAt: now() }, '合并聊天', cur.sha);
    return list;
  }

  /* ---------- 大厅 ---------- */
  async function hallRead() {
    const r = await getJSON('hall.json');
    const list = (r.data && r.data.msgs) || [];
    return { msgs: list, sha: r.sha };
  }
  async function hallSend(msg) { return appendMsg('hall.json', msg, HALL_MAX); }

  /* ---------- 用户表 ---------- */
  async function usersRead() {
    const r = await getJSON('users.json');
    return (r.data && r.data.users) || {};
  }
  async function userUpsert(uid, info) {
    for (let i = 0; i < 4; i++) {
      const r = await getJSON('users.json');
      const users = (r.data && r.data.users) || {};
      users[uid] = Object.assign({}, users[uid] || {}, info, { lastSeen: now() });
      try {
        await putJSON('users.json', { users, updatedAt: now() }, '用户 ' + uid, r.sha);
        return { ok: true };
      } catch (e) {
        if (e.status === 409 || e.status === 422) { await new Promise(x => setTimeout(x, 250 * (i + 1))); continue; }
        throw e;
      }
    }
    return { ok: false };
  }

  /* ---------- 私聊 ---------- */
  const dmKey = (a, b) => [String(a), String(b)].sort().join('__');
  const dmPath = (a, b) => 'dm/' + dmKey(a, b) + '.json';

  async function dmRead(a, b) {
    const r = await getJSON(dmPath(a, b));
    return { msgs: (r.data && r.data.msgs) || [], sha: r.sha };
  }
  async function dmSend(a, b, msg) {
    return appendMsg(dmPath(a, b), msg, DM_MAX);
  }

  // 列出我参与的所有私聊：靠 users.json 里的 dmIndex 记录
  async function dmIndexRead() {
    const r = await getJSON('dmindex.json');
    return (r.data && r.data.pairs) || [];
  }
  async function dmIndexAdd(a, b) {
    for (let i = 0; i < 4; i++) {
      const r = await getJSON('dmindex.json');
      const pairs = (r.data && r.data.pairs) || [];
      const key = dmKey(a, b);
      if (!pairs.some(p => p.key === key)) {
        pairs.push({ key, a: String(a), b: String(b), at: now() });
        if (pairs.length > 800) pairs.splice(0, pairs.length - 800);
        try {
          await putJSON('dmindex.json', { pairs, updatedAt: now() }, '私聊索引', r.sha);
          return { ok: true };
        } catch (e) {
          if (e.status === 409 || e.status === 422) { await new Promise(x => setTimeout(x, 250 * (i + 1))); continue; }
          throw e;
        }
      }
      return { ok: true, dup: true };
    }
    return { ok: false };
  }

  /* ---------- 图片 ---------- */
  function decodeDataUrl(dataUrl) {
    const i = String(dataUrl).indexOf(',');
    return { base64: dataUrl.slice(i + 1), mime: dataUrl.slice(5, dataUrl.indexOf(';')) };
  }

  async function uploadImage(dataUrl, ext) {
    const id = uid16();
    const rel = 'img/' + id + '.' + (ext || 'jpg');
    const { base64 } = decodeDataUrl(dataUrl);
    await putFile(rel, base64, '聊天图片 ' + id, true);
    return rawUrl(rel);
  }

  async function putFile(rel, contentB64, message, isB64) {
    const c = cfg();
    let sha = null;
    try { const cur = await getJSON(rel); sha = cur.sha; } catch (e) {}
    const body = {
      message: message || ('更新 ' + rel),
      content: isB64 ? contentB64 : b64enc(contentB64),
      branch: c.branch,
    };
    if (sha) body.sha = sha;
    return api('/repos/' + c.owner + '/' + c.repo + '/contents/' + full(rel), {
      method: 'PUT', body: JSON.stringify(body),
    });
  }

  /* ---------- 图片访问地址（走 CDN，不消耗 API 额度） ---------- */
  function rawUrl(rel) {
    const c = cfg();
    const p = full(rel);
    // raw.githubusercontent 有 CDN 缓存，设为 5 分钟左右，够用
    return 'https://raw.githubusercontent.com/' + c.owner + '/' + c.repo +
      '/' + c.branch + '/' + p;
  }

  /* ---------- 图片压缩（同后台传图逻辑） ---------- */
  function compressImage(file, maxW, quality) {
    maxW = maxW || 900; quality = quality || 0.78;
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => {
        const im = new Image();
        im.onload = () => {
          const scale = Math.min(1, maxW / im.width);
          const w = Math.round(im.width * scale), h = Math.round(im.height * scale);
          const cv = document.createElement('canvas');
          cv.width = w; cv.height = h;
          const ctx = cv.getContext('2d');
          ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
          ctx.drawImage(im, 0, 0, w, h);
          resolve(cv.toDataURL('image/jpeg', quality));
        };
        im.onerror = reject;
        im.src = fr.result;
      };
      im.onerror = reject;
      fr.onerror = reject;
      fr.readAsDataURL(file);
    });
  }

  /* ---------- 连通性自测 ---------- */
  async function test() {
    const c = cfg();
    if (!c.owner || !c.repo || !c.token) return { ok: false, error: '配置不完整' };
    const u = await api('/user');
    const r = await api('/repos/' + c.owner + '/' + c.repo);
    return {
      ok: true,
      user: u.login,
      repo: r.full_name,
      private: r.private,
      canWrite: !!(r.permissions && r.permissions.push),
    };
  }

  return {
    cfg, saveCfg, clearCfg, ready, test,
    hallRead, hallSend, usersRead, userUpsert,
    dmRead, dmSend, dmIndexRead, dmIndexAdd,
    uploadImage, compressImage, rawUrl,
    b64enc, b64dec, uid16, dmKey, dmPath, clean,
    getJSON, putJSON, appendMsg, mergeMsgs,
  };
});
