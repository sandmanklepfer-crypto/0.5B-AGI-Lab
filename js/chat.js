/* 顾客端私域聊天：用手机号当会话身份，不用注册 */
(function () {
  const $ = s => document.querySelector(s);
  const esc = LH.esc;

  const S = {
    me: null, api: null, settings: null,
    phone: '', lastId: 0, timer: null, sending: false,
  };

  /* ---------- 后端探测 ---------- */
  async function detectApi() {
    const cands = [];
    const base = String((S.settings && S.settings.payApiBase) || '').replace(/\/+$/, '');
    if (base) cands.push(base);
    if (!/\.github\.io$/i.test(location.hostname)) cands.push(location.origin);
    for (const c of cands) {
      try {
        const r = await fetch(c + '/api/health', { cache: 'no-store' });
        const d = await r.json();
        if (r.ok && d && d.ok) { S.api = c; return; }
      } catch (e) { /* 下一个 */ }
    }
    S.api = null;
  }

  /* ---------- 渲染 ---------- */
  function bubble(m) {
    const mine = m.from === 'c';
    const t = new Date(m.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    const d = document.createElement('div');
    d.className = 'b' + (mine ? ' me' : '');
    d.innerHTML =
      '<div class="av">' + (mine ? '我' : '🏪') + '</div>' +
      '<div class="tx">' + esc(m.text) + '</div>' +
      '<span class="tm">' + t + '</span>';
    return d;
  }

  function append(list, scroll) {
    if (!list || !list.length) return;
    const box = $('#msgs');
    const first = !box.querySelector('.b');
    for (const m of list) {
      box.querySelector('.in').appendChild(bubble(m));
      S.lastId = Math.max(S.lastId, m.id || 0);
    }
    if (scroll !== false && (first || true)) box.scrollTop = box.scrollHeight;
  }

  function showTip(html) {
    const box = $('#msgs').querySelector('.in');
    if (box.querySelector('.tip')) return;
    const d = document.createElement('div');
    d.className = 'tip';
    d.innerHTML = html;
    box.insertBefore(d, box.firstChild);
  }

  /* ---------- 拉消息 ---------- */
  async function poll() {
    if (!S.api || !S.phone) return;
    try {
      const r = await fetch(S.api + '/api/chat?phone=' + encodeURIComponent(S.phone) + '&since=' + S.lastId, { cache: 'no-store' });
      const d = await r.json();
      if (d.ok) append(d.messages || []);
    } catch (e) { /* 忽略抖动 */ }
  }

  /* ---------- 发送 ---------- */
  async function send() {
    const el = $('#input');
    const text = el.value.trim();
    if (!text || S.sending) return;
    if (!S.api) { LH.toast('聊天需要连上服务器，先加商家微信吧'); return; }
    S.sending = true;
    $('#btnSend').disabled = true;
    try {
      const r = await fetch(S.api + '/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: S.phone, name: (S.me && S.me.name) || '', text }),
      });
      const d = await r.json();
      if (!d.ok) { LH.toast(d.error || '发送失败'); return; }
      el.value = ''; el.style.height = 'auto';
      if (d.msg) append([d.msg]);
    } catch (e) {
      LH.toast('网络不太好，再试一次');
    } finally {
      S.sending = false;
      $('#btnSend').disabled = false;
      el.focus();
    }
  }

  /* ---------- 手机号门 ---------- */
  function askPhone(msg) {
    $('#gate').style.display = 'flex';
    $('#gateErr').textContent = msg || '';
    setTimeout(() => $('#phoneIn').focus(), 200);
  }

  async function enter(p) {
    p = String(p || '').replace(/\D/g, '');
    if (!/^1[3-9]\d{9}$/.test(p)) { $('#gateErr').textContent = '手机号看着不对，再检查一下'; return; }
    S.phone = p;
    LH.LS.set('lh_chat_phone', p);
    // 顺手并入"我的信息"，下单时也能带出来
    const me = LH.LS.get('lh_me', {}) || {};
    if (!me.phone) { me.phone = p; LH.LS.set('lh_me', me); }
    $('#gate').style.display = 'none';
    await loadHistory();
    S.timer = setInterval(poll, 3000);
  }

  async function loadHistory() {
    const box = $('#msgs').querySelector('.in');
    box.innerHTML = '';
    S.lastId = 0;
    await poll();
    if (!box.querySelector('.b')) {
      box.innerHTML = '<div class="tip">还没有聊过，说点什么吧～</div>';
    }
  }

  /* ---------- 没有后端时 ---------- */
  function noBackend() {
    const s = S.settings || {};
    $('#gate').style.display = 'none';
    $('#input').disabled = true;
    $('#input').placeholder = '当前无法在此发送消息';
    $('#btnSend').disabled = true;
    const box = $('#msgs').querySelector('.in');
    const has = s.phone || s.wechat;
    box.innerHTML =
      '<div class="tip">' +
      '💬 在线聊天需要服务器支持。<br>' +
      (has
        ? '现在就联系老板：<br>' + (s.phone ? '<b>📞 ' + esc(s.phone) + '</b><br>' : '') +
          (s.wechat ? '<b>💬 微信 ' + esc(s.wechat) + '</b>' : '')
        : '（老板还没留下联系方式）') +
      '</div>';
    if (has && s.wechat) {
      const b = document.createElement('div');
      b.style.cssText = 'text-align:center;margin-top:12px';
      b.innerHTML = '<button class="btn-ghost" id="cpWx">复制微信号</button>';
      box.appendChild(b);
      b.querySelector('#cpWx').onclick = async () => { await LH.copyText(s.wechat); LH.toast('已复制 ✅'); };
    }
  }

  /* ---------- 启动 ---------- */
  async function boot() {
    const [settings, me] = await Promise.all([LH.loadSettings(), Promise.resolve(LH.LS.get('lh_me', null))]);
    S.settings = settings; S.me = me;

    document.title = '联系商家 · ' + (settings.shopName || '卤味小店');
    $('#shopName').textContent = settings.shopName || '卤味小店';
    $('#subLine').textContent = settings.hours ? '营业时间 ' + settings.hours : '有问题直接问，看到就回';

    await detectApi();

    if (!S.api) { noBackend(); return; }

    $('#btnSend').onclick = send;
    const inp = $('#input');
    inp.onkeydown = e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
    };
    inp.oninput = () => { inp.style.height = 'auto'; inp.style.height = Math.min(inp.scrollHeight, 100) + 'px'; };
    $('#btnEnter').onclick = () => enter($('#phoneIn').value);
    $('#phoneIn').onkeydown = e => { if (e.key === 'Enter') $('#btnEnter').click(); };

    const saved = LH.LS.get('lh_chat_phone', '') || (me && me.phone) || '';
    if (saved) { $('#phoneIn').value = saved; enter(saved); }
    else askPhone('');

    document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
