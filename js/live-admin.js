/* 开播控制台：改直播设置 + 看聊天 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc;
  const KEY = 'lh_admin_token';
  let base = '', token = '', mode = 'hls', lastId = 0, timer = null, cfg = null;

  async function api(path, opts) {
    const r = await fetch(base + path, Object.assign({}, opts, {
      headers: Object.assign({ 'Authorization': 'Bearer ' + token }, (opts && opts.headers) || {}),
    }));
    const d = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, body: d };
  }

  /* ---------- 模式说明 ---------- */
  const HELP = {
    hls: {
      label: 'HLS 播放地址（.m3u8）',
      ph: 'https://你的域名/live/stream.m3u8',
      hint: '推荐。兼容性最好，iPhone/安卓微信里都能播。延迟约 5~15 秒。',
      help: '自建：用 SRS 或 nginx-rtmp 推流后，会得到一个 .m3u8 地址。<br>' +
            '第三方：阿里云/腾讯云直播、B站等都能给到 m3u8。',
    },
    flv: {
      label: 'FLV 播放地址（.flv）',
      ph: 'https://你的域名/live/stream.flv',
      hint: '延迟低（约 1~3 秒），但 iOS 微信里播不了（iPhone 用户会看不了）。',
      help: '适合观众主要是安卓的情况。iPhone 建议用 HLS。',
    },
    embed: {
      label: '第三方嵌入地址（iframe）',
      ph: 'https://live.example.com/room/123',
      hint: '直接嵌别人的直播间页面。有些平台禁止被嵌（会白屏），需实测。',
      help: '把第三方直播间的分享链接贴进来即可，不需要自己搭服务器。',
    },
    none: { label: '暂不提供视频', ph: '', hint: '只显示公告和商品，不开视频。', help: '' },
  };

  function renderMode() {
    const h = HELP[mode] || HELP.hls;
    $('#urlLabel').textContent = h.label;
    $('#f_url').placeholder = h.ph;
    $('#urlHint').textContent = h.hint;
    $('#modeHelp').innerHTML = h.help;
    $('#f_url').parentNode.style.display = (mode === 'none') ? 'none' : '';
    $$('.mode-tabs button').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
  }

  /* ---------- 填表 ---------- */
  function fill(c) {
    cfg = c;
    $('#swLive').classList.toggle('on', !!c.on);
    $('#stHint').textContent = c.on ? '顾客现在能看到「直播中」' : '关闭时顾客看到「未开播」';
    $('#f_title').value = c.title || '';
    $('#f_notice').value = c.notice || '';
    $('#f_cover').value = c.cover || '';
    $('#f_url').value = c.url || '';
    $('#f_chatOn').checked = c.chatOn !== false;
    $('#f_banned').value = (c.bannedWords || []).join(',');
    mode = c.mode || 'hls';
    renderMode();
  }

  async function load() {
    const r = await api('/api/admin/live');
    if (!r.ok) throw new Error(r.body.error || ('HTTP ' + r.status));
    fill(r.body.live);
    setStat(r.body.viewers, null);
  }

  function setStat(v, c) {
    if (v != null) $('#stViewers').textContent = v;
    if (c != null) $('#stChat').textContent = c;
  }

  /* ---------- 保存 ---------- */
  async function save() {
    const btn = $('#btnSave');
    btn.disabled = true; btn.textContent = '保存中…';
    const payload = {
      on: $('#swLive').classList.contains('on'),
      title: $('#f_title').value.trim(),
      notice: $('#f_notice').value.trim(),
      cover: $('#f_cover').value.trim(),
      mode,
      url: $('#f_url').value.trim(),
      chatOn: $('#f_chatOn').checked,
      bannedWords: $('#f_banned').value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    };
    if (payload.on && payload.mode !== 'none' && !payload.url) {
      $('#msg').innerHTML = '<div class="status err">要开播得先填视频地址（或选「暂不播」）</div>';
      btn.disabled = false; btn.textContent = '💾 保存'; return;
    }
    try {
      const r = await api('/api/admin/live', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(r.body.error || ('HTTP ' + r.status));
      fill(r.body.live);
      $('#msg').innerHTML = '<div class="status ok">✅ 已保存，顾客刷新直播间就能看到</div>';
      LH.toast('已保存');
    } catch (e) {
      $('#msg').innerHTML = '<div class="status err">保存失败：' + esc(e.message) + '</div>';
    }
    btn.disabled = false; btn.textContent = '💾 保存';
  }

  /* ---------- 聊天 ---------- */
  async function pollChat() {
    try {
      const r = await fetch(base + '/api/live/chat?since=' + lastId, { cache: 'no-store' });
      const d = await r.json();
      if (!d.ok) return;
      setStat(d.viewers, null);
      const list = d.messages || [];
      if (list.length) {
        const box = $('#chatBox');
        if (box.querySelector('div[style]')) box.innerHTML = '';
        for (const m of list) {
          lastId = Math.max(lastId, m.id);
          const t = new Date(m.at).toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
          const el = document.createElement('div');
          el.className = 'm';
          el.innerHTML = '<b>' + esc(m.name) + '</b> <span style="color:var(--muted);font-size:11px">' + t + '</span><br>' + esc(m.text);
          box.appendChild(el);
        }
        box.scrollTop = box.scrollHeight;
        $('#stChat').textContent = Number($('#stChat').textContent || 0) + list.length;
      }
    } catch (e) { /* 忽略 */ }
  }

  /* ---------- 绑定 ---------- */
  function bind() {
    $('#swLive').onclick = () => {
      $('#swLive').classList.toggle('on');
      $('#stHint').textContent = $('#swLive').classList.contains('on')
        ? '顾客现在能看到「直播中」' : '关闭时顾客看到「未开播」';
    };
    $$('.mode-tabs button').forEach(b => b.onclick = () => { mode = b.dataset.mode; renderMode(); });
    $('#btnSave').onclick = save;
    $('#btnReloadChat').onclick = pollChat;
    $('#btnClearChat').onclick = async () => {
      if (!confirm('清空直播间所有聊天记录？')) return;
      await api('/api/admin/live/chat', { method: 'DELETE' });
      $('#chatBox').innerHTML = '<div style="color:var(--muted);text-align:center;padding:14px">已清空</div>';
      $('#stChat').textContent = 0;
      LH.toast('已清空');
    };
    $('#btnUnlock').onclick = () => unlock($('#tokInput').value.trim());
    $('#tokInput').onkeydown = e => { if (e.key === 'Enter') $('#btnUnlock').click(); };
  }

  async function unlock(t) {
    if (!t) { $('#lockErr').textContent = '请填 Token'; return; }
    token = t;
    try {
      await load();
      LH.LS.set(KEY, { token: t, base });
      $('#lockScreen').style.display = 'none';
      $('#whoAmI').textContent = base.replace(/^https?:\/\//, '') + '　已连接';
      pollChat();
      timer = setInterval(pollChat, 4000);
    } catch (e) {
      $('#lockErr').textContent = (e.message || '').indexOf('无权限') >= 0 ? 'Token 不对' : '连不上：' + e.message;
    }
  }

  /* ---------- 推送说明 ---------- */
  function pushHelp() {
    $('#pushHelp').innerHTML =
      '<b>方式一：用第三方直播（最省事）</b><br>' +
      '在抖音/视频号/B站开播 → 拿到分享链接 → 视频源选「第三方嵌入」贴进去。<br>' +
      '<span style="color:var(--muted)">不用买服务器，缺点是有平台水印、观众可能被引走。</span><br><br>' +
      '<b>方式二：自建（无广告、观众不出站）</b><br>' +
      '需要一台有公网带宽的服务器（≥5Mbps 上行），用 SRS 或 nginx-rtmp 收推流：<br>' +
      '<code style="display:block;background:#f6ece3;padding:8px 10px;border-radius:8px;margin:6px 0;font-size:12.5px;word-break:break-all">' +
      'ffmpeg -re -i 视频源 -c:v libx264 -preset veryfast -tune zerolatency \\<br>' +
      '  -b:v 1500k -maxrate 1500k -bufsize 3000k -g 50 \\<br>' +
      '  -c:a aac -b:a 96k -ar 44100 \\<br>' +
      '  -f flv rtmp://你的服务器/live/stream</code>' +
      '推上去后，播放地址就是 <code>https://你的域名/live/stream.m3u8</code><br>' +
      '<span style="color:var(--muted)">手机推流可以用「直播助手」类 App，或直接用 ffmpeg 命令行。</span><br><br>' +
      '<b>⚠️ 注意</b><br>' +
      '· 直播很吃带宽：1080p 约需 3~6 Mbps 上行，500 人同时看约需 750 Mbps<br>' +
      '· 人多了建议直接买云直播（阿里云/腾讯云），按量付费，几块钱一场<br>' +
      '· 带宽不够会卡顿，观众会跑光 —— 这是自建最大的坑';
  }

  async function boot() {
    base = location.origin;
    const saved = LH.LS.get(KEY, null);
    if (saved && saved.base) base = saved.base;
    bind();
    pushHelp();
    renderMode();
    try {
      const r = await fetch(base + '/api/health', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error('bad');
    } catch (e) {
      $('#lockErr').textContent = '这个地址不是直播服务器，请从服务器的 /live-admin.html 打开';
      return;
    }
    if (saved && saved.token) { unlock(saved.token); return; }
    setTimeout(() => $('#tokInput').focus(), 300);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
