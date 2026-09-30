/* 订单后台：看所有订单 + 自动刷新 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc;
  const money = LH.money;

  const KEY = 'lh_admin_token';
  let base = '';
  let token = '';
  let timer = null;
  let filter = 'all';
  let cache = [];

  const statusOf = o => {
    if (o.status === 'PAID') return { cls: 'paid', text: '已支付' };
    if (o.status === 'AMOUNT_MISMATCH') return { cls: 'bad', text: '⚠ 金额异常' };
    return { cls: 'pending', text: '待支付' };
  };

  async function api(path, opts) {
    const r = await fetch(base + path, Object.assign({}, opts, {
      headers: Object.assign({ 'Authorization': 'Bearer ' + token }, (opts && opts.headers) || {})
    }));
    const d = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, body: d };
  }

  /* ---------- 解锁 ---------- */
  function showLock(msg) {
    $('#lockScreen').style.display = 'flex';
    if (msg) $('#lockErr').textContent = msg;
  }
  function hideLock() { $('#lockScreen').style.display = 'none'; }

  async function unlock(t) {
    token = t;
    const r = await api('/api/admin/orders');
    if (!r.ok) {
      showLock(r.status === 403 ? 'Token 不对，再看看 .env 里的 ADMIN_TOKEN' : '连不上支付服务器：' + (r.body.error || r.status));
      return false;
    }
    LH.LS.set(KEY, { token: t, base: base });
    hideLock();
    $('#whoAmI').textContent = base.replace(/^https?:\/\//, '') + '　已连接';
    render(r.body.orders || []);
    loadSettings();
    startAuto();
    return true;
  }

  /* ---------- 自动刷新 ---------- */
  function startAuto() {
    clearInterval(timer);
    timer = setInterval(refresh, 5000);
  }
  async function refresh() {
    if (!token) return;
    try {
      const r = await api('/api/admin/orders');
      if (r.ok) { render(r.body.orders || []); }
      else if (r.status === 403) { clearInterval(timer); showLock('会话失效，请重新输入 Token'); }
    } catch (e) { /* 网络抖动忽略 */ }
  }

  /* ---------- 渲染 ---------- */
  function render(orders) {
    cache = orders;
    const today = new Date().toISOString().slice(0, 10);
    const isToday = o => new Date(o.createdAt || 0).toISOString().slice(0, 10) === today;

    const t = orders.filter(isToday);
    const paid = t.filter(o => o.status === 'PAID');
    const pend = orders.filter(o => o.status === 'PENDING');
    $('#stToday').textContent = t.length;
    $('#stPaid').textContent = '¥' + money(paid.reduce((a, o) => a + Number(o.total || 0), 0));
    $('#stPending').textContent = pend.length;

    let list = orders;
    if (filter === 'PAID') list = orders.filter(o => o.status === 'PAID');
    else if (filter === 'PENDING') list = orders.filter(o => o.status === 'PENDING');
    else if (filter === 'BAD') list = orders.filter(o => o.status === 'AMOUNT_MISMATCH');

    if (!list.length) {
      $('#list').innerHTML = '<div class="box" style="text-align:center;color:var(--muted);padding:28px">' +
        (orders.length ? '这个分类下没有订单' : '还没有订单<br><span style="font-size:12.5px">顾客下单后会出现在这里，不用手动转发</span>') + '</div>';
      return;
    }

    $('#list').innerHTML = list.map(o => {
      const st = statusOf(o);
      const when = o.createdAt ? new Date(o.createdAt).toLocaleString('zh-CN', { hour12: false }) : '';
      const paidAt = o.paidAt ? new Date(o.paidAt).toLocaleString('zh-CN', { hour12: false }) : '';
      return '<div class="ord ' + st.cls + '">' +
        '<div class="top">' +
          '<span class="no">' + esc(o.outTradeNo) + '</span>' +
          '<span class="badge ' + st.cls + '">' + st.text + '</span>' +
        '</div>' +
        '<div class="amt">¥' + money(o.total) + '</div>' +
        '<div class="itm" style="margin-top:4px">' +
          (o.items || []).map(i => esc(i.name) + ' ×' + i.qty + ' <span style="color:var(--muted)">¥' + money(i.sum) + '</span>').join('<br>') +
        '</div>' +
        (Number(o.fee) > 0 ? '<div class="meta">配送费 ¥' + money(o.fee) + (Number(o.dis) > 0 ? '　优惠 −¥' + money(o.dis) : '') + '</div>' : '') +
        '<div class="meta">' +
          '👤 ' + esc(o.name) + '　📞 <a href="tel:' + esc(o.phone) + '">' + esc(o.phone) + '</a><br>' +
          '📍 ' + esc(o.address) + '<br>' +
          (o.want ? '🕙 ' + esc(o.want) + '<br>' : '') +
          (o.note ? '📝 ' + esc(o.note) + '<br>' : '') +
          '🕐 下单 ' + esc(when) +
          (paidAt ? '<br>💰 收款 ' + esc(paidAt) : '') +
          (o.transactionId && !/^MOCK/.test(o.transactionId) ? '<br>🔖 交易号 ' + esc(o.transactionId) : '') +
        '</div>' +
        '<div class="ft">' +
          '<button class="mini" data-copy="' + esc(o.outTradeNo) + '">复制订单</button>' +
          (o.status === 'PENDING' ? '<button class="mini" data-pay="' + esc(o.outTradeNo) + '">收款链接</button>' : '') +
        '</div>' +
      '</div>';
    }).join('');

    $$('#list [data-copy]').forEach(b => b.onclick = async () => {
      const o = cache.find(x => x.outTradeNo === b.dataset.copy);
      if (!o) return;
      const text = [
        '【订单】' + o.outTradeNo,
        (o.items || []).map(i => i.name + '×' + i.qty).join('、'),
        '金额：¥' + money(o.total),
        '收货：' + o.name + ' ' + o.phone,
        '地址：' + o.address,
        o.want ? '送达：' + o.want : '',
        o.note ? '备注：' + o.note : '',
      ].filter(Boolean).join('\n');
      await LH.copyText(text);
      LH.toast('已复制 ✅');
    });
    $$('#list [data-pay]').forEach(b => b.onclick = () => {
      const url = base + '/pay.html?no=' + encodeURIComponent(b.dataset.pay);
      LH.copyText(url).then(() => LH.toast('收款链接已复制，可发给顾客'));
    });
  }

  /* ---------- 店铺设置 ---------- */
  let settings = null;

  function needContact() { return !settings || (!settings.phone && !settings.wechat); }

  function showWarn() {
    if (!needContact()) { $('#warnBox').innerHTML = ''; return; }
    $('#warnBox').innerHTML =
      '<div class="box" style="border-color:#f3c9c4;background:#fdeceb;margin-bottom:12px">' +
      '<b style="color:var(--brand)">⚠️ 你还没填联系方式</b>' +
      '<div style="font-size:12.5px;color:var(--muted);margin-top:5px;line-height:1.8">' +
      '顾客下单后如果找不到你，只能干着急，很可能就取消订单了。<br>' +
      '<b>请点右上角「⚙️ 店铺设置」，把电话和微信号填上。</b></div>' +
      '</div>';
  }

  function openSet() {
    const s = settings || {};
    const val = (k, d) => (s[k] === undefined || s[k] === null ? (d || '') : s[k]);
    $('#setBody').innerHTML =
      '<div class="box" style="background:#f2fbf5;border-color:#c8e6d2;font-size:12.5px;line-height:1.8;margin-bottom:12px">' +
      '<b style="color:#07c160">这两项最重要</b><br>填上之后，顾客在页面右下角、下单成功页、付款页都能一键联系到你。</div>' +

      '<div class="field"><label>店铺电话 <i>*</i></label>' +
      '<input type="tel" id="f_phone" value="' + esc(val('phone')) + '" placeholder="例如 13800138000"></div>' +

      '<div class="field"><label>微信号 <i>*</i></label>' +
      '<input type="text" id="f_wechat" value="' + esc(val('wechat')) + '" placeholder="例如 axiangluwei"></div>' +

      '<div class="field"><label>营业时间</label>' +
      '<input type="text" id="f_hours" value="' + esc(val('hours')) + '" placeholder="10:00 - 20:00"></div>' +

      '<div class="field"><label>店名</label>' +
      '<input type="text" id="f_shopName" value="' + esc(val('shopName')) + '"></div>' +

      '<div class="field"><label>公告</label>' +
      '<textarea id="f_notice" rows="2">' + esc(val('notice')) + '</textarea></div>' +

      '<div class="field"><label>配送范围说明</label>' +
      '<input type="text" id="f_deliveryArea" value="' + esc(val('deliveryArea')) + '"></div>' +

      '<button class="btn-primary btn-block" id="setSave">保存</button>' +
      '<div id="setMsg" style="margin-top:10px"></div>';
    $('#setSave').onclick = saveSet;
    $('#mask').classList.add('on');
    $('#sheetSet').classList.add('on');
  }

  function closeSet() {
    $('#mask').classList.remove('on');
    $('#sheetSet').classList.remove('on');
  }

  async function saveSet() {
    const g = id => ($('#' + id) ? $('#' + id).value.trim() : '');
    const payload = {
      phone: g('f_phone'), wechat: g('f_wechat'), hours: g('f_hours'),
      shopName: g('f_shopName'), notice: g('f_notice'), deliveryArea: g('f_deliveryArea'),
    };
    if (!payload.phone && !payload.wechat) {
      $('#setMsg').innerHTML = '<div class="status err">电话和微信至少要填一个</div>'; return;
    }
    const btn = $('#setSave');
    btn.disabled = true; btn.textContent = '保存中…';
    try {
      const r = await api('/api/admin/settings', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!r.ok) throw new Error(r.body.error || ('HTTP ' + r.status));
      settings = r.body.settings;
      $('#setMsg').innerHTML = '<div class="status ok">✅ 已保存，顾客刷新页面就能看到</div>';
      showWarn();
      setTimeout(closeSet, 900);
    } catch (e) {
      $('#setMsg').innerHTML = '<div class="status err">保存失败：' + esc(e.message) + '</div>';
    }
    btn.disabled = false; btn.textContent = '保存';
  }

  async function loadSettings() {
    try {
      const r = await api('/api/admin/settings');
      if (r.ok) { settings = r.body.settings; showWarn(); }
    } catch (e) { /* 忽略 */ }
  }

  /* ---------- 绑定 ---------- */
  function bind() {
    $('#btnSet').onclick = openSet;
    $('#setClose').onclick = closeSet;
    $('#mask').onclick = closeSet;
    $('#btnUnlock').onclick = () => {
      const t = $('#tokInput').value.trim();
      if (!t) { showLock('填一下 Token'); return; }
      unlock(t);
    };
    $('#tokInput').onkeydown = e => { if (e.key === 'Enter') $('#btnUnlock').click(); };
    $('#btnRefresh').onclick = () => { refresh(); LH.toast('已刷新'); };
    $$('.tab').forEach(t => t.onclick = () => {
      $$('.tab').forEach(x => x.classList.remove('on'));
      t.classList.add('on');
      filter = t.dataset.f;
      render(cache);
    });
  }

  async function boot() {
    // 支付服务器地址：同源优先
    base = location.origin;
    const saved = LH.LS.get(KEY, null);
    if (saved && saved.base) base = saved.base;
    bind();

    // 探测服务器
    try {
      const r = await fetch(base + '/api/health', { cache: 'no-store' });
      const d = await r.json();
      if (!r.ok || !d.ok) throw new Error('bad');
      if (String(d.mode).indexOf('MOCK') === 0) {
        $('#autoTip').innerHTML = '<span class="dot" style="background:#c98a00"></span> 演示模式（不会真实扣款）· 每 5 秒自动刷新';
      }
    } catch (e) {
      showLock('这个地址不是支付服务器，请从支付服务器的 /orders.html 打开');
      return;
    }

    if (saved && saved.token) { if (await unlock(saved.token)) return; }
    else showLock('');
    setTimeout(() => $('#tokInput').focus(), 300);
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
