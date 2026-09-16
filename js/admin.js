/* 老板端后台逻辑 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const D = { settings: null, products: { categories: [], items: [] }, coupons: { items: [] } };
  const PENDING = {};            // 待上传图片 {path: dataURL}
  let unlocked = false;

  /* ================= 启动 ================= */
  async function boot() {
    const guess = LH.guessRepo();
    const c = GH.cfg();
    if (!c.owner && guess.owner) GH.saveCfg(guess);
    fillConn();
    await loadAll();
    checkLock();
    bind();
  }

  async function loadAll(fromGitHubFirst) {
    if (fromGitHubFirst && GH.ready()) {
      try {
        setStatus('info', '正在从 GitHub 拉取最新数据…');
        const [p, cp, st] = await Promise.all([
          GH.getFile('data/products.json'), GH.getFile('data/coupons.json'), GH.getFile('data/settings.json')
        ]);
        if (p) D.products = JSON.parse(p.text);
        if (cp) D.coupons = JSON.parse(cp.text);
        if (st) D.settings = Object.assign({}, LH.DEFAULT_SETTINGS, JSON.parse(st.text));
        setStatus('ok', '已从 GitHub 拉取最新数据（' + new Date().toLocaleTimeString('zh-CN') + '）');
        afterLoad(); return;
      } catch (e) {
        setStatus('err', '拉取失败：' + e.message + '（先用本地数据）');
      }
    }
    const [st, p, cp] = await Promise.all([LH.loadSettings(), LH.loadProducts(), LH.loadCoupons()]);
    D.settings = st; D.products = p; D.coupons = cp;
    if (!fromGitHubFirst) setStatus('info', GH.ready() ? '已连接 GitHub，点"从线上重新拉取"可以同步最新数据' : '本地模式：修改会先存在这台设备上');
    afterLoad();
  }

  function afterLoad() { renderGoods(); renderCoupons(); fillShop(); fillOrders(); $('#whoAmI').textContent = GH.ready() ? (GH.cfg().owner + '/' + GH.cfg().repo) : '未连接 GitHub（本地草稿模式）'; }

  function setStatus(kind, text) {
    const el = $('#status');
    el.className = 'status ' + kind;
    el.textContent = text;
  }

  /* ================= 数字锁 ================= */
  function checkLock() {
    if (unlocked) return;
    const pin = String((D.settings && D.settings.adminPin) || '1234');
    const ok = LH.LS.get('lh_admin_ok', false);
    if (ok) { unlocked = true; hideLock(); return; }
    $('#pinInput').focus();
    $('#pinInput').oninput = e => {
      if (e.target.value.length === 4) {
        if (e.target.value === pin) {
          unlocked = true; LH.LS.set('lh_admin_ok', true); hideLock();
        } else {
          $('#pinErr').textContent = '密码不对，再试一次';
          e.target.value = '';
        }
      }
    };
  }
  function hideLock() { $('#lockScreen').style.display = 'none'; }

  /* ================= Tab ================= */
  function bind() {
    $$('.tab').forEach(t => t.onclick = () => {
      $$('.tab').forEach(x => x.classList.remove('on'));
      $$('.panel').forEach(x => x.classList.remove('on'));
      t.classList.add('on');
      $('#p-' + t.dataset.p).classList.add('on');
      try { window.scrollTo({ top: 0, behavior: 'smooth' }); } catch (e) { /* 老浏览器忽略 */ }
    });
    $('#mask').onclick = closeModal;
    $('#modalClose').onclick = closeModal;
    $('#btnPublish').onclick = publish;
    $('#btnAddGoods').onclick = () => editGoods(null);
    $('#btnSaveCats').onclick = saveCats;
    $('#btnAddCoupon').onclick = () => editCoupon(null);
    $('#btnSaveConn').onclick = saveConn;
    $('#btnClearConn').onclick = () => { if (confirm('清除本机保存的 Token？')) { GH.clearCfg(); location.reload(); } };
    $('#btnPull').onclick = () => loadAll(true);
    $('#btnSaveDraft').onclick = () => { saveDraft(); LH.toast('草稿已保存在本机'); };
    $('#btnLoadDraft').onclick = loadDraft;
    $('#btnClearDraft').onclick = () => { if (confirm('丢弃本机草稿？')) { LH.LS.del('lh_draft'); location.reload(); } };
    $('#btnExport').onclick = exportData;
    $('#btnImport').onclick = () => $('#fileImport').click();
    $('#fileImport').onchange = importData;
    $('#btnTestOrder').onclick = testOrder;
    ['s_slogan', 's_notice', 's_shopName', 's_phone', 's_wechat', 's_hours', 's_minOrder', 's_deliveryFee',
      's_freeDeliveryOver', 's_deliveryArea', 's_deliveryTimeOptions', 's_payNote',
      's_payQrWechat', 's_payQrAlipay', 's_orderEmail', 's_orderKey'].forEach(id => { const el = $('#' + id); if (el) el.onchange = () => { collectShop(); markDirty(); }; });
    $('#s_acceptCash').onchange = () => { collectShop(); markDirty(); };
    $('#s_orderProvider').onchange = () => { collectShop(); markDirty(); syncOrderFields(); };
    $('#qrWechat').onchange = e => uploadImage(e, 'img/qr-wechat.jpg', (path, url) => { D.settings.payQrWechat = path; $('#s_payQrWechat').value = path; showQrPrev('#qrWechatPrev', url); markDirty(); });
    $('#qrAlipay').onchange = e => uploadImage(e, 'img/qr-alipay.jpg', (path, url) => { D.settings.payQrAlipay = path; $('#s_payQrAlipay').value = path; showQrPrev('#qrAlipayPrev', url); markDirty(); });
  }
  function showQrPrev(sel, url) { const el = $(sel); el.src = url; el.classList.remove('hidden'); }

  let dirty = false;
  function markDirty() { dirty = true; setStatus('warn', '有改动还没发布，记得点右上角"保存并发布"⬆️'); }

  /* ================= 商品 ================= */
  function renderGoods() {
    const tb = $('#tblGoods tbody');
    const items = D.products.items || [];
    if (!items.length) { tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">还没有商品，点下面「上架一个新商品」</td></tr>'; return; }
    tb.innerHTML = items.map((p, i) => {
      const off = (p.origPrice && Number(p.origPrice) > Number(p.price));
      return '<tr>' +
        '<td>' + (p.img ? '<img class="thumb-sm" src="' + LH.esc(p.img) + '">' : '<div class="thumb-sm" style="display:flex;align-items:center;justify-content:center">🍗</div>') + '</td>' +
        '<td><b>' + LH.esc(p.name) + '</b>' + (p.tag ? '<br><small style="color:var(--gold)">' + LH.esc(p.tag) + '</small>' : '') + '</td>' +
        '<td><small>' + LH.esc(p.cat || '-') + '</small></td>' +
        '<td class="num"><b style="color:var(--brand)">' + LH.money(p.price) + '</b></td>' +
        '<td class="num">' + (off ? '<span style="text-decoration:line-through;color:#b8a396">' + LH.money(p.origPrice) + '</span>' : '-') + '</td>' +
        '<td class="num">' + (p.stock == null ? '∞' : p.stock) + '</td>' +
        '<td><span class="switch"><input type="checkbox" data-on="' + i + '" ' + (p.on === false ? '' : 'checked') + '>在售</span></td>' +
        '<td><div class="row-actions"><button class="mini" data-edit="' + i + '">编辑</button>' +
        '<button class="mini" data-up="' + i + '">↑</button><button class="mini" data-down="' + i + '">↓</button>' +
        '<button class="mini danger" data-del="' + i + '">删</button></div></td>' +
        '</tr>';
    }).join('');
    tb.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editGoods(Number(b.dataset.edit)));
    tb.querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
      if (confirm('删除「' + D.products.items[Number(b.dataset.del)].name + '」？')) { D.products.items.splice(Number(b.dataset.del), 1); renderGoods(); markDirty(); }
    });
    tb.querySelectorAll('[data-up]').forEach(b => b.onclick = () => move(Number(b.dataset.up), -1));
    tb.querySelectorAll('[data-down]').forEach(b => b.onclick = () => move(Number(b.dataset.down), 1));
    tb.querySelectorAll('[data-on]').forEach(b => b.onchange = () => { D.products.items[Number(b.dataset.on)].on = b.checked; markDirty(); });
    $('#catInput').value = (D.products.categories || []).join(',');
  }
  function move(i, d) {
    const a = D.products.items, j = i + d;
    if (j < 0 || j >= a.length) return;
    const t = a[i]; a[i] = a[j]; a[j] = t; renderGoods(); markDirty();
  }
  function saveCats() {
    D.products.categories = $('#catInput').value.split(/[,，]/).map(s => s.trim()).filter(Boolean);
    renderGoods(); markDirty(); LH.toast('分类已保存，记得发布');
  }

  function editGoods(idx) {
    const isNew = idx === null;
    const p = isNew ? { id: 'p_' + Date.now().toString(36), name: '', cat: (D.products.categories || [])[0] || '', price: 0, origPrice: 0, unit: '份', stock: 20, on: true, tag: '', desc: '', img: '' } : D.products.items[idx];
    const cats = (D.products.categories || []);
    $('#modalTitle').textContent = isNew ? '上架新商品' : '编辑：' + p.name;
    $('#modalBody').innerHTML =
      '<div class="field"><label>商品名 <i>*</i></label><input type="text" id="m_name" value="' + LH.esc(p.name) + '"></div>' +
      '<div class="row2"><div class="field"><label>分类</label><input type="text" id="m_cat" list="catlist" value="' + LH.esc(p.cat) + '">' +
      '<datalist id="catlist">' + cats.map(c => '<option value="' + LH.esc(c) + '">').join('') + '</datalist></div>' +
      '<div class="field"><label>角标（可留空）</label><input type="text" id="m_tag" value="' + LH.esc(p.tag || '') + '" placeholder="招牌/微辣"></div></div>' +
      '<div class="row2"><div class="field"><label>现价（元）<i>*</i></label><input type="number" step="0.5" id="m_price" value="' + p.price + '"></div>' +
      '<div class="field"><label>原价（划线价，0 = 不显示）</label><input type="number" step="0.5" id="m_orig" value="' + (p.origPrice || 0) + '"></div></div>' +
      '<div class="row2"><div class="field"><label>单位</label><input type="text" id="m_unit" value="' + LH.esc(p.unit || '份') + '"></div>' +
      '<div class="field"><label>库存（-1 表示不限）</label><input type="number" id="m_stock" value="' + (p.stock == null ? -1 : p.stock) + '"></div></div>' +
      '<div class="field"><label>描述</label><textarea id="m_desc">' + LH.esc(p.desc || '') + '</textarea></div>' +
      '<div class="field"><label>商品图</label><input type="file" id="m_imgfile" accept="image/*">' +
      '<div style="margin-top:8px"><img id="m_imgprev" src="' + (p.img || '') + '" class="qr-prev ' + (p.img ? '' : 'hidden') + '"></div>' +
      '<div class="hint">图片会自动压缩后上传到仓库 img/ 目录</div></div>' +
      '<div class="field"><span class="switch"><input type="checkbox" id="m_on" ' + (p.on === false ? '' : 'checked') + '>在售（不勾选顾客看不到）</span></div>' +
      '<button class="btn-primary btn-block" id="m_save">保存</button>';
    $('#m_imgfile').onchange = e => uploadImage(e, 'img/p_' + p.id + '_' + Date.now() + '.jpg', (path, url) => {
      p.img = path; const pr = $('#m_imgprev'); pr.src = url; pr.classList.remove('hidden');
    });
    $('#m_save').onclick = () => {
      const name = $('#m_name').value.trim();
      if (!name) { LH.toast('商品名不能为空'); return; }
      const price = Number($('#m_price').value);
      if (!(price >= 0)) { LH.toast('价格填一下'); return; }
      Object.assign(p, {
        name, price,
        cat: $('#m_cat').value.trim(),
        tag: $('#m_tag').value.trim(),
        origPrice: Number($('#m_orig').value) || 0,
        unit: $('#m_unit').value.trim() || '份',
        stock: Number($('#m_stock').value),
        desc: $('#m_desc').value.trim(),
        on: $('#m_on').checked
      });
      const cat = p.cat;
      if (cat && (D.products.categories || []).indexOf(cat) < 0) D.products.categories.push(cat);
      if (isNew) D.products.items.unshift(p);
      closeModal(); renderGoods(); markDirty(); LH.toast('已保存，别忘了点"保存并发布"');
    };
    openModal();
  }

  /* ================= 优惠券 ================= */
  function renderCoupons() {
    const tb = $('#tblCoupons tbody');
    const items = D.coupons.items || [];
    if (!items.length) { tb.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">还没有优惠券</td></tr>'; return; }
    tb.innerHTML = items.map((c, i) =>
      '<tr>' +
      '<td><code>' + LH.esc(c.code) + '</code></td>' +
      '<td><b>' + LH.esc(c.title || '') + '</b></td>' +
      '<td><span style="color:var(--brand);font-weight:700">' + LH.couponLabel(c) + '</span></td>' +
      '<td class="num">' + (Number(c.min) ? '满' + LH.money(c.min) : '无') + '</td>' +
      '<td><small>' + LH.esc((c.start || '不限') + ' ~ ' + (c.end || '不限')) + '</small></td>' +
      '<td class="num">' + (c.used || 0) + '/' + (c.total || '∞') + '</td>' +
      '<td><span class="switch"><input type="checkbox" data-on="' + i + '" ' + (c.on === false ? '' : 'checked') + '>启用</span></td>' +
      '<td><div class="row-actions"><button class="mini" data-edit="' + i + '">编辑</button><button class="mini danger" data-del="' + i + '">删</button></div></td>' +
      '</tr>'
    ).join('');
    tb.querySelectorAll('[data-edit]').forEach(b => b.onclick = () => editCoupon(Number(b.dataset.edit)));
    tb.querySelectorAll('[data-del]').forEach(b => b.onclick = () => {
      if (confirm('删除这张券？')) { D.coupons.items.splice(Number(b.dataset.del), 1); renderCoupons(); markDirty(); }
    });
    tb.querySelectorAll('[data-on]').forEach(b => b.onchange = () => { D.coupons.items[Number(b.dataset.on)].on = b.checked; markDirty(); });
  }

  function editCoupon(idx) {
    const isNew = idx === null;
    const c = isNew ? { code: '', title: '', type: 'amount', value: 5, min: 30, start: '', end: '', total: 100, used: 0, perUser: 1, on: true } : D.coupons.items[idx];
    $('#modalTitle').textContent = isNew ? '新建优惠券' : '编辑：' + (c.title || c.code);
    $('#modalBody').innerHTML =
      '<div class="row2"><div class="field"><label>优惠码（顾客输入用）<i>*</i></label><input type="text" id="c_code" value="' + LH.esc(c.code) + '" placeholder="XINREN5"></div>' +
      '<div class="field"><label>名称</label><input type="text" id="c_title" value="' + LH.esc(c.title || '') + '" placeholder="新人立减5元"></div></div>' +
      '<div class="row2"><div class="field"><label>类型</label><select id="c_type">' +
      ['amount|满减金额', 'percent|折扣', 'freeship|免运费'].map(s => { const [v, t] = s.split('|'); return '<option value="' + v + '"' + (c.type === v ? ' selected' : '') + '>' + t + '</option>'; }).join('') +
      '</select></div>' +
      '<div class="field"><label>数值（折扣填 88 = 88折）</label><input type="number" step="1" id="c_value" value="' + (c.value || 0) + '"></div></div>' +
      '<div class="row2"><div class="field"><label>门槛（满多少可用，0 = 无门槛）</label><input type="number" id="c_min" value="' + (c.min || 0) + '"></div>' +
      '<div class="field"><label>每人限用</label><input type="number" id="c_per" value="' + (c.perUser || 1) + '"></div></div>' +
      '<div class="row2"><div class="field"><label>开始日期（可空）</label><input type="date" id="c_start" value="' + LH.esc(c.start || '') + '"></div>' +
      '<div class="field"><label>结束日期（可空）</label><input type="date" id="c_end" value="' + LH.esc(c.end || '') + '"></div></div>' +
      '<div class="field"><label>发放总量（0 = 不限）</label><input type="number" id="c_total" value="' + (c.total || 0) + '"></div>' +
      '<div class="field"><span class="switch"><input type="checkbox" id="c_on" ' + (c.on === false ? '' : 'checked') + '>启用</span></div>' +
      '<button class="btn-primary btn-block" id="c_save">保存</button>';
    $('#c_save').onclick = () => {
      const code = $('#c_code').value.trim().toUpperCase();
      if (!code) { LH.toast('优惠码不能为空'); return; }
      const dup = (D.coupons.items || []).some((x, i) => x.code === code && i !== idx);
      if (dup) { LH.toast('这个优惠码已经有了'); return; }
      Object.assign(c, {
        code,
        title: $('#c_title').value.trim(),
        type: $('#c_type').value,
        value: Number($('#c_value').value) || 0,
        min: Number($('#c_min').value) || 0,
        start: $('#c_start').value,
        end: $('#c_end').value,
        total: Number($('#c_total').value) || 0,
        perUser: Number($('#c_per').value) || 1,
        on: $('#c_on').checked
      });
      if (isNew) D.coupons.items.unshift(c);
      closeModal(); renderCoupons(); markDirty(); LH.toast('已保存，别忘了点"保存并发布"');
    };
    openModal();
  }

  /* ================= 店铺设置 ================= */
  function fillShop() {
    const s = D.settings;
    const set = (id, v) => { const el = $('#' + id); if (el) el.value = v == null ? '' : v; };
    set('s_shopName', s.shopName); set('s_slogan', s.slogan); set('s_notice', s.notice);
    set('s_phone', s.phone); set('s_wechat', s.wechat); set('s_hours', s.hours);
    set('s_minOrder', s.minOrder); set('s_deliveryFee', s.deliveryFee); set('s_freeDeliveryOver', s.freeDeliveryOver);
    set('s_deliveryArea', s.deliveryArea);
    set('s_deliveryTimeOptions', (s.deliveryTimeOptions || []).join(', '));
    set('s_payNote', s.payNote); set('s_payQrWechat', s.payQrWechat); set('s_payQrAlipay', s.payQrAlipay);
    $('#s_acceptCash').checked = s.acceptCash !== false;
    if (s.payQrWechat) showQrPrev('#qrWechatPrev', s.payQrWechat);
    if (s.payQrAlipay) showQrPrev('#qrAlipayPrev', s.payQrAlipay);
  }
  function collectShop() {
    const s = D.settings;
    const g = id => { const el = $('#' + id); return el ? el.value.trim() : ''; };
    s.shopName = g('s_shopName') || s.shopName;
    s.slogan = g('s_slogan'); s.notice = g('s_notice');
    s.phone = g('s_phone'); s.wechat = g('s_wechat'); s.hours = g('s_hours');
    s.minOrder = Number(g('s_minOrder')) || 0;
    s.deliveryFee = Number(g('s_deliveryFee')) || 0;
    s.freeDeliveryOver = Number(g('s_freeDeliveryOver')) || 0;
    s.deliveryArea = g('s_deliveryArea');
    s.deliveryTimeOptions = g('s_deliveryTimeOptions').split(/[,，]/).map(x => x.trim()).filter(Boolean);
    s.payNote = g('s_payNote');
    s.payQrWechat = g('s_payQrWechat'); s.payQrAlipay = g('s_payQrAlipay');
    s.acceptCash = $('#s_acceptCash').checked;
    s.orderForm = {
      provider: $('#s_orderProvider').value,
      email: g('s_orderEmail'),
      accessKey: g('s_orderKey')
    };
    if (g('s_orderKey')) s.orderForm.provider = 'web3forms';
  }

  function fillOrders() {
    const f = (D.settings.orderForm || {});
    $('#s_orderProvider').value = f.provider || 'none';
    $('#s_orderEmail').value = f.email || '';
    $('#s_orderKey').value = f.accessKey || '';
    syncOrderFields();
  }
  function syncOrderFields() {
    const v = $('#s_orderProvider').value;
    $('#wrapEmail').style.display = v === 'formsubmit' ? '' : 'none';
    $('#wrapKey').style.display = v === 'web3forms' ? '' : 'none';
  }

  async function testOrder() {
    collectShop(); markDirty();
    const f = D.settings.orderForm || {};
    if (f.provider === 'none') { $('#testResult').innerHTML = '<div class="status info">当前是"不自动发送"模式，顾客点复制按钮把订单发你微信。</div>'; return; }
    $('#testResult').innerHTML = '<div class="status info">正在发送测试…</div>';
    try {
      let ok = false;
      if (f.provider === 'web3forms' && f.accessKey) {
        const r = await fetch('https://api.web3forms.com/submit', {
          method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ access_key: f.accessKey, subject: '【测试】卤味小店订单通道', from_name: '店铺后台', '测试内容': '如果你收到这封邮件，说明订单通道正常 ✅', '订单号': 'TEST-' + Date.now() })
        });
        ok = r.ok;
      } else if (f.provider === 'formsubmit' && f.email) {
        const r = await fetch('https://formsubmit.co/ajax/' + encodeURIComponent(f.email), {
          method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({ _subject: '【测试】卤味小店订单通道', '订单号': 'TEST-' + Date.now(), '测试内容': '收到这封邮件说明订单通道正常 ✅' })
        });
        ok = r.ok;
      }
      $('#testResult').innerHTML = ok
        ? '<div class="status ok">✅ 已提交成功，去邮箱（含垃圾箱）看看，第一次要先点确认链接。</div>'
        : '<div class="status err">发送失败，检查邮箱 / key 是否填对。</div>';
    } catch (e) {
      $('#testResult').innerHTML = '<div class="status err">发送失败：' + LH.esc(e.message) + '</div>';
    }
  }

  /* ================= 图片上传 ================= */
  async function uploadImage(ev, path, cb) {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    try {
      const dataUrl = await LH.compressImage(file, 900, 0.82);
      PENDING[path] = dataUrl;
      cb(path, dataUrl);
      const kb = Math.round(dataUrl.length * 0.75 / 1024);
      setStatus('warn', '图片已准备好（约 ' + kb + 'KB），点"保存并发布"就会传到线上');
      markDirty();
    } catch (e) { LH.toast('图片处理失败：' + e.message); }
  }

  /* ================= 连接设置 ================= */
  function fillConn() {
    const c = GH.cfg();
    $('#g_owner').value = c.owner; $('#g_repo').value = c.repo;
    $('#g_branch').value = c.branch || 'gh-pages'; $('#g_path').value = c.path || '';
    $('#g_token').value = c.token || '';
  }
  async function saveConn() {
    GH.saveCfg({
      owner: $('#g_owner').value.trim(),
      repo: $('#g_repo').value.trim(),
      branch: $('#g_branch').value.trim() || 'gh-pages',
      path: $('#g_path').value.trim(),
      token: $('#g_token').value.trim()
    });
    if (!GH.ready()) { setStatus('err', '信息没填全'); return; }
    setStatus('info', '正在测试连接…');
    try {
      const r = await GH.testAuth();
      setStatus('ok', '✅ 连接成功：' + r.user + ' → ' + (r.repo || '(未指定仓库)') + (r.private ? '（私有仓库）' : ''));
      afterLoad();
      loadAll(true);
    } catch (e) {
      setStatus('err', '连接失败：' + e.message + '（检查 Token 权限是否勾了 Contents: Read and write）');
    }
  }

  /* ================= 发布 ================= */
  async function publish() {
    collectShop();
    saveDraft();
    if (!GH.ready()) {
      setStatus('warn', '还没连接 GitHub，改动已存成草稿。先去"连接 GitHub"填好 Token。');
      LH.toast('已存草稿，未发布');
      return;
    }
    const btn = $('#btnPublish');
    btn.disabled = true; btn.textContent = '发布中…';
    try {
      const stamp = new Date().toLocaleString('zh-CN');
      const files = [
        ['data/products.json', JSON.stringify(D.products, null, 2)],
        ['data/coupons.json', JSON.stringify(D.coupons, null, 2)],
        ['data/settings.json', JSON.stringify(D.settings, null, 2)]
      ];
      for (const [p, c] of files) {
        setStatus('info', '正在提交 ' + p + ' …');
        await GH.putFile(p, c, '更新店铺数据 ' + stamp);
      }
      const imgPaths = Object.keys(PENDING);
      for (let i = 0; i < imgPaths.length; i++) {
        const p = imgPaths[i];
        setStatus('info', '正在上传图片 ' + (i + 1) + '/' + imgPaths.length + ' …');
        await GH.putFile(p, GH.decodeDataUrl(PENDING[p]).base64, '上传图片 ' + p, true);
        delete PENDING[p];
      }
      dirty = false;
      setStatus('ok', '🎉 发布成功！约 30 秒～1 分钟后，顾客刷新页面就能看到新价格/新商品了。');
      LH.toast('发布成功');
    } catch (e) {
      setStatus('err', '发布失败：' + e.message);
    }
    btn.disabled = false; btn.textContent = '💾 保存并发布';
  }

  /* ================= 草稿 / 备份 ================= */
  function saveDraft() { LH.LS.set('lh_draft', { settings: D.settings, products: D.products, coupons: D.coupons, at: Date.now() }); }
  function loadDraft() {
    const d = LH.LS.get('lh_draft', null);
    if (!d) { LH.toast('没有草稿'); return; }
    if (!confirm('用草稿覆盖当前内容？')) return;
    D.settings = Object.assign({}, LH.DEFAULT_SETTINGS, d.settings);
    D.products = d.products; D.coupons = d.coupons;
    afterLoad(); dirty = true; setStatus('warn', '已读取草稿（' + new Date(d.at).toLocaleString('zh-CN') + '），记得发布');
  }
  function exportData() {
    const blob = new Blob([JSON.stringify({ settings: D.settings, products: D.products, coupons: D.coupons }, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'luhuo-backup-' + new Date().toISOString().slice(0, 10) + '.json';
    a.click();
  }
  function importData(ev) {
    const f = ev.target.files[0]; if (!f) return;
    const fr = new FileReader();
    fr.onload = () => {
      try {
        const d = JSON.parse(fr.result);
        if (d.settings) D.settings = Object.assign({}, LH.DEFAULT_SETTINGS, d.settings);
        if (d.products) D.products = d.products;
        if (d.coupons) D.coupons = d.coupons;
        afterLoad(); markDirty(); LH.toast('导入成功');
      } catch (e) { LH.toast('文件格式不对'); }
    };
    fr.readAsText(f);
  }

  /* ================= 弹窗 ================= */
  function openModal() { $('#mask').classList.add('on'); $('#modal').classList.add('on'); }
  function closeModal() { $('#mask').classList.remove('on'); $('#modal').classList.remove('on'); }

  window.addEventListener('beforeunload', e => {
    if (dirty) { e.preventDefault(); e.returnValue = ''; }
  });

  document.addEventListener('DOMContentLoaded', boot);
})();
