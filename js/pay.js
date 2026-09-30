/* 支付页逻辑：读取订单 → 展示微信支付码 → 轮询支付状态 */
(function () {
  const $ = s => document.querySelector(s);
  const money = n => { n = Number(n) || 0; return (Math.round(n * 100) / 100).toFixed(2).replace(/\.00$/, ''); };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const no = new URLSearchParams(location.search).get('no') || '';
  let timer = null;

  function api(path, opts) {
    return fetch(path, opts).then(r => r.json().then(j => ({ ok: r.ok, status: r.status, body: j })));
  }

  function render(kind, html) { $('#root').innerHTML = html; }

  function notFound(msg) {
    render('err', '<div class="box" style="text-align:center;padding:26px">' +
      '<div style="font-size:40px">🤔</div><div style="margin-top:8px;color:var(--brand);font-weight:700">' + esc(msg) + '</div>' +
      '<div style="color:var(--muted);font-size:13px;margin-top:8px">请回下单页重新提交，或联系商家</div>' +
      '<div style="height:14px"></div><a class="btn-primary btn-block" href="./" style="display:block;text-align:center">回首页</a></div>');
  }

  let shop = {};   // 店铺设置（联系方式等）

  async function loadShop() {
    try {
      const r = await fetch('/data/settings.json?t=' + Date.now(), { cache: 'no-store' });
      if (r.ok) shop = await r.json();
    } catch (e) { shop = {}; }
  }

  // 页面底部固定显示联系方式：付完钱找不到人最慌
  function contactBar() {
    const p = shop.phone, w = shop.wechat;
    if (!p && !w) {
      return '<div class="pay-tip" style="margin-top:18px;font-size:11.5px;opacity:.7">' +
        '付款遇到问题？请联系商家</div>';
    }
    return '<div style="margin-top:20px;padding-top:14px;border-top:1px dashed var(--line);text-align:center">' +
      '<div style="font-size:12.5px;color:var(--muted);margin-bottom:9px">付款遇到问题？直接找商家</div>' +
      '<div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap">' +
      (p ? '<a href="tel:' + esc(p) + '" style="display:inline-block;padding:9px 18px;border-radius:22px;' +
           'background:#f2fbf5;border:1px solid #c8e6d2;color:#07c160;font-weight:700;font-size:13.5px;text-decoration:none">📞 打电话</a>' : '') +
      (w ? '<button id="btnWx" style="padding:9px 18px;border-radius:22px;cursor:pointer;' +
           'background:#f2fbf5;border:1px solid #c8e6d2;color:#07c160;font-weight:700;font-size:13.5px">💬 复制微信号</button>' : '') +
      '</div>' +
      (w ? '<div style="font-size:11.5px;color:var(--muted);margin-top:8px">微信：' + esc(w) + '</div>' : '') +
      (shop.hours ? '<div style="font-size:11.5px;color:var(--muted);margin-top:4px">营业时间 ' + esc(shop.hours) + '</div>' : '') +
      '</div>';
  }

  function bindContact() {
    const b = document.getElementById('btnWx');
    if (!b) return;
    b.onclick = async () => {
      try { await navigator.clipboard.writeText(shop.wechat); } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = shop.wechat; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } catch (x) {}
        document.body.removeChild(ta);
      }
      b.textContent = '✅ 已复制';
      setTimeout(() => { b.textContent = '💬 复制微信号'; }, 1600);
    };
  }

  async function boot() {
    if (!no) { notFound('缺少订单号'); return; }
    await loadShop();
    const r = await api('/api/orders/' + encodeURIComponent(no));
    if (!r.ok) { notFound(r.body.error || '订单不存在'); return; }
    const o = r.body.order;
    document.title = '支付 ¥' + money(o.total) + ' · ' + (o.shop || '卤味小店');
    $('#shopName').textContent = o.shop || '卤味小店';
    if (o.status === 'PAID') { showPaid(o); return; }
    showPay(o);
    startPrepay(o);
    startPolling();
  }

  function orderBox(o) {
    return '<div class="box" style="font-size:13px;line-height:1.9">' +
      '<div style="display:flex;justify-content:space-between"><span>订单号</span><b>' + esc(o.outTradeNo) + '</b></div>' +
      '<div style="display:flex;justify-content:space-between"><span>收货</span><span>' + esc(o.name) + '　' + esc(o.want || '') + '</span></div>' +
      '<div style="border-top:1px dashed var(--line);margin:8px 0"></div>' +
      (o.items || []).map(i => '<div style="display:flex;justify-content:space-between"><span>' + esc(i.name) + ' ×' + i.qty + '</span><span>¥' + money(i.sum) + '</span></div>').join('') +
      (Number(o.fee) > 0 ? '<div style="display:flex;justify-content:space-between;color:var(--muted)"><span>配送费</span><span>¥' + money(o.fee) + '</span></div>' : '') +
      (Number(o.dis) > 0 ? '<div style="display:flex;justify-content:space-between;color:var(--ok)"><span>优惠</span><span>−¥' + money(o.dis) + '</span></div>' : '') +
      '</div>';
  }

  function showPay(o) {
    render('pay',
      '<div class="card-panel" style="text-align:center">' +
        '<div style="color:var(--muted);font-size:13px">需支付</div>' +
        '<div class="pay-amount"><small>¥</small>' + money(o.total) + '</div>' +
        '<div class="pay-num">' + esc(o.outTradeNo) + '</div>' +
      '</div>' +
      '<div id="payArea"><div class="spinner"></div><div class="pay-tip">正在生成微信支付码…</div></div>' +
      '<div style="height:10px"></div>' +
      '<details class="help" style="background:#fff;border-radius:14px;padding:10px 12px;border:1px solid var(--line)">' +
        '<summary style="cursor:pointer;font-size:13px;color:var(--muted)">订单明细</summary>' + orderBox(o) +
      '</details>' +
      contactBar() +
      '<div style="height:70px"></div>' +
      '<div id="paidTip"></div>'
    );
    bindContact();
  }

  async function startPrepay(o) {
    const area = $('#payArea');
    const r = await api('/api/pay/prepay', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ outTradeNo: o.outTradeNo })
    });
    if (!r.ok) {
      area.innerHTML = '<div class="box" style="border-color:#f3c9c4;background:#fdeceb">' +
        '❌ 生成支付码失败：' + esc(r.body.error || '未知错误') +
        '<div style="color:var(--muted);font-size:12.5px;margin-top:6px">请稍后重试，或联系商家线下付款</div></div>';
      return;
    }
    if (r.body.paid) { location.reload(); return; }
    const codeUrl = r.body.codeUrl;
    const mock = r.body.mock;
    area.innerHTML =
      '<div class="qr-frame"><img id="qrImg" alt="微信扫码支付" src="/api/qr.svg?cell=8&text=' + encodeURIComponent(codeUrl) + '"></div>' +
      '<div class="pay-tip">' +
        '打开 <b style="color:#07c160">微信</b> → 扫一扫 → 扫码付款<br>' +
        '付款成功后本页会自动跳转，无需手动操作' +
      '</div>' +
      '<div class="pay-tip" style="margin-top:8px;font-size:11.5px;opacity:.75">二维码 30 分钟内有效，请勿重复支付</div>' +
      (mock ? '<div style="height:14px"></div><button class="btn-ghost btn-block" id="btnMock">🧪 演示模式：模拟支付成功</button>' +
              '<div class="pay-tip" style="font-size:11.5px;margin-top:6px">演示模式不会真实扣款，仅用于走通回调链路</div>' : '');

    if (mock) {
      $('#btnMock').onclick = async () => {
        $('#btnMock').disabled = true; $('#btnMock').textContent = '处理中…';
        await api('/api/pay/mock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outTradeNo: o.outTradeNo }) });
        poll();
      };
    }
  }

  function startPolling() { timer = setInterval(poll, 2500); }

  async function poll() {
    const r = await api('/api/pay/status?outTradeNo=' + encodeURIComponent(no));
    if (!r.ok) return;
    if (r.body.status === 'PAID') {
      clearInterval(timer);
      showPaid({ outTradeNo: no, total: r.body.total, paidAt: r.body.paidAt });
    } else if (r.body.status === 'AMOUNT_MISMATCH') {
      clearInterval(timer);
      $('#paidTip').innerHTML = '<div class="box" style="background:#fdeceb;border-color:#f3c9c4">⚠️ 金额核对异常，请联系商家</div>';
    }
  }

  function showPaid(o) {
    clearInterval(timer);
    render('done',
      '<div class="big-ok">' +
        '<div class="ic">✅</div>' +
        '<h2 style="margin:8px 0 2px">支付成功</h2>' +
        '<div style="color:var(--muted);font-size:13px">商家已收到通知，马上给你安排～</div>' +
      '</div>' +
      '<div class="card-panel" style="text-align:center">' +
        '<div class="pay-amount" style="font-size:32px"><small>¥</small>' + money(o.total || 0) + '</div>' +
        '<div class="pay-num">' + esc(o.outTradeNo) + '</div>' +
      '</div>' +
      '<div style="height:12px"></div>' +
      '<a class="btn-primary btn-block" href="./" style="display:block;text-align:center">再买一单</a>');
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
