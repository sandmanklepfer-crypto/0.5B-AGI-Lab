/* 商家端：顾客消息面板 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc;
  const KEY = 'lh_admin_token';

  let base = '', token = '', cur = '', lastId = 0, timer = null, sending = false;
  let threads = [];

  async function api(path, opts) {
    const r = await fetch(base + path, Object.assign({}, opts, {
      headers: Object.assign({ 'Authorization': 'Bearer ' + token }, (opts && opts.headers) || {}),
    }));
    const d = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, body: d };
  }

  /* ---------- 会话列表 ---------- */
  async function loadThreads() {
    const r = await api('/api/admin/chat/threads');
    if (!r.ok) {
      if (r.status === 403) { clearInterval(timer); showLock('Token 失效，重新输入'); }
      return;
    }
    threads = r.body.threads || [];
    const total = r.body.unread || 0;
    const pill = $('#unreadPill');
    pill.style.display = total ? '' : 'none';
    pill.textContent = total > 99 ? '99+' : total;
    renderSide();
  }

  function renderSide() {
    const side = $('#side');
    if (!threads.length) {
      side.innerHTML = '<div class="empty">还没有顾客留言<br><span style="font-size:12px">顾客在 chat.html 留言后会出现在这里</span></div>';
      return;
    }
    side.innerHTML = threads.map(t => {
      const when = t.lastAt ? new Date(t.lastAt).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '';
      return '<div class="th' + (t.phone === cur ? ' on' : '') + '" data-phone="' + esc(t.phone) + '">' +
        '<div class="r1"><span class="nm">' + esc(t.name || t.phone) + '</span>' +
        (t.unread ? '<span class="badge">' + t.unread + '</span>' : '') + '</div>' +
        '<div class="pv">' + esc(t.lastText || '') + '</div>' +
        '<div class="pv" style="font-size:11px;margin-top:2px">' + when + '</div>' +
      '</div>';
    }).join('');
    $$('#side .th').forEach(el => el.onclick = () => openThread(el.dataset.phone));
  }

  /* ---------- 打开会话 ---------- */
  async function openThread(phone) {
    cur = phone; lastId = 0;
    renderSide();
    const t = threads.find(x => x.phone === phone);
    $('#room').innerHTML =
      '<div class="top"><span class="nm">' + esc((t && t.name) || phone) + '</span>' +
      '<a href="tel:' + esc(phone) + '">📞 ' + esc(phone) + '</a>' +
      '<a href="#" id="btnDel" style="color:#c0392b">删除</a></div>' +
      '<div class="chat" id="chat"></div>' +
      '<div class="bar"><div class="in">' +
        '<textarea id="reply" rows="1" placeholder="回复…（Enter 发送）" maxlength="500"></textarea>' +
        '<button id="btnReply">发送</button>' +
      '</div></div>';

    const ta = $('#reply');
    ta.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); reply(); } };
    ta.oninput = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 100) + 'px'; };
    $('#btnReply').onclick = reply;
    $('#btnDel').onclick = async (e) => {
      e.preventDefault();
      if (!confirm('删除与 ' + phone + ' 的聊天记录？')) return;
      await api('/api/admin/chat/thread?phone=' + encodeURIComponent(phone), { method: 'DELETE' });
      cur = ''; lastId = 0;
      $('#room').innerHTML = '<div class="placeholder">← 左边选一个顾客开始回复</div>';
      loadThreads(); LH.toast('已删除');
    };

    await pollThread();
    loadThreads();   // 刷新未读（服务端已标记已读）
    ta.focus();
  }

  async function pollThread() {
    if (!cur) return;
    try {
      const r = await fetch(base + '/api/admin/chat/thread?phone=' + encodeURIComponent(cur) + '&since=' + lastId,
        { headers: { 'Authorization': 'Bearer ' + token }, cache: 'no-store' });
      const d = await r.json();
      if (!d.ok) return;
      const list = (d.thread && d.thread.msgs) || [];
      const box = $('#chat');
      if (!box) return;
      const news = list.filter(m => (m.id || 0) > lastId);
      if (!news.length) return;
      for (const m of news) {
        lastId = Math.max(lastId, m.id || 0);
        box.appendChild(bubble(m));
      }
      box.scrollTop = box.scrollHeight;
    } catch (e) { /* 忽略 */ }
  }

  function bubble(m) {
    const mine = m.from === 'm';
    const t = new Date(m.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    const d = document.createElement('div');
    d.className = 'b' + (mine ? ' me' : '');
    d.innerHTML = '<div class="av">' + (mine ? '我' : '👤') + '</div>' +
      '<div class="tx">' + esc(m.text) + '</div><span class="tm">' + t + '</span>';
    return d;
  }

  async function reply() {
    const ta = $('#reply');
    const text = ta.value.trim();
    if (!text || sending || !cur) return;
    sending = true;
    $('#btnReply').disabled = true;
    try {
      const r = await api('/api/admin/chat/reply', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: cur, text }),
      });
      if (!r.ok) { LH.toast(r.body.error || '发送失败'); return; }
      ta.value = ''; ta.style.height = 'auto';
      const box = $('#chat');
      if (box) { box.appendChild(bubble(r.body.msg)); box.scrollTop = box.scrollHeight; }
      lastId = Math.max(lastId, r.body.msg.id || 0);
    } catch (e) { LH.toast('网络不太好'); }
    finally { sending = false; $('#btnReply').disabled = false; ta.focus(); }
  }

  /* ---------- 解锁 ---------- */
  function showLock(msg) {
    $('#lockScreen').style.display = 'flex';
    if (msg) $('#lockErr').textContent = msg;
  }

  async function unlock(t) {
    token = t;
    const r = await api('/api/admin/chat/threads');
    if (!r.ok) {
      showLock(r.status === 403 ? 'Token 不对' : '连不上：' + (r.body.error || r.status));
      return;
    }
    LH.LS.set(KEY, { token: t, base });
    $('#lockScreen').style.display = 'none';
    await loadThreads();
    clearInterval(timer);
    timer = setInterval(() => { loadThreads(); pollThread(); }, 5000);
  }

  async function boot() {
    base = location.origin;
    const saved = LH.LS.get(KEY, null);
    if (saved && saved.base) base = saved.base;

    $('#btnUnlock').onclick = () => {
      const t = $('#tokInput').value.trim();
      if (t) unlock(t);
    };
    $('#tokInput').onkeydown = e => { if (e.key === 'Enter') $('#btnUnlock').click(); };

    try {
      const r = await fetch(base + '/api/health', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error('bad');
    } catch (e) {
      showLock('这个地址不是商家服务器，请从服务器的 /chat-admin.html 打开');
      return;
    }
    if (saved && saved.token) { unlock(saved.token); return; }
    setTimeout(() => $('#tokInput').focus(), 300);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
