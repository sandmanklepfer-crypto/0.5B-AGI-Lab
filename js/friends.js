/* 遇见 · 聊天交友
 * 存储：你的 GitHub 仓库（和卤味后台同一套：ghchat.js）
 * 特性：不用服务器 / 永久保存 / 跨设备 / 支持图片
 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const GH = window.GHChat;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const AVATARS = ['🐱', '🐰', '🦊', '🐼', '🐨', '🐯', '🦁', '🐸', '🐧', '🦄', '🐳', '🦋',
                   '🌸', '🍀', '⭐', '🌙', '🍜', '☕', '🎧', '🎮'];
  const LSK = {
    uid: 'yh_uid', me: 'yh_me',
    read: 'yh_read',          // { peerUid: lastReadAt }
    blocked: 'yh_blocked',    // [uid]
  };
  const ONLINE_MS = 3 * 60 * 1000;   // 3 分钟内有心跳算"在线"

  const S = {
    uid: '', me: null, view: 'hall', peer: null,
    hall: [], users: {}, threads: [], blocked: [], read: {},
    busy: false, timers: {}, lastMs: 0,
  };

  /* ---------- 小工具 ---------- */
  let toastT;
  function toast(m) {
    let el = document.querySelector('.toast');
    if (!el) { el = document.createElement('div'); el.className = 'toast'; document.body.appendChild(el); }
    el.textContent = m; el.classList.add('on');
    clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove('on'), 2000);
  }
  const readLS = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } };
  const writeLS = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} };
  function hhmm(ts) {
    const d = new Date(ts), n = new Date();
    if (d.toDateString() === n.toDateString())
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
  }
  const amOnline = uid => {
    const u = S.users[uid];
    return !!(u && u.lastSeen && Date.now() - u.lastSeen < ONLINE_MS);
  };

  /* ---------- 敏感词（本地也拦一道） ---------- */
  const BAD = ['加微信', '微信号', '加v', '转账', '借钱', '刷单', '兼职', '投资', '理财',
               '博彩', '赌博', '返利', '贷款', '裸聊', '约炮', '代付'];
  function badHit(t) {
    const s = String(t).toLowerCase();
    return BAD.filter(w => s.includes(w.toLowerCase()));
  }
  function checkText(t) {
    if (!t) return '内容不能为空';
    if (/(https?:\/\/|www\.)/i.test(t)) return '不能发链接';
    if (/\d{6,}/.test(t)) return '不能发一长串数字（防联系方式）';
    const b = badHit(t);
    if (b.length) return '包含不允许的词：' + b[0];
    return null;
  }

  /* ---------- 视图 ---------- */
  function show(v) {
    S.view = v;
    ['hall', 'msg', 'me', 'dm'].forEach(x => {
      const el = $('#v-' + x); if (el) el.classList.toggle('on', x === v);
    });
    $$('.tabs button').forEach(b => b.classList.toggle(
      'on', b.dataset.v === v || (v === 'dm' && b.dataset.v === 'msg')));
    $('#strip').classList.toggle('hid', v === 'dm' || v === 'me');
    $('#topTitle').textContent = v === 'me' ? '我' : (v === 'msg' ? '消息' : '遇见');
    if (v === 'hall') $('#hallFlow').scrollTop = 1e9;
    if (v === 'dm') $('#dmFlow').scrollTop = 1e9;
  }

  /* ---------- 气泡 ---------- */
  function bubble(m) {
    const mine = m.uid === S.uid;
    const d = document.createElement('div');
    d.className = 'b' + (mine ? ' me' : '');
    const isPic = !!m.img;
    d.innerHTML =
      '<div class="av">' + esc(m.avatar || '🙂') + '</div>' +
      '<div class="wrap">' +
        (mine ? '' : '<div class="who2">' + esc(m.nick || '') + '</div>') +
        '<div class="tx' + (isPic ? ' pic' : '') + '">' +
          (m.text ? esc(m.text) : '') +
          (isPic ? '<img src="' + esc(m.img) + '" loading="lazy" alt="图片">' : '') +
        '</div>' +
      '</div>';
    return d;
  }

  /* ---------- 大厅 ---------- */
  async function loadHall(first) {
    try {
      const r = await GH.hallRead();
      const list = r.msgs || [];
      const box = $('#hallFlow');
      if (first) box.innerHTML = '';
      const have = new Set(S.hall.map(m => m.id));
      const news = list.filter(m => !have.has(m.id));
      S.hall = list;
      if (!list.length && first) {
        box.innerHTML = '<div class="empty">还没有人说话<br>打个招呼吧 👋</div>';
      }
      if (news.length) {
        const e = box.querySelector('.empty'); if (e) e.remove();
        for (const m of news) {
          if (S.blocked.includes(m.uid)) continue;
          box.appendChild(bubble(m));
        }
        box.scrollTop = box.scrollHeight;
      }
    } catch (e) { /* 抖动忽略 */ }
  }

  async function sendHall() {
    const ta = $('#hallIn'), t = ta.value.trim();
    if (!t || S.busy) return;
    if (needToken()) return toastNeedToken();
    const err = checkText(t);
    if (err) return toast(err);
    S.busy = true; $('#hallSend').disabled = true;
    try {
      const msg = { id: GH.uid16(), uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, text: t, at: Date.now() };
      const r = await GH.hallSend(msg);
      if (!r.ok) return toast(r.error || '保存失败');
      ta.value = ''; ta.style.height = 'auto';
      const box = $('#hallFlow');
      const e = box.querySelector('.empty'); if (e) e.remove();
      S.hall.push(msg);
      box.appendChild(bubble(msg));
      box.scrollTop = box.scrollHeight;
    } catch (e) { toast('保存失败：' + e.message); }
    finally { S.busy = false; $('#hallSend').disabled = false; ta.focus(); }
  }

  /* ---------- 在线的人 ---------- */
  async function loadUsers() {
    try {
      S.users = await GH.usersRead();
      const box = $('#onlineRow');
      const list = Object.entries(S.users)
        .filter(([uid, u]) => uid !== S.uid && amOnline(uid) && !S.blocked.includes(uid))
        .map(([uid, u]) => Object.assign({ uid }, u))
        .sort((a, b) => (b.lastSeen || 0) - (a.lastSeen || 0));
      $('#onlineN').textContent = list.length;
      if (!list.length) {
        box.innerHTML = '<span style="color:var(--mut);font-size:12.5px;padding:8px 0">现在只有你在线，等等看～</span>';
      } else {
        box.innerHTML = list.map(u =>
          '<div class="who" data-uid="' + esc(u.uid) + '">' +
            '<div class="av">' + esc(u.avatar || '🙂') + '</div>' +
            '<div class="nm"><span class="dot">●</span> ' + esc(u.nick || '') + '</div>' +
          '</div>').join('');
        box.querySelectorAll('.who').forEach(el =>
          el.onclick = () => openDM(el.dataset.uid));
      }
      $('#topSub').textContent = list.length + ' 人在线 · 数据存在你自己的仓库里';
    } catch (e) { /* 忽略 */ }
  }

  async function heartbeat() {
    if (!S.me) return;
    try { await GH.userUpsert(S.uid, { nick: S.me.nick, avatar: S.me.avatar, blocked: S.blocked }); }
    catch (e) { /* 忽略 */ }
  }

  /* ---------- 消息列表 ---------- */
  async function loadThreads() {
    try {
      const pairs = await GH.dmIndexRead();
      const mine = pairs.filter(p => p.a === S.uid || p.b === S.uid);
      const out = [];
      for (const p of mine) {
        const peer = p.a === S.uid ? p.b : p.a;
        if (S.blocked.includes(peer)) continue;
        let msgs = [];
        try { const r = await GH.dmRead(S.uid, peer); msgs = r.msgs || []; } catch (e) { continue; }
        if (!msgs.length) continue;
        const last = msgs[msgs.length - 1];
        const seen = S.read[peer] || 0;
        const unread = msgs.filter(m => m.uid !== S.uid && m.at > seen).length;
        const u = S.users[peer] || {};
        out.push({ uid: peer, nick: u.nick || peer.slice(0, 6), avatar: u.avatar || '🙂',
          lastText: last.img ? '[图片]' : last.text, lastAt: last.at, unread });
      }
      out.sort((a, b) => b.lastAt - a.lastAt);
      S.threads = out;
      const total = out.reduce((a, t) => a + t.unread, 0);
      const dot = $('#tabDot');
      if (total) { dot.textContent = total > 99 ? '99+' : total; dot.classList.remove('hid'); }
      else dot.classList.add('hid');
      if (S.view === 'msg') renderThreads();
    } catch (e) { /* 忽略 */ }
  }

  function renderThreads() {
    const box = $('#dmList');
    if (!S.threads.length) {
      box.innerHTML = '<div class="empty">还没有人跟你聊过<br>去「大厅」说句话，或者点上面的头像找人聊</div>';
      return;
    }
    box.innerHTML = S.threads.map(t =>
      '<div class="li" data-uid="' + esc(t.uid) + '">' +
        '<div class="av">' + esc(t.avatar) + '</div>' +
        '<div class="mid"><div class="nm">' + esc(t.nick) +
          '<span style="font-size:11px;color:' + (amOnline(t.uid) ? 'var(--ok)' : 'var(--mut)') + ';margin-left:6px">' +
          (amOnline(t.uid) ? '● 在线' : '离线') + '</span></div>' +
        '<div class="pv">' + esc(t.lastText || '') + '</div></div>' +
        '<div class="rt"><div class="tm">' + hhmm(t.lastAt) + '</div>' +
        (t.unread ? '<div class="un">' + t.unread + '</div>' : '') + '</div>' +
      '</div>').join('');
    box.querySelectorAll('.li').forEach(el => el.onclick = () => openDM(el.dataset.uid));
  }

  /* ---------- 私聊 ---------- */
  let dmMsgs = [];
  async function openDM(peer) {
    if (!peer || peer === S.uid) return;
    const u = S.users[peer] || {};
    S.peer = { uid: peer, nick: u.nick || peer.slice(0, 6), avatar: u.avatar || '🙂' };
    $('#dmNm').textContent = S.peer.nick;
    $('#dmAv').textContent = S.peer.avatar;
    $('#dmFlow').innerHTML = '<div class="loading">加载中…</div>';
    dmMsgs = [];
    show('dm');
    await loadDM(true);
    markRead();
    setTimeout(() => $('#dmIn').focus(), 150);
  }

  async function loadDM(first) {
    if (!S.peer) return;
    try {
      const r = await GH.dmRead(S.uid, S.peer.uid);
      const list = r.msgs || [];
      const box = $('#dmFlow');
      if (first) box.innerHTML = '';
      const have = new Set(dmMsgs.map(m => m.id));
      const news = list.filter(m => !have.has(m.id));
      dmMsgs = list;
      if (!list.length && first) {
        box.innerHTML = '<div class="empty">还没聊过，说句话打破沉默吧～</div>';
      }
      if (news.length) {
        const e = box.querySelector('.empty'); if (e) e.remove();
        for (const m of news) box.appendChild(bubble(m));
        box.scrollTop = box.scrollHeight;
      }
    } catch (e) { /* 忽略 */ }
  }

  function markRead() {
    if (!S.peer) return;
    S.read[S.peer.uid] = Date.now();
    writeLS(LSK.read, S.read);
  }

  async function sendDM() {
    const ta = $('#dmIn'), t = ta.value.trim();
    if (!t || S.busy || !S.peer) return;
    if (needToken()) return toastNeedToken();
    const err = checkText(t);
    if (err) return toast(err);
    S.busy = true; $('#dmSend').disabled = true;
    try {
      const msg = { id: GH.uid16(), uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, text: t, at: Date.now() };
      const r = await GH.dmSend(S.uid, S.peer.uid, msg);
      if (!r.ok) return toast(r.error || '保存失败');
      await GH.dmIndexAdd(S.uid, S.peer.uid).catch(() => {});
      ta.value = ''; ta.style.height = 'auto';
      const box = $('#dmFlow');
      const e = box.querySelector('.empty'); if (e) e.remove();
      dmMsgs.push(msg);
      box.appendChild(bubble(msg));
      box.scrollTop = box.scrollHeight;
      markRead();
      heartbeat();
    } catch (e) { toast('保存失败：' + e.message); }
    finally { S.busy = false; $('#dmSend').disabled = false; ta.focus(); }
  }

  /* ---------- 发图片 ---------- */
  async function pickImage(target) {
    const inp = $('#filePick');
    inp.value = '';
    inp.onchange = async () => {
      const f = inp.files && inp.files[0];
      if (!f) return;
      if (!/^image\//.test(f.type)) return toast('只能发图片');
      toast('图片压缩中…');
      let dataUrl;
      try { dataUrl = await GH.compressImage(f, 900, 0.78); }
      catch (e) { return toast('图片处理失败'); }
      const kb = Math.round(dataUrl.length * 0.75 / 1024);
      if (kb > 900) return toast('图片太大了（' + kb + 'KB），换一张');
      toast('上传中（' + kb + 'KB）…');
      try {
        const url = await GH.uploadImage(dataUrl, 'jpg');
        if (target === 'hall') {
          const msg = { id: GH.uid16(), uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, img: url, text: '', at: Date.now() };
          const r = await GH.hallSend(msg);
          if (!r.ok) return toast(r.error || '发送失败');
          S.hall.push(msg);
          const box = $('#hallFlow');
          const e = box.querySelector('.empty'); if (e) e.remove();
          box.appendChild(bubble(msg)); box.scrollTop = box.scrollHeight;
        } else {
          if (!S.peer) return;
          const msg = { id: GH.uid16(), uid: S.uid, nick: S.me.nick, avatar: S.me.avatar, img: url, text: '', at: Date.now() };
          const r = await GH.dmSend(S.uid, S.peer.uid, msg);
          if (!r.ok) return toast(r.error || '发送失败');
          await GH.dmIndexAdd(S.uid, S.peer.uid).catch(() => {});
          dmMsgs.push(msg);
          const box = $('#dmFlow');
          const e = box.querySelector('.empty'); if (e) e.remove();
          box.appendChild(bubble(msg)); box.scrollTop = box.scrollHeight;
        }
        toast('图片已发送');
      } catch (e) {
        toast('上传失败：' + (e.message || '检查 Token 权限'));
      }
    };
    inp.click();
  }

  /* ---------- 拉黑 / 举报 ---------- */
  function openAct() {
    if (!S.peer) return;
    $('#actTitle').textContent = S.peer.nick;
    $('#actBlock').textContent = S.blocked.includes(S.peer.uid) ? '✅ 解除拉黑' : '🚫 拉黑';
    $('#mask').classList.add('on'); $('#sAct').classList.add('on');
  }
  function closeAct() { $('#mask').classList.remove('on'); $('#sAct').classList.remove('on'); }
  function closeGh() { $('#mask').classList.remove('on'); $('#sGh').classList.remove('on'); }
  function closeMe() { $('#mask').classList.remove('on'); $('#sMe').classList.remove('on'); }

  async function toggleBlock() {
    if (!S.peer) return;
    const on = !S.blocked.includes(S.peer.uid);
    S.blocked = on ? S.blocked.concat(S.peer.uid) : S.blocked.filter(x => x !== S.peer.uid);
    writeLS(LSK.blocked, S.blocked);
    toast(on ? '已拉黑' : '已解除');
    closeAct();
    heartbeat();
    loadHall(true); loadThreads();
  }
  async function doReport() {
    if (!S.peer) return;
    const why = prompt('说说为什么要举报（可留空）');
    if (why === null) return;
    try {
      const list = (await GH.getJSON('reports.json')).data || { items: [] };
      list.items = list.items || [];
      list.items.push({ id: GH.uid16(), by: S.uid, byNick: S.me.nick,
        target: S.peer.uid, targetNick: S.peer.nick, why: String(why).slice(0, 100), at: Date.now() });
      if (list.items.length > 300) list.items = list.items.slice(-300);
      await GH.putJSON('reports.json', list, '举报 ' + S.peer.nick);
      toast('已举报，记录在你的仓库里');
      closeAct();
    } catch (e) { toast('举报失败：' + e.message); }
  }

  /* ---------- 我的 ---------- */
  function renderMe() {
    const blockedNames = S.blocked.map(u => (S.users[u] && S.users[u].nick) || u.slice(0, 6));
    $('#meBox').innerHTML =
      '<div class="prof">' +
        '<div class="big">' + esc(S.me.avatar || '🙂') + '</div>' +
        '<div class="nick">' + esc(S.me.nick) + '</div>' +
        '<div class="uid">ID ' + esc(S.uid.slice(0, 14)) + '</div>' +
      '</div>' +
      '<div class="card">' +
        '<h3>我的资料</h3>' +
        '<p>昵称和头像随时能改，改了别人看到的也是新的。</p>' +
        '<div class="r"><button class="go" id="btnEdit">改昵称 / 头像</button></div>' +
      '</div>' +
      '<div class="card safe">' +
        '<h3>🛡️ 安全提示</h3>' +
        '<p>' +
          '· 这里<b>不用手机号、不用实名</b>，就是个聊天的地方<br>' +
          '· <b>别透露</b>真实姓名、住址、单位、银行卡<br>' +
          '· <b>任何要钱的都是骗子</b>：投资、刷单、借钱、代付<br>' +
          '· 遇到骚扰点右上角 <b>⋯ → 拉黑</b>，顺手举报<br>' +
          '· <b>图片是公开的</b>：别发身份证、证件照、私密照' +
        '</p>' +
      '</div>' +
      (function () {
        const c = GH.cfg();
        const w = GH.canWrite();
        const fromLh = GH.hasLhCfg() && c._fromLh;
        return '<div class="card">' +
          '<h3>存储 ' + (w
            ? '<span style="color:var(--ok)">✅ 已连接</span>'
            : '<span style="color:var(--warn)">⚠️ 只读模式</span>') + '</h3>' +
          '<p>' +
            '数据存在 <b>' + esc(c.owner + '/' + c.repo) + '</b> 的 <code>' + esc(c.path || '/') + '</code> 目录。<br>' +
            (w
              ? (fromLh ? '🔑 复用你<b>卤味后台</b>已填过的 Token，不用再填一次。' : '🔑 已配置 Token。')
              : '⚠️ <b>现在只能看、不能发言</b>。要发言需要连一次仓库（填个 Token）。') +
          '</p>' +
          '<div class="r">' +
            (w ? '' : '<button class="go" id="btnGh">连上仓库（开始发言）</button>') +
            (w ? '<button id="btnGh">改仓库 / Token</button>' : '') +
            '<button id="btnTest">测试连接</button>' +
            '<button id="btnDiag">看诊断</button>' +
            (c.token ? '<button id="btnClear">清除本机 Token</button>' : '') +
          '</div>' +
          '<div id="testBox" style="margin-top:10px;font-size:12.5px"></div>' +
        '</div>';
      })() +
      '<div class="card">' +
        '<h3>已拉黑（' + S.blocked.length + '）</h3>' +
        '<p>' + (blockedNames.length ? esc(blockedNames.join('、')) : '还没有拉黑任何人。') + '</p>' +
      '</div>' +
      '<div style="height:20px"></div>';

    // 动态生成的按钮可能因为各种原因拿不到，这里全部容错，避免整页白屏
    const on = (sel, fn) => { const el = $(sel); if (el) el.onclick = fn; };
    on('#btnEdit', openMe);
    on('#btnGh', openGh);
    on('#btnTest', async () => {
      const tb = $('#testBox');
      const show = html => { if (tb) tb.innerHTML = html; };
      show('测试中…');
      try {
        const r = await GH.test();
        show(r.ok
          ? '<span style="color:var(--ok)">✅ 连接正常：' + esc(r.user) + ' → ' + esc(r.repo) +
            (r.canWrite ? '（可写入）' : '（⚠️ 没有写权限）') + '</span>'
          : '<span style="color:var(--bad)">❌ ' + esc(r.error) + '</span>');
      } catch (e) {
        show('<span style="color:var(--bad)">❌ ' + esc(e.message) + '</span>');
      }
    });
    on('#btnDiag', () => {
      const c = GH.cfg();
      let lh = {}, mine = {};
      try { lh = JSON.parse(localStorage.getItem('lh_gh') || '{}') || {}; } catch (e) {}
      try { mine = JSON.parse(localStorage.getItem('yh_gh') || '{}') || {}; } catch (e) {}
      const mark = t => t ? (String(t).slice(0, 7) + '…(' + String(t).length + '位)') : '(空)';
      const box = $('#testBox');
      if (!box) return;
      box.style.textAlign = 'left';
      box.innerHTML =
        '<div style="background:#f7f7fb;border-radius:10px;padding:10px;font-family:monospace;font-size:11.5px;line-height:1.9">' +
        '<b>卤味后台存的(lh_gh)：</b><br>' +
        '  owner=' + esc(lh.owner || '(无)') + '<br>' +
        '  repo=' + esc(lh.repo || '(无)') + '<br>' +
        '  branch=' + esc(lh.branch || '(无)') + '<br>' +
        '  token=' + esc(mark(lh.token)) + '<br>' +
        '<b>本页存的(yh_gh)：</b><br>' +
        '  owner=' + esc(mine.owner || '(无)') + '<br>' +
        '  token=' + esc(mark(mine.token)) + '<br>' +
        '<b>实际生效：</b><br>' +
        '  ' + esc(c.owner + '/' + c.repo) + ' @ ' + esc(c.branch) + '/' + esc(c.path) + '<br>' +
        '  token=' + esc(mark(c.token)) + '　' +
        (c._fromLh ? '<span style="color:#1f9d55">借用自卤味后台</span>' : (c.token ? '本页设置' : '<span style="color:#e03131">无</span>')) + '<br>' +
        '  可发言=' + (GH.canWrite() ? '<span style="color:#1f9d55">是</span>' : '<span style="color:#e03131">否</span>') +
        '</div>';
    });
    on('#btnClear', () => {
      if (!confirm('清掉本机保存的 Token？清掉后要重新填。')) return;
      GH.clearCfg();
      location.reload();
    });
  }

  /* ---------- 设置仓库 ---------- */
  function openGh() {
    const c = GH.cfg();
    // 已预填好仓库信息，多数情况下只需粘一个 Token
    $('#g_owner').value = c.owner || '';
    $('#g_repo').value = c.repo || '';
    $('#g_branch').value = c.branch || 'gh-pages';
    $('#g_path').value = c.path || 'social';
    $('#g_token').value = c.token || '';
    // 如果借用的是卤味后台的令牌，提示一下不用重填
    if (c._fromLh) {
      $('#ghErr').innerHTML = '<span style="color:var(--ok)">✅ 已自动沿用你卤味后台的令牌，一般不用改</span>';
    } else {
      $('#ghErr').textContent = '';
    }
    $('#mask').classList.add('on'); $('#sGh').classList.add('on');
    // 没 Token 时直接聚焦到 Token 那格
    if (!c.token) setTimeout(() => $('#g_token').focus(), 300);
  }
  async function doGh() {
    const c = {
      owner: $('#g_owner').value.trim(),
      repo: $('#g_repo').value.trim(),
      branch: $('#g_branch').value.trim() || 'main',
      path: $('#g_path').value.trim().replace(/^\/|\/$/g, ''),
      token: $('#g_token').value.trim(),
    };
    if (!c.owner || !c.repo || !c.token) { $('#ghErr').textContent = '三项都要填'; return; }
    $('#ghErr').textContent = '连接中…';
    GH.saveCfg(c);
    try {
      const r = await GH.test();
      if (!r.canWrite) throw new Error('这个 Token 没有写入权限');
      $('#mask').classList.remove('on'); $('#sGh').classList.remove('on');
      toast('连上了：' + r.repo);
      await boot();
    } catch (e) {
      $('#ghErr').textContent = '❌ ' + (e.message || '连不上') + '（检查 Token 是否勾了 Contents: Read and write）';
    }
  }

  /* ---------- 只读模式提示（没 Token 时） ---------- */
  function needToken() {
    const c = GH.cfg();
    return !c.token;
  }
  function toastNeedToken() {
    toast('要发言需要先连上仓库（点「我」→ 存储设置）');
    show('me'); renderMe();
  }

  /* ---------- 身份 ---------- */
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
  async function doMe() {
    const nick = $('#nickIn').value.trim();
    if (!nick) { $('#meErr').textContent = '起个名字吧'; return; }
    S.me = { nick, avatar: pickedAv };
    writeLS(LSK.me, S.me);
    $('#topMe').textContent = pickedAv;
    $('#mask').classList.remove('on'); $('#sMe').classList.remove('on');
    await heartbeat().catch(() => {});
    toast('欢迎，' + nick + '！');
    // 关键：设完昵称要立刻拉一次数据，否则大厅空着要等 6 秒
    renderConn();
    renderMe();
    await Promise.all([
      loadHall(true).catch(() => {}),
      loadUsers().catch(() => {}),
      loadThreads().catch(() => {}),
    ]);
    startLoops();
  }

  /* ---------- 主循环 ---------- */
  function startLoops() {
    Object.values(S.timers).forEach(clearInterval);
    // 大厅
    S.timers.hall = setInterval(() => { if (S.view !== 'dm') loadHall(false); }, 6000);
    // 用户/在线
    S.timers.users = setInterval(() => { if (S.view !== 'dm') loadUsers(); }, 15000);
    // 私聊
    S.timers.dm = setInterval(() => { if (S.peer) loadDM(false); }, 6000);
    // 会话列表
    S.timers.threads = setInterval(() => { if (S.view === 'msg') loadThreads(); }, 15000);
    // 心跳（保持"在线"）
    S.timers.hb = setInterval(heartbeat, 45000);
  }

  /* ---------- 连接状态条 ---------- */
  function renderConn() {
    const bar = $('#connbar');
    if (!bar) return;
    const c = GH.cfg();
    const w = GH.canWrite();
    const fromLh = GH.hasLhCfg() && c._fromLh;
    if (w) {
      bar.className = 'connbar ok';
      bar.innerHTML = '✅ 已连上 ' + esc(c.owner + '/' + c.repo) +
        (fromLh ? ' · 🔑 用的是你<b>卤味后台</b>那个令牌，不用重填' : '');
      // 3 秒后自动收起，不挡视线
      setTimeout(() => { if (bar.className.indexOf('ok') >= 0) bar.className = 'connbar hid'; }, 3500);
    } else {
      bar.className = 'connbar warn';
      bar.innerHTML = '⚠️ <b>现在只能看，不能发言</b> · ' +
        '<button id="goConn">点这里连上仓库</button>';
      const b = $('#goConn');
      if (b) b.onclick = openGh;
    }
  }

  /* ---------- 启动 ---------- */
  async function boot() {
    // 身份（本机生成，不用填任何东西）
    let uid = readLS(LSK.uid, '');
    if (!uid) { uid = 'u' + GH.uid16(); writeLS(LSK.uid, uid); }
    S.uid = String(uid).replace(/[^\w-]/g, '');
    S.blocked = readLS(LSK.blocked, []) || [];
    S.read = readLS(LSK.read, {}) || {};

    // 角色：老板（有卤味后台配置）还是普通用户（只有本机身份）
    S.isOwner = GH.canWrite();

    const me = readLS(LSK.me, null);
    if (!me || !me.nick) { openMe(); return; }
    S.me = me;
    $('#topMe').textContent = me.avatar || '🙂';

    // 先渲染，再拉数据（先让界面活起来）
    show('hall');
    renderConn();
    renderMe();

    // 首次拉取（读不需要 Token）
    await heartbeat().catch(() => {});
    await Promise.all([
      loadHall(true).catch(() => {}),
      loadUsers().catch(() => {}),
      loadThreads().catch(() => {}),
    ]);
    startLoops();
  }

  function bind() {
    $$('.tabs button').forEach(b => b.onclick = () => {
      show(b.dataset.v);
      if (b.dataset.v === 'msg') loadThreads();
      if (b.dataset.v === 'me') renderMe();
      if (b.dataset.v === 'hall') { loadHall(false); loadUsers(); }
    });
    $('#topMe').onclick = () => { show('me'); renderMe(); };
    $('#hallSend').onclick = sendHall;
    $('#dmSend').onclick = sendDM;
    $('#hallPic').onclick = () => pickImage('hall');
    $('#dmPic').onclick = () => pickImage('dm');
    $('#dmBack').onclick = () => { S.peer = null; dmMsgs = []; show('msg'); loadThreads(); };
    $('#dmMore').onclick = openAct;
    $('#actBlock').onclick = toggleBlock;
    $('#actReport').onclick = doReport;
    $('#actClose').onclick = closeAct;
    $('#mask').onclick = () => {
      // 第一次进来还没起昵称时，不允许点遮罩关掉（否则就没法继续了）
      if (!S.me || !S.me.nick) return;
      closeAct(); closeGh(); closeMe();
    };
    $('#ghGo').onclick = doGh;
    $('#meGo').onclick = doMe;
    $('#nickIn').onkeydown = e => { if (e.key === 'Enter') doMe(); };

    [['#hallIn', sendHall], ['#dmIn', sendDM]].forEach(([sel, fn]) => {
      const ta = $(sel);
      ta.oninput = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 96) + 'px'; };
      ta.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); fn(); } };
    });

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) return;
      if (S.view === 'dm') { loadDM(false); markRead(); }
      else { loadHall(false); loadUsers(); loadThreads(); }
      heartbeat();
    });
  }

  document.addEventListener('DOMContentLoaded', () => { bind(); boot(); });
})();
