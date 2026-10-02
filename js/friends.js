/* 遇见 · 聊天交友
 * 通信：公共 MQTT（免注册 / 免 Token / 真双向 / 实时推送）
 * 历史：本机保存（换设备看不到旧的，这是无服务器方案的代价）
 */
(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const AVATARS = ['🐱', '🐰', '🦊', '🐼', '🐨', '🐯', '🦁', '🐸', '🐧', '🦄', '🐳', '🦋',
                   '🌸', '🍀', '⭐', '🌙', '🍜', '☕', '🎧', '🎮'];
  const LSK = { uid: 'yh_uid', me: 'yh_me', room: 'yh_room', blocked: 'yh_blocked' };
  const ONLINE_MS = 70 * 1000;     // 70 秒内有心跳算在线
  const HIST_MAX = 200;            // 本机每个房间最多留 200 条
  const HIST_KEEP = 80;            // broker 上最多保留 80 条（跨设备可见的历史）
  const IMG_MAX_KB = 90;           // 图片压到 90KB 以内

  const S = {
    uid: '', me: null, room: '', peer: null,
    mq: null, online: {}, blocked: [],
    msgs: [], dmMsgs: [], timerPing: null, timerSweep: null, presAck: {},
  };

  /* ---------- 小工具 ---------- */
  let toastT;
  function toast(m) {
    let el = document.querySelector('.toast');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
    el.textContent = m; el.classList.add('on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('on'), 2200);
  }
  const rd = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
  const wr = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  const hhmm = ts => new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  const amOnline = uid => !!(S.online[uid] && Date.now() - S.online[uid].at < ONLINE_MS);

  const BAD = ['加微信', '微信号', '加v', '转账', '借钱', '刷单', '兼职', '投资', '理财',
               '博彩', '赌博', '返利', '贷款', '裸聊', '约炮', '代付'];
  function checkText(t) {
    if (!t) return '内容不能为空';
    if (/(https?:\/\/|www\.)/i.test(t)) return '不能发链接';
    if (/\d{7,}/.test(t)) return '不能发一长串数字';
    const low = t.toLowerCase();
    const hit = BAD.filter(w => low.includes(w.toLowerCase()));
    if (hit.length) return '包含不允许的词：' + hit[0];
    return null;
  }

  /* ---------- topic ----------
   * 消息用「一条一主题 + retain（保留消息）」：
   *   broker 会替我们保存每条消息，任何新进来的人订阅通配符就能拿到全部历史。
   *   —— 这就是跨设备同步的来源，不需要任何账号或令牌。
   */
  const ROOT = 'zhz/c/';
  const tMsg = (key) => ROOT + S.room + '/m/' + key;   // 单条消息（retained）
  const tMsgAll = () => ROOT + S.room + '/m/#';         // 历史 + 实时
  const tPres = () => ROOT + S.room + '/p';             // 在线心跳（不 retain）
  const tDm = (a, b) => ROOT + S.room + '/d/' + [a, b].sort().join('_');

  // 消息 key：时间戳(36进制) + 随机 → 天生按时间排序
  function msgKey(ts) { return ts.toString(36) + Math.random().toString(36).slice(2, 6); }

  /* ---------- 消息收发 ---------- */
  function sendMsg(obj) {
    if (!S.mq || !S.mq.connected) { toast('还没连上，稍等一下'); return false; }
    try {
      S.mq.publish(tMsg(obj._k), JSON.stringify(obj), true);   // retain = true，broker 帮我们存
      return true;
    } catch (e) { toast('发送失败'); return false; }
  }

  function onMsg(topic, raw) {
    let m;
    try { m = JSON.parse(raw); } catch (e) { return; }
    if (!m || !m.uid) return;
    if (S.blocked.includes(m.uid) && m.uid !== S.uid) return;

    if (topic === tPres()) {                       // 在线心跳
      const isNew = m.uid !== S.uid && !S.online[m.uid];
      S.online[m.uid] = { nick: m.nick, avatar: m.avatar, at: m.at || Date.now() };
      if (m.bye) delete S.online[m.uid];
      renderOnline();
      // 看到陌生人在线就回一声 —— 否则要等下次心跳（25 秒）对方才知道我在
      if (isNew && !m.bye) {
        const last = S.presAck[m.uid] || 0;
        if (Date.now() - last > 15000) {
          S.presAck[m.uid] = Date.now();
          setTimeout(publishPresence, 200 + Math.random() * 500);   // 错开，避免同时刷
        }
      }
      return;
    }
    if (topic.indexOf('/m/') > 0) {                // 房间消息（含 broker 补发的历史）
      if (S.msgs.some(x => x.id === m.id)) return;
      if (m.dm) return;                            // 私聊不走这里
      m._k = topic.split('/m/')[1];
      S.msgs.push(m);
      S.msgs.sort((a, b) => (a.at || 0) - (b.at || 0));
      saveHist();
      appendBubble($('#flow'), m);
      trimHistory();                               // 太老的从 broker 上删掉
      return;
    }
    if (topic === tDm(S.uid, S.peer ? S.peer.uid : '')) {
      if (S.dmMsgs.some(x => x.id === m.id)) return;
      S.dmMsgs.push(m);
      appendBubble($('#flow'), m);
      return;
    }
    // 任意私聊主题（对方主动发来时我们还没打开窗口）
    if (topic.indexOf('/dm/') > 0) {
      if (S.dmMsgs.some(x => x.id === m.id)) return;
      S.dmMsgs.push(m);
      toast('收到 ' + (m.nick || '对方') + ' 的私聊');
      if (S.peer) appendBubble($('#flow'), m);
      return;
    }
  }

  /* ---------- 渲染 ---------- */
  function bubbleEl(m) {
    const mine = m.uid === S.uid;
    const d = document.createElement('div');
    d.className = 'b' + (mine ? ' me' : '');
    const isPic = !!(m.img || (m.text && /^data:image\//.test(m.text)));
    const src = m.img || m.text;
    const txt = (isPic ? '' : m.text);
    d.innerHTML =
      '<div class="av">' + esc(m.avatar || '🙂') + '</div>' +
      '<div class="wrap">' +
        (mine ? '' : '<div class="who2">' + esc(m.nick || '') + '</div>') +
        '<div class="tx' + (isPic ? ' pic' : '') + '">' +
          (txt ? esc(txt) : '') +
          (isPic ? '<img src="' + esc(src) + '" alt="图片" loading="lazy">' : '') +
        '</div>' +
      '</div>';
    return d;
  }

  function appendBubble(box, m) {
    if (!box) return;
    const e = box.querySelector('.empty'); if (e) e.remove();
    box.appendChild(bubbleEl(m));
    const near = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
    if (near || box.scrollTop === 0) box.scrollTop = box.scrollHeight;
  }

  function renderAll() {
    const box = $('#flow');
    box.innerHTML = '';
    const list = S.peer ? S.dmMsgs : S.msgs;
    if (!list.length) {
      box.innerHTML = '<div class="empty">' +
        (S.peer ? '还没聊过，说句话吧～' : '这个房间还很安静<br>说句话，别人就能看到') + '</div>';
      return;
    }
    for (const m of list.slice(-HIST_MAX)) box.appendChild(bubbleEl(m));
    box.scrollTop = box.scrollHeight;
  }

  function renderOnline() {
    const list = Object.entries(S.online)
      .filter(([u, v]) => amOnline(u))
      .map(([u, v]) => Object.assign({ uid: u }, v))
      .sort((a, b) => b.at - a.at);
    const n = list.filter(x => x.uid !== S.uid).length;
    $('#onlineTxt').textContent = n ? ('· ' + (n + 1) + ' 人在线') : '';
    const head = $('.sub');
    if (head) {
      let box = $('#onlineRow');
      if (!box) {
        box = document.createElement('div');
        box.id = 'onlineRow';
        box.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin-top:6px';
        $('.top').appendChild(box);
      }
      box.innerHTML = list.slice(0, 12).map(u =>
        '<span data-uid="' + esc(u.uid) + '" title="' + esc(u.nick) + '" ' +
        'style="cursor:pointer;font-size:19px;line-height:1;opacity:' +
        (u.uid === S.uid ? '.55' : '1') + '">' + esc(u.avatar || '🙂') + '</span>').join('');
      box.querySelectorAll('span[data-uid]').forEach(el => {
        el.onclick = () => {
          const u = el.dataset.uid;
          if (u === S.uid) { openMe(); return; }
          openDm(u);
        };
      });
    }
  }

  function renderConn() {
    const c = $('#conn');
    const ok = S.mq && S.mq.connected;
    if (ok) { c.className = 'conn hid'; return; }
    c.className = 'conn warn';
    c.innerHTML = '⚠️ 正在连接聊天服务器… <button id="btnRetry">重连</button>';
    const b = $('#btnRetry');
    if (b) b.onclick = () => { toast('重连中…'); location.reload(); };
  }

  /* ---------- 历史（本机） ---------- */
  const histKey = () => 'yh_hist_' + S.room;
  function saveHist() {
    wr(histKey(), S.msgs.slice(-HIST_MAX));
  }
  function loadHist() {
    S.msgs = rd(histKey(), []) || [];
  }

  /* ---------- 发送 ---------- */
  function doSend() {
    const ta = $('#input');
    const t = ta.value.trim();
    if (!t) return;
    if (S.peer) return sendDm(t);
    const err = checkText(t);
    if (err) return toast(err);
    const at = Date.now();
    const m = {
      id: S.uid + '-' + at + '-' + Math.random().toString(36).slice(2, 5),
      uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, text: t, at,
      _k: msgKey(at),
    };
    if (!sendMsg(m)) return;
    ta.value = ''; ta.style.height = 'auto';
    if (!S.msgs.some(x => x.id === m.id)) { S.msgs.push(m); saveHist(); appendBubble($('#flow'), m); }
  }

  function sendDm(t) {
    if (!S.peer) return;
    const err = checkText(t);
    if (err) return toast(err);
    const m = {
      id: S.uid + '-' + Date.now() + '-' + Math.random().toString(36).slice(2, 6),
      uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, text: t, at: Date.now(), dm: 1,
    };
    try { S.mq.publish(tDm(S.uid, S.peer.uid), JSON.stringify(m)); }
    catch (e) { return toast('发送失败'); }
    $('#input').value = ''; $('#input').style.height = 'auto';
    if (!S.dmMsgs.some(x => x.id === m.id)) { S.dmMsgs.push(m); appendBubble($('#flow'), m); }
  }

  /* ---------- 图片 ---------- */
  function compress(file) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader();
      fr.onload = () => {
        const im = new Image();
        im.onload = () => {
          const maxW = 760;
          const sc = Math.min(1, maxW / im.width);
          const w = Math.round(im.width * sc), h = Math.round(im.height * sc);
          const cv = document.createElement('canvas');
          cv.width = w; cv.height = h;
          const ctx = cv.getContext('2d');
          ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, w, h);
          ctx.drawImage(im, 0, 0, w, h);
          let q = 0.62, out = cv.toDataURL('image/jpeg', q);
          while (out.length * 0.75 / 1024 > IMG_MAX_KB && q > 0.25) {
            q -= 0.12; out = cv.toDataURL('image/jpeg', q);
          }
          resolve(out);
        };
        im.onerror = reject; im.src = fr.result;
      };
      fr.onerror = reject; fr.readAsDataURL(file);
    });
  }

  function pickImage() {
    const inp = $('#filePick');
    inp.value = '';
    inp.onchange = async () => {
      const f = inp.files && inp.files[0];
      if (!f) return;
      if (!/^image\//.test(f.type)) return toast('只能发图片');
      toast('压缩中…');
      let data;
      try { data = await compress(f); } catch (e) { return toast('图片处理失败'); }
      const kb = Math.round(data.length * 0.75 / 1024);
      if (kb > IMG_MAX_KB + 15) return toast('图片还是太大（' + kb + 'KB），换一张');
      const at = Date.now();
      const m = {
        id: S.uid + '-' + at + '-' + Math.random().toString(36).slice(2, 5),
        uid: S.uid, nick: S.me.nick, avatar: S.me.avatar,
        text: data, at, pic: 1, _k: msgKey(at),
      };
      if (S.peer) {
        m.dm = 1;
        try { S.mq.publish(tDm(S.uid, S.peer.uid), JSON.stringify(m)); }
        catch (e) { return toast('发送失败'); }
        S.dmMsgs.push(m);
      } else {
        if (!sendMsg(m)) return;
        S.msgs.push(m); saveHist();
      }
      appendBubble($('#flow'), m);
      toast('已发送');
    };
    inp.click();
  }

  /* ---------- 私聊 ---------- */
  function openDm(uid) {
    const u = S.online[uid] || {};
    S.peer = { uid, nick: u.nick || uid.slice(0, 6), avatar: u.avatar || '🙂' };
    S.dmMsgs = [];
    $('#roomTitle').textContent = '与 ' + S.peer.nick + ' 私聊';
    showDmBar();
    renderAll();
    if (S.mq && S.mq.connected) S.mq.subscribe(tDm(S.uid, uid));
    setTimeout(() => $('#input').focus(), 150);
  }
  function closeDm() {
    S.peer = null; S.dmMsgs = [];
    $('#roomTitle').textContent = roomLabel();
    hideDmBar();
    renderAll();
  }
  function showDmBar() {
    if ($('#dmBar')) return;
    const d = document.createElement('div');
    d.id = 'dmBar';
    d.style.cssText = 'padding:7px 12px;background:#eef1ff;font-size:12.5px;color:#4a45a8;' +
      'display:flex;justify-content:space-between;align-items:center;gap:8px';
    d.innerHTML = '<span>🔒 只有你俩能看到</span>' +
      '<span><button id="dmBlock" style="font-size:12px;color:#4a45a8;text-decoration:underline">拉黑</button>' +
      ' <button id="dmBack" style="font-size:12px;color:#4a45a8;text-decoration:underline">返回房间</button></span>';
    $('.top').parentNode.insertBefore(d, $('#conn'));
    $('#dmBack').onclick = closeDm;
    $('#dmBlock').onclick = () => {
      if (!S.peer) return;
      if (S.blocked.includes(S.peer.uid)) {
        S.blocked = S.blocked.filter(x => x !== S.peer.uid);
        toast('已解除拉黑');
      } else {
        S.blocked = S.blocked.concat(S.peer.uid);
        toast('已拉黑');
      }
      wr(LSK.blocked, S.blocked);
      closeDm();
    };
  }
  function hideDmBar() { const d = $('#dmBar'); if (d) d.remove(); }

  /* ---------- 房间 ---------- */
  const roomLabel = () => '房间 ' + S.room;
  function randRoom() {
    const AB = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    let s = '';
    for (let i = 0; i < 6; i++) s += AB[Math.floor(Math.random() * AB.length)];
    return s;
  }
  function openRoom() {
    $('#roomIn').value = S.room;
    $('#roomErr').textContent = '';
    $('#mask').classList.add('on'); $('#sRoom').classList.add('on');
  }
  function closeRoom() { $('#mask').classList.remove('on'); $('#sRoom').classList.remove('on'); }

  async function joinRoom(code) {
    code = String(code || '').trim().toUpperCase().replace(/[^A-Z0-9]/g, '');
    if (code.length < 3) { $('#roomErr').textContent = '至少 3 个字符'; return; }
    if (code === S.room && S.mq && S.mq.connected) { closeRoom(); return; }
    // 退掉旧房间
    if (S.mq) {
      try {
        S.mq.unsubscribe(tMsgAll()); S.mq.unsubscribe(tPres());
        S.mq.publish(tPres(), JSON.stringify({ uid: S.uid, bye: 1, at: Date.now() }));
      } catch (e) {}
      try { S.mq.end(); } catch (e) {}
      S.mq = null;
    }
    S.room = code; S.peer = null; S.dmMsgs = [];
    wr(LSK.room, code);
    closeRoom();
    hideDmBar();
    $('#roomTitle').textContent = roomLabel();
    document.title = roomLabel() + ' · 遇见';
    S.online = {};
    loadHist();
    renderAll();
    renderOnline();
    startMqtt();
  }

  /* ---------- MQTT ---------- */
  function startMqtt() {
    const mq = window.MiniMqtt.createClient({ clientId: 'yh' + S.uid.slice(-6) });
    S.mq = mq;

    mq.on('connect', broker => {
      renderConn();
      $('#liveDot').className = 'dotlive';
      $('#liveTxt').textContent = '已连接';
      // 订阅通配符 = 拿到 broker 保存的全部历史 + 后续实时消息
      mq.subscribe(tMsgAll());
      mq.subscribe(tPres());
      if (S.peer) mq.subscribe(tDm(S.uid, S.peer.uid));
      // 打个招呼，让别人看到我在线
      publishPresence();
      clearInterval(S.timerPing);
      S.timerPing = setInterval(publishPresence, 25000);
    });

    mq.on('message', onMsg);
    mq.on('close', () => {
      renderConn();
      $('#liveDot').className = 'dotoff';
      $('#liveTxt').textContent = '连接断开，重连中…';
    });
    mq.on('error', () => {
      $('#liveDot').className = 'dotoff';
      $('#liveTxt').textContent = '连接中…';
    });

    clearInterval(S.timerSweep);
    S.timerSweep = setInterval(() => { renderOnline(); }, 15000);
  }

  /* ---------- 历史清理：把太老的 retained 消息从 broker 上删掉 ----------
   * 删法：向同一主题发一个空载荷、retain=true 的消息，broker 就会清掉它。
   */
  let lastTrim = 0;
  function trimHistory() {
    if (!S.mq || !S.mq.connected) return;
    if (S.msgs.length <= HIST_KEEP) return;
    if (Date.now() - lastTrim < 20000) return;      // 别太频繁
    lastTrim = Date.now();
    const extra = S.msgs.slice(0, S.msgs.length - HIST_KEEP);
    for (const m of extra) {
      if (!m._k) continue;
      try { S.mq.publish(tMsg(m._k), '', true); } catch (e) {}
    }
    S.msgs = S.msgs.slice(-HIST_KEEP);
    saveHist();
  }

  function publishPresence() {
    if (!S.mq || !S.mq.connected || !S.me) return;
    try {
      S.mq.publish(tPres(), JSON.stringify({
        uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, at: Date.now(),
      }));
    } catch (e) {}
  }

  /* ---------- 我的资料 ---------- */
  let pickedAv = '🙂';
  function renderAvPick() {
    $('#avPick').innerHTML = AVATARS.map(a =>
      '<span data-av="' + a + '"' + (a === pickedAv ? ' class="on"' : '') + '>' + a + '</span>').join('');
    $('#avPick').querySelectorAll('span').forEach(el =>
      el.onclick = () => { pickedAv = el.dataset.av; renderAvPick(); });
  }
  function openMe() {
    pickedAv = (S.me && S.me.avatar) || '🙂';
    renderAvPick();
    $('#nickIn').value = (S.me && S.me.nick) || '';
    $('#meErr').textContent = '';
    $('#mask').classList.add('on'); $('#sMe').classList.add('on');
    setTimeout(() => $('#nickIn').focus(), 250);
  }
  function closeMe() { $('#mask').classList.remove('on'); $('#sMe').classList.remove('on'); }

  function doMe() {
    const nick = $('#nickIn').value.trim();
    if (!nick) { $('#meErr').textContent = '起个名字吧'; return; }
    S.me = { nick, avatar: pickedAv };
    wr(LSK.me, S.me);
    $('#topMe').textContent = pickedAv;
    closeMe();
    toast('好，' + nick + '！');
    publishPresence();
  }

  /* ---------- 绑定 ---------- */
  function bind() {
    $('#btnSend').onclick = doSend;
    $('#btnPic').onclick = pickImage;
    $('#topMe').onclick = openMe;
    $('#topRoom').onclick = openRoom;
    $('#meGo').onclick = doMe;
    $('#roomGo').onclick = () => joinRoom($('#roomIn').value);
    $('#roomNew').onclick = () => { $('#roomIn').value = randRoom(); };
    $('#roomCopy').onclick = async () => {
      const txt = S.room;
      try { await navigator.clipboard.writeText(txt); }
      catch (e) {
        const ta = document.createElement('textarea');
        ta.value = txt; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch (x) {}
        document.body.removeChild(ta);
      }
      toast('房间号已复制：' + txt);
    };
    $('#mask').onclick = () => { if (S.me) { closeMe(); closeRoom(); } };
    $('#nickIn').onkeydown = e => { if (e.key === 'Enter') doMe(); };
    $('#roomIn').onkeydown = e => { if (e.key === 'Enter') joinRoom($('#roomIn').value); };

    const ta = $('#input');
    ta.oninput = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 96) + 'px'; };
    ta.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); } };

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) { publishPresence(); renderOnline(); }
    });
    window.addEventListener('beforeunload', () => {
      try { S.mq && S.mq.publish(tPres(), JSON.stringify({ uid: S.uid, bye: 1, at: Date.now() })); } catch (e) {}
    });
  }

  /* ---------- 启动 ---------- */
  function boot() {
    if (!window.MiniMqtt) {
      $('#flow').innerHTML = '<div class="empty">😕 聊天组件没加载成功<br>刷新一下试试</div>';
      return;
    }
    let uid = rd(LSK.uid, '');
    if (!uid) { uid = 'u' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); wr(LSK.uid, uid); }
    S.uid = String(uid).replace(/[^\w-]/g, '');
    S.blocked = rd(LSK.blocked, []) || [];

    // 房间：优先 URL 参数（方便分享链接），其次本机上次，最后默认大厅
    const q = new URLSearchParams(location.search).get('room');
    S.room = String(q || rd(LSK.room, '') || 'LOBBY').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12) || 'LOBBY';
    wr(LSK.room, S.room);
    $('#roomTitle').textContent = roomLabel();
    document.title = roomLabel() + ' · 遇见';

    S.me = rd(LSK.me, null);
    if (S.me && S.me.nick) $('#topMe').textContent = S.me.avatar || '🙂';

    bind();
    loadHist();
    renderAll();
    renderConn();
    startMqtt();

    if (!S.me || !S.me.nick) setTimeout(openMe, 400);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
