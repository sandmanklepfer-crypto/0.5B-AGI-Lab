/* 顾客端逻辑 */
(function () {
  const S = {
    settings: null,
    products: { categories: [], items: [] },
    coupons: { items: [] },
    cart: LH.LS.get('lh_cart', {}),      // {id: qty}
    cat: '全部',
    couponCode: '',
    lastOrder: null,
    lastOrderSent: false
  };
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));

  /* ================= 初始化 ================= */
  async function init() {
    const [settings, products, coupons] = await Promise.all([
      LH.loadSettings(), LH.loadProducts(), LH.loadCoupons()
    ]);
    S.settings = settings;
    S.products = products || { categories: [], items: [] };
    S.coupons = coupons || { items: [] };
    // 清理已下架商品
    Object.keys(S.cart).forEach(id => {
      const p = findProduct(id);
      if (!p || p.on === false) delete S.cart[id];
    });
    renderHero();
    renderCats();
    renderGrid();
    renderBar();
    buildTimeOptions();
    bindEvents();
  }

  const findProduct = id => (S.products.items || []).find(p => p.id === id);
  const liveItems = () => (S.products.items || []).filter(p => p.on !== false);

  /* ================= 顶部 ================= */
  function renderHero() {
    const s = S.settings;
    document.title = s.shopName + ' · 在线下单';
    $('#shopName').textContent = s.shopName;
    $('#shopSlogan').textContent = s.slogan || '';
    const meta = [];
    if (s.hours) meta.push('🕙 ' + s.hours);
    if (s.phone) meta.push('📞 ' + s.phone);
    if (s.wechat) meta.push('💬 微信 ' + s.wechat);
    $('#shopMeta').innerHTML = meta.map(t => '<span>' + LH.esc(t) + '</span>').join('');
    const n = $('#shopNotice');
    if (s.notice) { n.textContent = s.notice; n.classList.remove('hidden'); } else n.classList.add('hidden');
    const f = [];
    if (s.deliveryArea) f.push('配送范围：' + s.deliveryArea);
    if (Number(s.minOrder) > 0) f.push('起送 ¥' + LH.money(s.minOrder));
    if (Number(s.freeDeliveryOver) > 0) f.push('满 ¥' + LH.money(s.freeDeliveryOver) + ' 免配送费');
    if (Number(s.deliveryFee) > 0) f.push('配送费 ¥' + LH.money(s.deliveryFee));
    $('#footer').innerHTML =
      (f.length ? '<div>' + f.map(LH.esc).join(' · ') + '</div>' : '') +
      '<div style="margin-top:6px"><a href="#" id="linkMyOrders">我的订单</a></div>' +
      '<div style="margin-top:4px">© ' + LH.esc(s.shopName) + '</div>';
    const lk = $('#linkMyOrders');
    if (lk) lk.onclick = e => { e.preventDefault(); openMy(); };
  }

  /* ================= 分类 ================= */
  function renderCats() {
    const cats = ['全部'].concat((S.products.categories || []).filter(c => liveItems().some(p => p.cat === c)));
    const extra = liveItems().map(p => p.cat).filter(c => c && cats.indexOf(c) < 0);
    const all = cats.concat(extra.filter((v, i, a) => a.indexOf(v) === i));
    $('#cats').innerHTML = all.map(c =>
      '<button class="chip ' + (c === S.cat ? 'on' : '') + '" data-cat="' + LH.esc(c) + '">' + LH.esc(c) + '</button>'
    ).join('');
    $$('#cats .chip').forEach(b => b.onclick = () => { S.cat = b.dataset.cat; renderCats(); renderGrid(); });
  }

  /* ================= 商品列表 ================= */
  function renderGrid() {
    const items = liveItems().filter(p => S.cat === '全部' || p.cat === S.cat);
    const box = $('#grid');
    if (!items.length) { box.innerHTML = ''; $('#emptyBox').classList.remove('hidden'); return; }
    $('#emptyBox').classList.add('hidden');
    box.innerHTML = items.map(p => {
      const qty = S.cart[p.id] || 0;
      const out = Number(p.stock) === 0;
      const off = (p.origPrice && Number(p.origPrice) > Number(p.price))
        ? Math.round((1 - Number(p.price) / Number(p.origPrice)) * 100) : 0;
      const thumb = p.img
        ? '<img src="' + LH.esc(p.img) + '" alt="' + LH.esc(p.name) + '" loading="lazy">'
        : '<span>🍗</span>';
      const ctl = out
        ? '<button class="btn-add" disabled>已售完</button>'
        : (qty > 0
          ? '<div class="stepper"><button data-dec="' + p.id + '">−</button><span>' + qty + '</span><button data-inc="' + p.id + '">+</button></div>'
          : '<button class="btn-add" data-inc="' + p.id + '">＋ 加入</button>');
      return '<div class="card">' +
        '<div class="thumb">' + thumb +
        (p.tag ? '<span class="tag">' + LH.esc(p.tag) + '</span>' : '') +
        (off > 0 ? '<span class="off">' + off + '% off</span>' : '') +
        '</div>' +
        '<div class="body">' +
        '<h3>' + LH.esc(p.name) + '</h3>' +
        '<div class="desc">' + LH.esc(p.desc || '') + '</div>' +
        '<div class="price-row"><span class="price"><small>¥</small>' + LH.money(p.price) + '</span>' +
        '<span class="unit">/ ' + LH.esc(p.unit || '份') + '</span>' +
        (p.origPrice && Number(p.origPrice) > Number(p.price) ? '<span class="orig">¥' + LH.money(p.origPrice) + '</span>' : '') +
        '</div>' +
        '<div class="add-line">' +
        (Number(p.stock) > 0 && Number(p.stock) <= 5 ? '<span class="stock-out">仅剩 ' + p.stock + '</span>' : '<span></span>') +
        ctl +
        '</div></div></div>';
    }).join('');
    box.querySelectorAll('[data-inc]').forEach(b => b.onclick = () => addQty(b.dataset.inc, 1));
    box.querySelectorAll('[data-dec]').forEach(b => b.onclick = () => addQty(b.dataset.dec, -1));
  }

  /* ================= 购物车 ================= */
  function addQty(id, d) {
    const p = findProduct(id); if (!p) return;
    const cur = S.cart[id] || 0;
    let next = cur + d;
    if (next <= 0) { delete S.cart[id]; }
    else if (Number(p.stock) > 0 && next > Number(p.stock)) {
      LH.toast('只剩 ' + p.stock + ' ' + (p.unit || '份') + ' 啦'); return;
    } else { S.cart[id] = next; }
    LH.LS.set('lh_cart', S.cart);
    renderGrid(); renderBar();
    if ($('#sheetCart').classList.contains('on')) renderCart();
    if ($('#sheetCheckout').classList.contains('on')) renderCheckout();
  }

  function cartLines() {
    return Object.keys(S.cart).map(id => {
      const p = findProduct(id);
      if (!p) return null;
      const q = S.cart[id];
      return { p, q, sum: Number(p.price) * q };
    }).filter(Boolean);
  }
  function subtotal() { return cartLines().reduce((a, l) => a + l.sum, 0); }
  function shipFee() {
    const s = S.settings, sub = subtotal();
    if (sub <= 0) return 0;
    if (Number(s.freeDeliveryOver) > 0 && sub >= Number(s.freeDeliveryOver)) return 0;
    return Number(s.deliveryFee) || 0;
  }
  function currentCoupon() {
    if (!S.couponCode) return null;
    return (S.coupons.items || []).find(c => String(c.code).toUpperCase() === String(S.couponCode).toUpperCase()) || null;
  }
  function money_v2() {
    const sub = subtotal();
    let fee = shipFee(), dis = 0, cp = currentCoupon(), r = null;
    if (cp) {
      r = LH.calcCoupon(cp, sub, fee);
      if (r.ok) { dis = r.discount; if (r.freeShip) fee = 0; }
    }
    const total = Math.max(0, sub + fee - dis);
    return { sub, fee, dis, total, cp, r };
  }

  function renderBar() {
    const n = Object.values(S.cart).reduce((a, b) => a + b, 0);
    const m = money_v2();
    const b = $('#cartBadge');
    b.textContent = n; b.classList.toggle('hidden', n === 0);
    $('#barTotal').textContent = LH.yuan(m.total);
    $('#btnGoCart').disabled = n === 0;
    const min = Number(S.settings.minOrder) || 0;
    if (n === 0) $('#barHint').textContent = '还没选东西';
    else if (m.sub < min) $('#barHint').textContent = '再买 ¥' + LH.money(min - m.sub) + ' 起送';
    else $('#barHint').textContent = '共 ' + n + ' 件 · 含配送费 ¥' + LH.money(m.fee) + (m.dis > 0 ? ' · 已优惠 ¥' + LH.money(m.dis) : '');
  }

  /* ================= 抽屉 ================= */
  function openSheet(id) {
    $('#mask').classList.add('on');
    $(id).classList.add('on');
    document.body.style.overflow = 'hidden';
  }
  function closeAll() {
    $('#mask').classList.remove('on');
    $$('.sheet').forEach(s => s.classList.remove('on'));
    document.body.style.overflow = '';
  }

  function renderCart() {
    const lines = cartLines();
    const box = $('#cartContent');
    if (!lines.length) {
      box.innerHTML = '<div class="empty"><span class="ic">🛒</span>购物车还是空的<br>去挑点好吃的吧</div>';
      return;
    }
    const m = money_v2();
    box.innerHTML = lines.map(l =>
      '<div class="cart-line">' +
      '<div class="nm"><b>' + LH.esc(l.p.name) + '</b><small>¥' + LH.money(l.p.price) + ' / ' + LH.esc(l.p.unit || '份') + '</small></div>' +
      '<div class="stepper"><button data-dec="' + l.p.id + '">−</button><span>' + l.q + '</span><button data-inc="' + l.p.id + '">+</button></div>' +
      '<div class="pr">¥' + LH.money(l.sum) + '</div>' +
      '</div>'
    ).join('') +
      '<div class="summary" style="margin-top:14px">' +
      line('商品小计', LH.yuan(m.sub)) +
      line('配送费', m.fee > 0 ? LH.yuan(m.fee) : '<span class="dis">免</span>') +
      (m.dis > 0 ? line('优惠券', '<span class="dis">−' + LH.yuan(m.dis) + '</span>') : '') +
      '<div class="line total"><span>合计</span><span>' + LH.yuan(m.total) + '</span></div></div>' +
      '<button class="btn-primary btn-block" id="btnToCheckout">去填写地址</button>' +
      '<div style="height:8px"></div>' +
      '<button class="btn-ghost btn-block" id="btnClearCart">清空购物车</button>';
    box.querySelectorAll('[data-inc]').forEach(b => b.onclick = () => addQty(b.dataset.inc, 1));
    box.querySelectorAll('[data-dec]').forEach(b => b.onclick = () => addQty(b.dataset.dec, -1));
    $('#btnToCheckout').onclick = () => { closeAll(); setTimeout(() => openCheckout(), 180); };
    $('#btnClearCart').onclick = () => {
      if (confirm('确定清空购物车？')) { S.cart = {}; LH.LS.set('lh_cart', S.cart); renderGrid(); renderBar(); renderCart(); }
    };
  }
  const line = (k, v) => '<div class="line"><span>' + k + '</span><span>' + v + '</span></div>';

  /* ================= 结算 ================= */
  function buildTimeOptions() {
    const s = S.settings;
    $('#timeSel').innerHTML = (s.deliveryTimeOptions || ['尽快送到'])
      .map(t => '<option>' + LH.esc(t) + '</option>').join('');
    $('#areaHint').textContent = s.deliveryArea ? '配送范围：' + s.deliveryArea : '';
    if (!s.acceptCash) {
      Array.from($('#paySel').options).forEach(o => { if (o.value === 'cash') o.remove(); });
    }
  }

  function openCheckout() {
    if (!cartLines().length) { LH.toast('先选点东西吧'); return; }
    const min = Number(S.settings.minOrder) || 0;
    if (subtotal() < min) { LH.toast('满 ¥' + LH.money(min) + ' 才起送哦'); return; }
    renderCheckout();
    openSheet('#sheetCheckout');
  }

  function renderCoupons() {
    const sub = subtotal();
    const list = (S.coupons.items || []).filter(c => c.on !== false);
    const box = $('#couponList');
    if (!list.length) { box.innerHTML = '<div class="hint" style="color:var(--muted);font-size:12.5px;margin-bottom:8px">暂时没有可领的优惠券</div>'; return; }
    box.innerHTML = list.map(c => {
      const r = LH.calcCoupon(c, sub, shipFee());
      const sel = String(S.couponCode).toUpperCase() === String(c.code).toUpperCase();
      return '<div class="coupon-card ' + (sel ? 'sel' : '') + '" data-code="' + LH.esc(c.code) + '">' +
        '<div class="amt">' + LH.couponLabel(c) + '</div>' +
        '<div class="info"><b>' + LH.esc(c.title || c.code) + '</b>' +
        '<small>' + (r.ok ? '本单可用' : r.reason) + (Number(c.min) > 0 ? ' · 满' + LH.money(c.min) + '可用' : '') + '</small></div>' +
        '<div class="pick">' + (sel ? '✓ 已选' : (r.ok ? '使用' : '不可用')) + '</div></div>';
    }).join('');
    box.querySelectorAll('.coupon-card').forEach(el => el.onclick = () => {
      const code = el.dataset.code;
      const cp = (S.coupons.items || []).find(c => c.code === code);
      const r = LH.calcCoupon(cp, subtotal(), shipFee());
      if (!r.ok) { LH.toast('这张券：' + r.reason); return; }
      S.couponCode = (String(S.couponCode).toUpperCase() === String(code).toUpperCase()) ? '' : code;
      renderCoupons(); renderSummary(); renderBar();
    });
  }

  function renderSummary() {
    const m = money_v2();
    $('#checkoutSummary').innerHTML =
      line('商品小计（' + Object.values(S.cart).reduce((a, b) => a + b, 0) + ' 件）', LH.yuan(m.sub)) +
      line('配送费', m.fee > 0 ? LH.yuan(m.fee) : '<span class="dis">免</span>') +
      (m.dis > 0 ? line('优惠券 ' + LH.esc(m.cp.code), '<span class="dis">−' + LH.yuan(m.dis) + '</span>') : '') +
      '<div class="line total"><span>应付</span><span>' + LH.yuan(m.total) + '</span></div>';
  }

  function renderCheckout() { renderCoupons(); renderSummary(); }

  /* ================= 提交订单 ================= */
  function collectOrder() {
    const f = $('#orderForm');
    const el = n => f.elements[n];          // 注意：不能用 f.name（和表单自身属性冲突）
    const m = money_v2();
    return {
      code: LH.orderCode(),
      time: new Date().toLocaleString('zh-CN'),
      name: el('name').value.trim(),
      phone: el('phone').value.trim(),
      address: el('address').value.trim(),
      want: el('time').value,
      pay: el('pay').value,
      note: el('note').value.trim(),
      items: cartLines().map(l => ({ name: l.p.name, unit: l.p.unit || '份', price: Number(l.p.price), qty: l.q, sum: l.sum })),
      sub: m.sub, fee: m.fee, dis: m.dis, total: m.total,
      coupon: m.dis > 0 ? m.cp.code : '',
      shop: S.settings.shopName
    };
  }

  function orderText(o) {
    const payMap = { wechat: '微信扫码付', alipay: '支付宝扫码付', cash: '货到付款' };
    return [
      '【新订单】' + o.shop,
      '订单号：' + o.code,
      '——————',
      o.items.map(i => i.name + ' ×' + i.qty + '（¥' + LH.money(i.price) + '/' + i.unit + '）  ¥' + LH.money(i.sum)).join('\n'),
      '——————',
      '商品小计：¥' + LH.money(o.sub),
      '配送费：¥' + LH.money(o.fee),
      o.dis > 0 ? '优惠（' + o.coupon + '）：−¥' + LH.money(o.dis) : '',
      '合计应付：¥' + LH.money(o.total),
      '——————',
      '收货人：' + o.name,
      '电话：' + o.phone,
      '地址：' + o.address,
      '送达时间：' + o.want,
      '付款方式：' + (payMap[o.pay] || o.pay),
      o.note ? '备注：' + o.note : '',
      '下单时间：' + o.time
    ].filter(Boolean).join('\n');
  }

  async function pushOrder(o) {
    const cfg = (S.settings.orderForm || {});
    const text = orderText(o);
    try {
      if (cfg.provider === 'web3forms' && cfg.accessKey) {
        const body = {
          access_key: cfg.accessKey,
          subject: '【新订单】' + o.shop + ' ' + o.code + ' ¥' + LH.money(o.total),
          from_name: o.shop + ' 在线下单',
          '订单号': o.code, '金额': '¥' + LH.money(o.total),
          '收货人': o.name, '电话': o.phone, '地址': o.address,
          '送达时间': o.want, '付款方式': o.pay, '备注': o.note,
          '明细': o.items.map(i => i.name + '×' + i.qty).join('、'),
          '完整订单': text
        };
        const r = await fetch('https://api.web3forms.com/submit', {
          method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(body)
        });
        return r.ok;
      }
      if (cfg.provider === 'formsubmit' && cfg.email) {
        const r = await fetch('https://formsubmit.co/ajax/' + encodeURIComponent(cfg.email), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            _subject: '【新订单】' + o.shop + ' ' + o.code + ' ¥' + LH.money(o.total),
            '订单号': o.code, '金额': '¥' + LH.money(o.total),
            '收货人': o.name, '电话': o.phone, '地址': o.address,
            '送达时间': o.want, '付款方式': o.pay, '备注': o.note,
            '完整订单': text
          })
        });
        return r.ok;
      }
    } catch (e) { console.warn('订单推送失败', e); }
    return false;
  }

  /* ================= 提交订单 ================= */
  async function submitOrder(e) {
    e.preventDefault();
    const f = $('#orderForm');
    const g = n => f.elements[n];
    if (!g('name').value.trim()) { LH.toast('写一下收货人怎么称呼'); g('name').focus(); return; }
    if (!/^1[3-9]\d{9}$/.test(g('phone').value.trim())) { LH.toast('手机号好像不对，再检查一下'); g('phone').focus(); return; }
    if (g('address').value.trim().length < 5) { LH.toast('地址写详细一点，师傅才好找～'); g('address').focus(); return; }
    const btn = $('#btnSubmit');
    btn.disabled = true; btn.textContent = '正在提交…';
    const o = collectOrder();
    const sent = await pushOrder(o);
    S.lastOrder = o; S.lastOrderSent = sent;
    // 本地留档
    const my = LH.LS.get('lh_orders', []);
    my.unshift(o); LH.LS.set('lh_orders', my.slice(0, 30));
    // 记录券已用
    if (o.coupon) {
      const used = LH.LS.get('lh_used_coupon', {});
      used[o.coupon] = (used[o.coupon] || 0) + 1; LH.LS.set('lh_used_coupon', used);
    }
    btn.disabled = false; btn.textContent = '提交订单';
    // 清空购物车
    S.cart = {}; S.couponCode = ''; LH.LS.set('lh_cart', S.cart);
    renderGrid(); renderBar();
    closeAll();
    setTimeout(() => openDone(o, sent), 200);
  }

  /* ================= 下单成功 & 付款 ================= */
  function openDone(o, sent) {
    const s = S.settings;
    const payMap = { wechat: '微信', alipay: '支付宝', cash: '货到付款' };
    const qrSrc = o.pay === 'alipay' ? s.payQrAlipay : s.payQrWechat;
    let payBlock = '';
    if (o.pay === 'cash') {
      payBlock = '<div class="box">💵 已选择<b>货到付款</b>，送到时付给送货师傅就行。</div>';
    } else if (qrSrc) {
      payBlock = '<div class="qr-box">' +
        '<div style="font-weight:700">请用' + payMap[o.pay] + '扫码付款 <span style="color:var(--brand)">¥' + LH.money(o.total) + '</span></div>' +
        '<img src="' + LH.esc(qrSrc) + '" alt="收款码">' +
        '<div style="font-size:12.5px;color:var(--muted)">' + LH.esc(s.payNote || '') + '</div></div>';
    } else {
      payBlock = '<div class="qr-box">' +
        '<div style="font-weight:700">应付 <span style="color:var(--brand)">¥' + LH.money(o.total) + '</span></div>' +
        '<div class="qr-ph">商家还没上传收款码，请直接联系商家付款<br>' +
        (s.phone ? '<br>📞 ' + LH.esc(s.phone) : '') +
        (s.wechat ? '<br>💬 微信：' + LH.esc(s.wechat) : '') + '</div></div>';
    }
    const notice = sent
      ? '<div class="status ok">✅ 订单已发送给商家，稍后会联系您确认。</div>'
      : '<div class="status warn">⚠️ 订单已保存在您手机上。<b>请把下面这段订单发给商家</b>（点下面的复制按钮，粘贴到微信即可），这样商家才能收到。</div>';

    $('#doneContent').innerHTML =
      '<div class="ok-hero"><div class="ic">🎉</div><h2>下单成功！</h2>' +
      '<div style="color:var(--muted);font-size:13px">把订单号报给商家，方便核对</div>' +
      '<div class="order-code">' + LH.esc(o.code) + '</div></div>' +
      notice +
      '<div class="sec-title">付款</div>' + payBlock +
      '<div class="sec-title">订单信息</div>' +
      '<div class="box" style="white-space:pre-wrap;font-size:13px;line-height:1.7">' + LH.esc(orderText(o)) + '</div>' +
      '<div style="height:14px"></div>' +
      '<button class="btn-primary btn-block" id="btnCopyOrder">📋 复制订单，发给商家</button>' +
      '<div style="height:8px"></div>' +
      '<button class="btn-ghost btn-block" id="btnDoneClose">继续逛逛</button>' +
      (s.wechat || s.phone
        ? '<div class="hint" style="text-align:center;margin-top:12px;color:var(--muted)">' +
        (s.wechat ? '微信：' + LH.esc(s.wechat) + '　' : '') + (s.phone ? '电话：' + LH.esc(s.phone) : '') + '</div>'
        : '');
    $('#btnCopyOrder').onclick = async () => { await LH.copyText(orderText(o)); LH.toast('已复制，粘贴给商家就行 ✅'); };
    $('#btnDoneClose').onclick = closeAll;
    openSheet('#sheetDone');
  }

  /* ================= 我的订单 ================= */
  function openMy() {
    const my = LH.LS.get('lh_orders', []);
    if (!my.length) {
      $('#myContent').innerHTML = '<div class="empty"><span class="ic">📦</span>还没有下过单</div>';
    } else {
      $('#myContent').innerHTML = my.map((o, i) =>
        '<div class="box" style="margin-bottom:10px">' +
        '<div style="display:flex;justify-content:space-between;margin-bottom:6px"><b>' + LH.esc(o.code) + '</b>' +
        '<span style="color:var(--brand);font-weight:700">¥' + LH.money(o.total) + '</span></div>' +
        '<div style="font-size:12.5px;color:var(--muted);line-height:1.7">' +
        o.items.map(k => LH.esc(k.name) + '×' + k.qty).join('、') + '<br>' +
        LH.esc(o.time) + ' · ' + LH.esc(o.want) + '</div>' +
        '<div style="margin-top:8px" class="row-actions">' +
        '<button class="mini" data-re="' + i + '">再复制一次</button>' +
        '<button class="mini" data-again="' + i + '">再买一单</button>' +
        '</div></div>'
      ).join('');
      $('#myContent').querySelectorAll('[data-re]').forEach(b => b.onclick = async () => {
        await LH.copyText(orderText(my[Number(b.dataset.re)])); LH.toast('已复制 ✅');
      });
      $('#myContent').querySelectorAll('[data-again]').forEach(b => b.onclick = () => {
        const o = my[Number(b.dataset.again)];
        S.cart = {};
        o.items.forEach(it => {
          const p = (S.products.items || []).find(x => x.name === it.name);
          if (p) S.cart[p.id] = it.qty;
        });
        LH.LS.set('lh_cart', S.cart); closeAll(); renderGrid(); renderBar(); LH.toast('已放回购物车');
      });
    }
    openSheet('#sheetMy');
  }

  /* ================= 事件 ================= */
  function bindEvents() {
    $('#mask').onclick = closeAll;
    $$('[data-close]').forEach(b => b.onclick = closeAll);
    $('#btnCart').onclick = () => { renderCart(); openSheet('#sheetCart'); };
    $('#btnGoCart').onclick = () => { renderCart(); openSheet('#sheetCart'); };
    $('#orderForm').onsubmit = submitOrder;
    $('#btnApplyCoupon').onclick = () => {
      const code = $('#couponInput').value.trim().toUpperCase();
      if (!code) return;
      const cp = (S.coupons.items || []).find(c => String(c.code).toUpperCase() === code);
      if (!cp) { LH.toast('没有这个优惠码'); return; }
      const usedCount = LH.LS.get('lh_used_coupon', {})[cp.code] || 0;
      if (cp.perUser && usedCount >= Number(cp.perUser)) { LH.toast('这张券你已经用过啦'); return; }
      const r = LH.calcCoupon(cp, subtotal(), shipFee());
      if (!r.ok) { LH.toast('这张券：' + r.reason); return; }
      S.couponCode = cp.code; renderCoupons(); renderSummary(); renderBar();
      LH.toast('优惠券已使用 🎉');
    };
    $('#paySel').onchange = () => {};
  }

  document.addEventListener('DOMContentLoaded', init);
})();
