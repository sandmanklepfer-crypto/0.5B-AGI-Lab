/* 遇见 · 聊天交友（匿名，不用手机号） */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const AVATARS = ['🐱', '🐰', '🦊', '🐼', '🐨', '🐯', '🦁', '🐸', '🐧', '🦄', '🐳', '🦋',
                   '🌸', '🍀', '⭐', '🌙', '🍜', '☕', '🎧', '🎮'];
  const LSK = { uid: 'yh_uid', me: 'yh_me', blocked: 'yh_blocked' };
  // 后端基地址：默认同源。可用 ?api=https://xxx 指定远程后端
  const API_POOL = (function () {
    const q = new URLSearchParams(location.search).get('api');
    const list = [];
    if (q) list.push(String(q).replace(/\/+$/, ''));
    list.push('');                       // 同源
    return list;
  })();

  const S = {
    api: null, uid: '', me: null,
    hallId: 0, dmId: 0, peer: null,
    view: 'hall', online: [], threads: [], blocked: [],
    timers: {}, sending: false,
  };

  /* ---------- 小工具 ---------- */
  let toastT;
  function toast(msg) {
    let el = document.querySelector('.toast');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
    el.textContent = msg; el.classList.add('on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('on'), 1900);
  }
  function nowT(ts) {
    const d = new Date(ts);
    const n = new Date();
    const sameDay = d.toDateString() === n.toDateString();
    return sameDay
      ? d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
      : d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  }
  function store(k, v) { try { v === undefined ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function read(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }

  /* ---------- 后端探测 ---------- */
  async function detectApi() {
    for (const c of API_POOL) {
      try {
        const r = await fetch(c + '/api/social/online?uid=probe', { cache: 'no-store' });
        const d = await r.json();
        if (r.ok && d && d.ok) { S.api = c; return true; }
      } catch (e) { /* 下一个 */ }
    }
    return false;
  }
  const api = (p, opts) => fetch(S.api + p, opts).then(r => r.json().then(j => ({ ok: r.ok, body: j })));
  const post = (p, data) => api(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });

  /* ---------- 视图切换 ---------- */
  function show(v) {
    S.view = v;
    ['hall', 'msg', 'me', 'dm'].forEach(x => {
      const el = $('#v-' + x);
      if (el) el.classList.toggle('on', x === v);
    });
    $$('.tabs button').forEach(b => {
      b.classList.toggle('on', b.dataset.v === v || (v === 'dm' && b.dataset.v === 'msg'));
    });
    $('#strip').classList.toggle('hid', v === 'dm');
    $('#topTitle').textContent = v === 'me' ? '我' : (v === 'msg' ? '消息' : '遇见');
    if (v === 'hall') $('#hallFlow').scrollTop = 1e9;
    if (v === 'dm') $('#dmFlow').scrollTop = 1e9;
  }

  /* ---------- 气泡 ---------- */
  function bubble(m, mine) {
    const d = document.createElement('div');
    d.className = 'b' + (mine ? ' me' : '');
    d.innerHTML =
      '<div class="av">' + esc(m.avatar || (mine ? (S.me && S.me.avatar) : '🙂') || '🙂') + '</div>' +
      '<div class="wrap">' +
        (mine ? '' : '<div class="who2">' + esc(m.nick || '') + '</div>') +
        '<div class="tx">' + esc(m.text) + '</div>' +
      '</div>';
    return d;
  }
  function sysLine(text) {
    const d = document.createElement('div');
    d.className = 'sys'; d.textContent = text;
    return d;
  }

  /* ---------- 大厅 ---------- */
  async function pollHall() {
    if (S.view === 'dm') return;
    try {
      const r = await api('/api/social/hall?uid=' + encodeURIComponent(S.uid) + '&since=' + S.hallId);
      if (!r.ok || !r.body.ok) return;
      const box = $('#hallFlow');
      const news = r.body.messages || [];
      if (news.length) {
        const e = box.querySelector('.empty'); if (e) e.remove();
        for (const m of news) {
          S.hallId = Math.max(S.hallId, m.id);
          box.appendChild(bubble(m, m.from.uid === S.uid));
        }
        box.scrollTop = box.scrollHeight;
      }
      if (r.body.stats) {
        $('#onlineN').textContent = r.body.stats.online;
        $('#topSub').textContent = r.body.stats.online + ' 人在线 · 大家聊得挺热闹';
      }
    } catch (e) { /* 抖动忽略 */ }
  }

  async function sendHall() {
    const ta = $('#hallIn'); const t = ta.value.trim();
    if (!t || S.sending) return;
    if (t.length > 300) return toast('太长了');
    S.sending = true; $('#hallSend').disabled = true;
    try {
      const r = await post('/api/social/hall', { uid: S.uid, text: t });
      if (!r.ok || !r.body.ok) { toast(r.body.error || '发送失败'); return; }
      ta.value = ''; ta.style.height = 'auto';
      const box = $('#hallFlow');
      const e = box.querySelector('.empty'); if (e) e.remove();
      S.hallId = Math.max(S.hallId, r.body.msg.id);
      box.appendChild(bubble(r.body.msg, true));
      box.scrollTop = box.scrollHeight;
    } catch (e) { toast('网络不好'); }
    finally { S.sending = false; $('#hallSend').disabled = false; ta.focus(); }
  }

  /* ---------- 在线的人 ---------- */
  async function pollOnline() {
    if (S.view === 'dm') return;
    try {
      const r = await api('/api/social/online?uid=' + encodeURIComponent(S.uid));
      if (!r.ok || !r.body.ok) return;
      S.online = r.body.list || [];
      if (r.body.me) { S.me = Object.assign(S.me || {}, r.body.me); store(LSK.me, S.me); }
      const row = $('#onlineRow');
      if (!S.online.length) {
        row.innerHTML = '<span style="color:var(--mut);font-size:12.5px;padding:8px 0">暂时只有你一个人，等等看～</span>';
      } else {
        row.innerHTML = S.online.map(u =>
          '<div class="who" data-uid="' + esc(u.uid) + '" data-nick="' + esc(u.nick) + '" data-av="' + esc(u.avatar) + '">' +
            '<div class="av">' + esc(u.avatar || '🙂') + '</div>' +
            '<div class="nm"><span class="dot">●</span> ' + esc(u.nick) + '</div>' +
          '</div>').join('');
        row.querySelectorAll('.who').forEach(el => el.onclick = () =>
          openDM(el.dataset.uid, el.dataset.nick, el.dataset.av));
      }
      $('#onlineN').textContent = (r.body.stats && r.body.stats.online) || S.online.length;
    } catch (e) { /* 忽略 */ }
  }

  /* ---------- 消息列表 ---------- */
  async function pollThreads() {
    try {
      const r = await api('/api/social/dms?uid=' + encodeURIComponent(S.uid));
      if (!r.ok || !r.body.ok) return;
      S.threads = r.body.list || [];
      const total = S.threads.reduce((a, t) => a + (t.unread || 0), 0);
      const dot = $('#tabDot');
      if (total) { dot.textContent = total > 99 ? '99+' : total; dot.classList.remove('hid'); }
      else dot.classList.add('hid');
      if (S.view !== 'msg') return;
      const box = $('#dmList');
      if (!S.threads.length) {
        box.innerHTML = '<div class="empty">还没有人跟你聊过<br>去「大厅」或者点上面的头像找人说句话吧</div>';
      } else {
        box.innerHTML = S.threads.map(t =>
          '<div class="li" data-uid="' + esc(t.uid) + '" data-nick="' + esc(t.nick) + '" data-av="' + esc(t.avatar) + '">' +
            '<div class="av">' + esc(t.avatar || '🙂') + '</div>' +
            '<div class="mid"><div class="nm">' + esc(t.nick) + '</div>' +
            '<div class="pv">' + esc(t.lastText || '') + '</div></div>' +
            '<div class="rt"><div class="tm">' + nowT(t.lastAt) + '</div>' +
            (t.unread ? '<div class="un">' + t.unread + '</div>' : '') + '</div>' +
          '</div>').join('');
        box.querySelectorAll('.li').forEach(el => el.onclick = () =>
          openDM(el.dataset.uid, el.dataset.nick, el.dataset.av));
      }
    } catch (e) { /* 忽略 */ }
  }

  /* ---------- 私聊 ---------- */
  function openDM(uid, nick, avatar) {
    if (!uid || uid === S.uid) return;
    S.peer = { uid, nick: nick || uid, avatar: avatar || '🙂' };
    S.dmId = 0;
    $('#dmNm').textContent = S.peer.nick;
    $('#dmAv').textContent = S.peer.avatar;
    $('#dmFlow').innerHTML = '';
    show('dm');
    pollDM(true);
    setTimeout(() => $('#dmIn').focus(), 200);
  }

  async function pollDM(first) {
    if (!S.peer) return;
    try {
      const r = await api('/api/social/dm?uid=' + encodeURIComponent(S.uid) +
        '&peer=' + encodeURIComponent(S.peer.uid) + '&since=' + S.dmId);
      if (!r.ok || !r.body.ok) return;
      const box = $('#dmFlow');
      const news = r.body.messages || [];
      if (first && !news.length) {
        box.innerHTML = '<div class="empty">还没聊过，说句话打破沉默吧～</div>';
      }
      for (const m of news) {
        const e = box.querySelector('.empty'); if (e) e.remove();
        S.dmId = Math.max(S.dmId, m.id);
        box.appendChild(bubble(m, m.from === S.uid));
      }
      if (news.length) box.scrollTop = box.scrollHeight;
    } catch (e) { /* 忽略 */ }
  }

  async function sendDM() {
    const ta = $('#dmIn'); const t = ta.value.trim();
    if (!t || S.sending || !S.peer) return;
    S.sending = true; $('#dmSend').disabled = true;
    try {
      const r = await post('/api/social/dm', { uid: S.uid, to: S.peer.uid, text: t });
      if (!r.ok || !r.body.ok) { toast(r.body.error || '发送失败'); return; }
      ta.value = ''; ta.style.height = 'auto';
      const box = $('#dmFlow');
      const e = box.querySelector('.empty'); if (e) e.remove();
      S.dmId = Math.max(S.dmId, r.body.msg.id);
      box.appendChild(bubble(r.body.msg, true));
      box.scrollTop = box.scrollHeight;
    } catch (e) { toast('网络不好'); }
    finally { S.sending = false; $('#dmSend').disabled = false; ta.focus(); }
  }

  /* ---------- 操作（拉黑/举报） ---------- */
  function openActions() {
    if (!S.peer) return;
    $('#actTitle').textContent = S.peer.nick;
    const isBlocked = S.blocked.includes(S.peer.uid);
    $('#actBlock').textContent = isBlocked ? '✅ 解除拉黑' : '🚫 拉黑';
    $('#mask').classList.add('on');
    $('#actSheet').classList.add('on');
  }
  function closeActions() {
    $('#mask').classList.remove('on');
    $('#actSheet').classList.remove('on');
  }

  async function toggleBlock() {
    if (!S.peer) return;
    const on = !S.blocked.includes(S.peer.uid);
    const r = await post('/api/social/block', { uid: S.uid, target: S.peer.uid, on });
    if (!r.ok || !r.body.ok) return toast(r.body.error || '操作失败');
    S.blocked = on ? S.blocked.concat(S.peer.uid) : S.blocked.filter(x => x !== S.peer.uid);
    store(LSK.blocked, S.blocked);
    toast(on ? '已拉黑，ta 的消息你看不到了' : '已解除拉黑');
    closeActions();
    // 重新拉一遍
    S.hallId = 0; $('#hallFlow').innerHTML = '';
    pollHall(); pollDM(true);
  }

  async function doReport() {
    if (!S.peer) return;
    const reason = prompt('说说为什么要举报（可留空）');
    if (reason === null) return;
    const r = await post('/api/social/report', { uid: S.uid, target: S.peer.uid, reason: reason || '未说明' });
    if (r.ok && r.body.ok) { toast('已举报，管理员会处理'); closeActions(); }
    else toast('举报失败');
  }

  /* ---------- 我的 ---------- */
  function renderMe() {
    const m = S.me || {};
    $('#meBox').innerHTML =
      '<div class="prof">' +
        '<div class="big">' + esc(m.avatar || '🙂') + '</div>' +
        '<div class="nick">' + esc(m.nick || '未设置') + '</div>' +
        '<div class="uid">ID ' + esc((S.uid || '').slice(0, 12)) + '</div>' +
      '</div>' +
      '<div class="card">' +
        '<h3>我的资料</h3>' +
        '<p>昵称和头像随时可以改，改了之后别人看到的也是新的。</p>' +
        '<div class="r"><button class="go" id="btnEdit">改昵称 / 头像</button>' +
        '<button id="btnClear">清空大厅记录</button></div>' +
      '</div>' +
      '<div class="card safe">' +
        '<h3>🛡️ 安全提示</h3>' +
        '<p>' +
          '· 这里<b>不用手机号、不用实名</b>，就是个陌生人聊天的地方<br>' +
          '· <b>别透露</b>真实姓名、住址、单位、银行卡<br>' +
          '· <b>任何要钱的都是骗子</b>：投资、刷单、借钱、代付、带你赚钱<br>' +
          '· 遇到骚扰就点右上角 <b>⋯ → 拉黑</b>，顺手举报一下<br>' +
          '· 聊得来也别急着线下见面，先在人多的地方见' +
        '</p>' +
      '</div>' +
      '<div class="card">' +
        '<h3>已拉黑（' + S.blocked.length + '）</h3>' +
        '<p>' + (S.blocked.length ? '被拉黑的人你在大厅和私聊都看不到。' : '还没有拉黑任何人。') + '</p>' +
      '</div>' +
      '<div style="height:20px"></div>';

    $('#btnEdit').onclick = openJoin;
    $('#btnClear').onclick = () => {
      S.hallId = 0; $('#hallFlow').innerHTML = '';
      toast('已清空显示，下次进来会重新拉取');
    };
  }

  /* ---------- 加入 ---------- */
  let pickedAv = '🙂';
  function renderAvPick() {
    $('#avPick').innerHTML = AVATARS.map(a =>
      '<span data-av="' + a + '"' + (a === pickedAv ? ' class="on"' : '') + '>' + a + '</span>').join('');
    $('#avPick').querySelectorAll('span').forEach(el => el.onclick = () => {
      pickedAv = el.dataset.av; renderAvPick();
    });
  }
  function openJoin() {
    const m = S.me || {};
    pickedAv = m.avatar || '🙂';
    renderAvPick();
    $('#nickIn').value = m.nick || '';
    $('#joinErr').textContent = '';
    $('#mask').classList.add('on');
    $('#sSheet').classList.add('on');
    setTimeout(() => $('#nickIn').focus(), 250);
  }
  async function doJoin() {
    const nick = $('#nickIn').value.trim();
    if (!nick) { $('#joinErr').textContent = '起个名字吧'; return; }
    const r = await post('/api/social/join', { uid: S.uid, nick, avatar: pickedAv });
    if (!r.ok || !r.body.ok) { $('#joinErr').textContent = r.body.error || '进不去'; return; }
    S.me = r.body.user; store(LSK.me, S.me);
    $('#mask').classList.remove('on');
    $('#sSheet').classList.remove('on');
    $('#topMe').textContent = S.me.avatar;
    toast('欢迎，' + S.me.nick + '！');
    renderMe();
    pollHall(); pollOnline(); pollThreads();
  }

  /* ---------- 没有后端 ---------- */
  function noBackend() {
    $('#mask').classList.remove('on');
    $('#sSheet').classList.remove('on');
    $('#strip').classList.add('hid');
    $('#topSub').textContent = '未连接服务器';
    $('#hallFlow').innerHTML =
      '<div class="empty">😕 现在连不上服务器<br><br>' +
      '聊天需要后端一直开着。<br>让管理员把服务启动起来就能用了。</div>';
    $('#hallIn').disabled = true;
    $('#hallSend').disabled = true;
  }

  /* ---------- 启动 ---------- */
  async function boot() {
    let uid = read(LSK.uid, '');
    if (!uid) {
      uid = 'u' + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      store(LSK.uid, uid);
    }
    S.uid = uid;
    S.me = read(LSK.me, null);
    S.blocked = read(LSK.blocked, []) || [];

    // 交互绑定
    $$('.tabs button').forEach(b => b.onclick = () => {
      show(b.dataset.v);
      $('#strip').classList.toggle('hid', b.dataset.v !== 'hall');
      if (b.dataset.v === 'msg') pollThreads();
      if (b.dataset.v === 'me') renderMe();
      if (b.dataset.v === 'hall') { pollHall(); pollOnline(); }
    });
    $('#topMe').onclick = () => { show('me'); renderMe(); $('#strip').classList.add('hid'); };
    $('#hallSend').onclick = sendHall;
    $('#dmSend').onclick = sendDM;
    $('#dmBack').onclick = () => { S.peer = null; show('msg'); pollThreads(); $('#strip').classList.remove('hid'); };
    $('#dmMore').onclick = openActions;
    $('#actBlock').onclick = toggleBlock;
    $('#actReport').onclick = doReport;
    $('#actClose').onclick = closeActions;
    $('#mask').onclick = () => { closeActions(); };
    $('#joinGo').onclick = doJoin;
    $('#nickIn').onkeydown = e => { if (e.key === 'Enter') doJoin(); };

    ['#hallIn', '#dmIn'].forEach(sel => {
      const ta = $(sel);
      ta.oninput = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 96) + 'px'; };
      ta.onkeydown = e => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sel === '#hallIn' ? sendHall() : sendDM();
        }
      };
    });

    // 连后端
    const ok = await detectApi();
    if (!ok) { noBackend(); return; }

    if (!S.me || !S.me.nick) { openJoin(); return; }
    $('#topMe').textContent = S.me.avatar || '🙂';
    const r = await post('/api/social/join', { uid: S.uid, nick: S.me.nick, avatar: S.me.avatar });
    if (r.ok && r.body.ok) { S.me = r.body.user; store(LSK.me, S.me); }

    show('hall');
    await Promise.all([pollHall(), pollOnline(), pollThreads()]);
    renderMe();

    S.timers.hall = setInterval(pollHall, 2500);
    S.timers.online = setInterval(pollOnline, 12000);
    S.timers.threads = setInterval(pollThreads, 4000);
    S.timers.dm = setInterval(() => { if (S.peer) pollDM(false); }, 2500);

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) return;
      if (S.view === 'dm') pollDM(false);
      else { pollHall(); pollOnline(); pollThreads(); }
    });
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
