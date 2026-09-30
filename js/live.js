/* 直播间：播放器（HLS/FLV/嵌入）+ 商品 + 聊天
 * 后端可选：GitHub Pages 上也能跑（读静态 data/live.json，聊天降级）
 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc, money = LH.money;

  const S = {
    cfg: null, products: { items: [], categories: [] }, settings: null,
    api: null,            // 后端地址（没有则纯静态）
    lastId: 0, timer: null, pingTimer: null, sending: false,
  };

  /* ---------- 后端探测（复用与顾客端一致的策略） ---------- */
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
      } catch (e) { /* 试下一个 */ }
    }
    S.api = null;
  }

  /* ---------- 直播状态 ---------- */
  async function loadLive() {
    if (S.api) {
      try {
        const r = await fetch(S.api + '/api/live/config', { cache: 'no-store' });
        const d = await r.json();
        if (d.ok) { S.cfg = d.live; setViewers(d.viewers); return; }
      } catch (e) { /* 落到静态 */ }
    }
    try {
      const r = await fetch('data/live.json?t=' + Date.now(), { cache: 'no-store' });
      S.cfg = await r.json();
    } catch (e) { S.cfg = { on: false, mode: 'none' }; }
  }

  function setViewers(n) { $('#viewers').textContent = Number(n) || 0; }

  function renderHead() {
    const c = S.cfg || {};
    document.title = (c.title || '直播间') + ' · 卤味小店';
    $('#liveTitle').textContent = c.title || '直播间';
    const b = $('#liveBadge');
    if (c.on) {
      b.classList.remove('badge-off');
      $('#liveText').textContent = '直播中';
    } else {
      b.classList.add('badge-off');
      $('#liveText').textContent = '未开播';
    }
    const n = $('#liveNotice');
    if (c.notice) { n.textContent = c.notice; n.style.display = ''; } else n.style.display = 'none';
  }

  /* ---------- 播放器 ---------- */
  function playerPlaceholder(html) { $('#player').innerHTML = '<div class="ph">' + html + '</div>'; }

  async function setupPlayer() {
    const c = S.cfg || {};
    const box = $('#player');

    if (!c.on) {
      playerPlaceholder('<span class="ic">💤</span>主播还没开播<br>先去挑点好吃的，开播就有提醒');
      return;
    }
    if (!c.url || c.mode === 'none') {
      playerPlaceholder('<span class="ic">🔧</span>直播已开启，但还没配置视频地址<br>' +
        '<span style="font-size:12px">主播可在开播控制台里填</span>');
      return;
    }

    if (c.mode === 'embed') {
      box.innerHTML = '<iframe src="' + esc(c.url) + '" allow="autoplay; fullscreen; picture-in-picture" ' +
        'allowfullscreen referrerpolicy="no-referrer"></iframe>';
      return;
    }

    // hls / flv：用原生 video
    box.innerHTML =
      (c.cover ? '<img class="cover" src="' + esc(c.cover) + '" alt="">' : '') +
      '<video id="v" controls playsinline autoplay muted></video>';
    const v = $('#v');
    const url = c.url;

    if (c.mode === 'hls') {
      if (v.canPlayType('application/vnd.apple.mpegurl')) {
        v.src = url;                       // Safari / iOS 原生支持
      } else if (window.Hls && window.Hls.isSupported()) {
        const hls = new window.Hls({ lowLatencyMode: true, liveSyncDurationCount: 3 });
        hls.loadSource(url);
        hls.attachMedia(v);
        hls.on(window.Hls.Events.ERROR, (e, data) => {
          if (!data || !data.fatal) return;
          playerPlaceholder('⚠️ 直播流断了，正在重连…<br><span style="font-size:12px">' + esc(String(data.details || '')) + '</span>');
          setTimeout(setupPlayer, 4000);
        });
        S.hls = hls;
      } else {
        playerPlaceholder('这个浏览器不支持 HLS 播放，换个浏览器或让主播改用别的格式');
        return;
      }
    } else if (c.mode === 'flv') {
      if (window.flvjs && window.flvjs.isSupported()) {
        const p = window.flvjs.createPlayer({ type: 'flv', url, isLive: true });
        p.attachMediaElement(v); p.load(); p.play().catch(() => {});
        S.flv = p;
      } else {
        playerPlaceholder('这个浏览器不支持 FLV 播放，建议主播改用 HLS（.m3u8）');
        return;
      }
    }

    v.onerror = () => {
      playerPlaceholder('⚠️ 播放失败，正在重试…');
      setTimeout(setupPlayer, 4000);
    };
  }

  /* ---------- 商品 ---------- */
  function renderGoods() {
    const items = (S.products.items || []).filter(p => p.on !== false).slice(0, 20);
    if (!items.length) { $('#goods').innerHTML = '<div class="empty" style="color:var(--muted);font-size:13px;padding:14px">还没有上架商品</div>'; return; }
    $('#goods').innerHTML = items.map(p =>
      '<div class="card" style="display:flex;gap:12px;align-items:center;padding:10px;margin-bottom:9px;background:#fff;border-radius:14px;box-shadow:var(--shadow)">' +
        '<div style="width:60px;height:60px;border-radius:10px;overflow:hidden;flex:0 0 auto;background:#f6ece3;display:flex;align-items:center;justify-content:center">' +
          (p.img ? '<img src="' + esc(p.img) + '" style="width:100%;height:100%;object-fit:cover">' : '🍗') +
        '</div>' +
        '<div style="flex:1;min-width:0">' +
          '<div style="font-weight:700;font-size:14px">' + esc(p.name) + '</div>' +
          '<div style="font-size:12.5px;color:var(--muted)">' + esc(p.desc || '') + '</div>' +
          '<div style="color:var(--brand);font-weight:800;margin-top:2px">¥' + money(p.price) +
            '<span style="font-weight:400;color:var(--muted);font-size:12px"> / ' + esc(p.unit || '份') + '</span></div>' +
        '</div>' +
        '<a href="./" style="flex:0 0 auto;text-decoration:none;background:var(--brand);color:#fff;' +
          'font-weight:700;font-size:13px;padding:8px 15px;border-radius:20px">去买</a>' +
      '</div>'
    ).join('');
  }

  /* ---------- 聊天 ---------- */
  function addMsgs(list) {
    const box = $('#chatList');
    if (!list.length) return;
    if (box.querySelector('.empty')) box.innerHTML = '';
    for (const m of list) {
      const t = new Date(m.at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
      const d = document.createElement('div');
      d.className = 'm';
      d.innerHTML = '<b>' + esc(m.name) + '</b><span class="t">' + t + '</span><br>' + esc(m.text);
      box.appendChild(d);
      S.lastId = Math.max(S.lastId, m.id);
    }
    box.scrollTop = box.scrollHeight;
  }

  async function pollChat() {
    if (!S.api) return;
    try {
      const r = await fetch(S.api + '/api/live/chat?since=' + S.lastId, { cache: 'no-store' });
      const d = await r.json();
      if (d.ok) { addMsgs(d.messages || []); setViewers(d.viewers); }
    } catch (e) { /* 抖动忽略 */ }
  }

  async function send() {
    if (S.sending) return;
    const txt = $('#chatText').value.trim();
    if (!txt) return;
    if (!S.api) { LH.toast('聊天需要连上服务器，先加商家微信聊吧'); return; }
    S.sending = true;
    $('#btnSend').disabled = true;
    try {
      const r = await fetch(S.api + '/api/live/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: $('#chatName').value.trim(), text: txt }),
      });
      const d = await r.json();
      if (!d.ok) { LH.toast(d.error || '发送失败'); return; }
      $('#chatText').value = '';
      LH.LS.set('lh_chat_name', $('#chatName').value.trim());
      if (d.msg) addMsgs([d.msg]);
    } catch (e) {
      LH.toast('网络不太好，再试一次');
    } finally {
      S.sending = false;
      $('#btnSend').disabled = false;
      $('#chatText').focus();
    }
  }

  function chatFallback() {
    // 没有后端（GitHub Pages）时的降级：把聊天区换成联系方式
    const s = S.settings || {};
    const has = s.phone || s.wechat;
    $('#chatIn').style.display = 'none';
    $('#chatList').innerHTML =
      '<div class="chat-off">' +
      '💬 直播间聊天需要连上服务器。<br>' +
      (has
        ? '可以先联系商家：<br>' + (s.phone ? '📞 ' + esc(s.phone) + '<br>' : '') + (s.wechat ? '💬 微信 ' + esc(s.wechat) : '')
        : '商家还没留下联系方式。') +
      '</div>';
  }

  /* ---------- 启动 ---------- */
  async function boot() {
    const [settings, products] = await Promise.all([LH.loadSettings(), LH.loadProducts()]);
    S.settings = settings; S.products = products || { items: [] };

    await detectApi();
    await loadLive();
    renderHead();
    await setupPlayer();
    renderGoods();

    // 名字记住
    const nm = LH.LS.get('lh_chat_name', '');
    if (nm) $('#chatName').value = nm;

    $('#btnSend').onclick = send;
    $('#chatText').onkeydown = e => { if (e.key === 'Enter') send(); };

    if (S.api) {
      pollChat();
      S.timer = setInterval(pollChat, 3000);
      S.pingTimer = setInterval(() => {
        fetch(S.api + '/api/live/ping', { method: 'POST' }).catch(() => {});
      }, 30000);
      // 每 20 秒刷新直播状态（主播可能刚开播/改地址）
      setInterval(async () => {
        const old = JSON.stringify(S.cfg);
        await loadLive();
        if (JSON.stringify(S.cfg) !== old) { renderHead(); setupPlayer(); }
      }, 20000);
    } else {
      chatFallback();
    }

    // 页脚
    const f = ['📺 直播间'];
    if (settings.deliveryArea) f.push(settings.deliveryArea);
    if (Number(settings.minOrder) > 0) f.push('起送 ¥' + money(settings.minOrder));
    $('#footer').innerHTML = '<div>' + f.map(esc).join(' · ') + '</div>' +
      '<div style="margin-top:5px"><a href="./">← 回店铺首页</a></div>';

    // 手机息屏/切回来时补拉一次
    document.addEventListener('visibilitychange', () => { if (!document.hidden) pollChat(); });
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
