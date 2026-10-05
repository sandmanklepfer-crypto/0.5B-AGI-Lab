/* ============================================================
   商家工作台（移动端 · 5 个 tab 全部真实功能）
   ------------------------------------------------------------
   · 首页 ：经营看板（销售额/订单/商品 + 功能菜单 + 榜单）
   · 选品 ：商品管理（搜索/分类/排序/改价/上下架/新增/删除）
   · 分析 ：经营分析（结构统计 + 图表 + 库存预警）
   · 消息 ：通知中心 + 顾客聊天 + 话术 + 店铺公告
   · 我的 ：店铺资料 + 工作台设置 + 后端状态 + 数据工具
   ------------------------------------------------------------
   后端：默认全部免 Token
     - 商品/店铺资料：直接读本站 data/*.json
     - 实时改价、改资料、订单：公共 MQTT（retain 当存储）
   可选：填了 GitHub Token 才会额外写回仓库文件
   ============================================================ */
(function () {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc;

  /* ---------------- 图标 ---------------- */
  const ICONS = {
    bag:   '<path d="M6 8h12l-1 12H7L6 8z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
    team:  '<rect x="4" y="5" width="7" height="7" rx="3.5"/><rect x="13" y="12" width="7" height="7" rx="3.5"/>',
    order: '<rect x="5" y="4" width="14" height="16" rx="3"/><path d="M8.5 9h7M8.5 12.5h7M8.5 16h4"/>',
    score: '<circle cx="12" cy="12" r="8"/><path d="M8.5 13.5c1 1.3 2.2 2 3.5 2s2.5-.7 3.5-2"/><path d="M9 9.6h.01M15 9.6h.01"/>',
    pick:  '<circle cx="11" cy="11" r="6"/><path d="m20 20-3.6-3.6"/><path d="M11 8.4l.9 1.8 2 .3-1.45 1.4.35 2-1.8-.95-1.8.95.35-2L8.1 10.5l2-.3z"/>',
    user:  '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 19c1.2-3.2 3.8-5 7-5s5.8 1.8 7 5"/>',
    coin:  '<circle cx="12" cy="12" r="8"/><path d="M9 9.5l3 3 3-3M12 12.5V16M9.5 14h5"/>',
    cert:  '<rect x="5" y="4" width="14" height="12" rx="2.5"/><path d="M8.5 8h7M8.5 11h4"/><path d="M9.5 16v3.2l2.5-1.4 2.5 1.4V16"/>',
    ban:   '<circle cx="12" cy="12" r="8"/><path d="m7 7 10 10"/>',
    home:  '<path d="M4 11 12 4l8 7"/><path d="M6.5 10v9h11v-9"/>',
    check: '<rect x="4.5" y="4.5" width="15" height="15" rx="4"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
    chart: '<rect x="4.5" y="4.5" width="15" height="15" rx="4"/><path d="m8 14 3-3 2.5 2.5L16 10"/>',
    chat:  '<path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v6A2.5 2.5 0 0 1 16.5 15H10l-4 4v-4H7.5"/>'
  };
  const svg = (n, cls) => '<svg class="ic' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" fill="none" ' +
    'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[n] || '') + '</svg>';

  /* ---------------- 默认配置 ---------------- */
  const DEFAULT_SHOP = {
    shopName: '', score: '4.5',
    banner: { on: true, text: '盛世华诞启新章 好物相伴度金秋' },
    metrics: { autoFromOrders: true, salesToday: 0, pendingOrders: 0 },
    hot: { title: '爆款榜单', tag: '热门', limit: 3 },
    stock: { title: '精选现货', tag: 'New', limit: 1 },
    service: { phone: '', wechat: '', note: '' },
    replies: ['您好，欢迎光临～', '亲，订单已收到，马上安排备货～',
              '不好意思这个今天卖完了，换一个可以吗？', '您的餐已经出发啦，预计 20 分钟到～',
              '感谢支持，麻烦给个五星好评，下次送您一份小菜～']
  };
  const MENUS = [
    { key: 'goods',     name: '商品管理',   icon: 'bag',   tab: 'pick' },
    { key: 'team',      name: '团队店铺',   icon: 'team',  href: 'tuiguang.html' },
    { key: 'order',     name: '订单管理',   icon: 'order', act: 'orders', badge: 'pending' },
    { key: 'score',     name: '商家体验分', icon: 'score', act: 'score' },
    { key: 'pick',      name: '智能选品',   icon: 'pick',  tab: 'pick' },
    { key: 'account',   name: '账户中心',   icon: 'user',  tab: 'mine' },
    { key: 'deposit',   name: '保证金账户', icon: 'coin',  act: 'soon' },
    { key: 'license',   name: '店铺资质',   icon: 'cert',  act: 'soon' },
    { key: 'violation', name: '违规管理',   icon: 'ban',   act: 'soon' }
  ];
  const TABS = [
    { key: 'home',    name: '首页', icon: 'home' },
    { key: 'pick',    name: '选品', icon: 'check' },
    { key: 'analyze', name: '分析', icon: 'chart' },
    { key: 'msg',     name: '消息', icon: 'chat' },
    { key: 'mine',    name: '我的', icon: 'user', dot: true }
  ];

  /* ---------------- 数据 ---------------- */
  const DATA = {
    products: { categories: [], items: [] },
    settings: {}, coupons: { items: [] },
    shop: mergeShop(null),
    orders: {}                       // code -> order
  };
  const MQ = { cli: null, ready: false, broker: '', got: { cfg: false, prod: false, set: false } };
  const PICK = { q: '', cat: '全部', sort: '默认' };
  const LSKEY = { cfg: 'lh_wb_shop', prod: 'lh_wb_prod', set: 'lh_wb_set' };
  let ACTIVE = 'home';

  /* ---------------- 小工具 ---------------- */
  function mergeShop(s) {
    const out = JSON.parse(JSON.stringify(DEFAULT_SHOP));
    if (!s || typeof s !== 'object') return out;
    Object.keys(out).forEach(k => {
      if (s[k] && typeof s[k] === 'object' && !Array.isArray(s[k])) Object.assign(out[k], s[k]);
      else if (s[k] !== undefined && s[k] !== null && s[k] !== '') out[k] = s[k];
    });
    if (!Array.isArray(out.replies) || !out.replies.length) out.replies = DEFAULT_SHOP.replies.slice();
    return out;
  }
  const yuan = n => '¥' + (Number(n) || 0).toFixed(2);
  const onItems = () => (DATA.products.items || []).filter(it => it && it.on !== false);
  const salesNum = it => Number(it.sales || it.sold || 0) || 0;
  function fmtW(n) {
    n = Number(n) || 0;
    if (n >= 10000) return (Math.round(n / 1000) / 10) + 'w';
    return String(n);
  }
  function thumbHTML(it) {
    if (it && it.img) return '<img src="' + esc(it.img) + '" alt="" loading="lazy">';
    return '<div class="ph">' + esc(((it && it.name) || '?').slice(0, 1)) + '</div>';
  }
  const dayStr = ts => { const d = new Date(ts); return d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const storeName = () => DATA.shop.shopName || DATA.settings.shopName || '满满小店';

  /* ---------------- 实时通道（公共 MQTT · 免 Token） ---------------- */
  function storeKey() {
    const c = GH.cfg(), g = LH.guessRepo();
    const o = c.owner || g.owner || 'anon', r = c.repo || g.repo || 'luhuo';
    return (o + '__' + r).toLowerCase().replace(/[^a-z0-9_]/g, '');
  }
  const K = storeKey();
  const TP = {
    cfg: 'zhz/luhuo/wb/' + K + '/cfg',
    prod: 'zhz/luhuo/wb/' + K + '/products',
    set: 'zhz/luhuo/wb/' + K + '/settings',
    ordBase: 'zhz/luhuo/orders/' + K + '/'
  };
  function initMq() {
    if (typeof MiniMqtt === 'undefined') return;
    try {
      MQ.cli = MiniMqtt.createClient({ clientId: 'wbshop' });
      MQ.cli.on('connect', b => {
        MQ.ready = true; MQ.broker = b;
        MQ.cli.subscribe(TP.cfg); MQ.cli.subscribe(TP.prod);
        MQ.cli.subscribe(TP.set); MQ.cli.subscribe(TP.ordBase + '#');
        renderFoot(); renderBackend();
      });
      MQ.cli.on('close', () => { MQ.ready = false; renderFoot(); renderBackend(); });
      MQ.cli.on('message', onMq);
    } catch (e) { console.warn('[工作台] MQTT 初始化失败', e); }
  }
  function onMq(topic, raw) {
    let o; try { o = JSON.parse(raw); } catch (e) { return; }
    if (!o) return;
    if (topic === TP.cfg) { DATA.shop = mergeShop(o); MQ.got.cfg = true; renderAll(); }
    else if (topic === TP.prod) {
      if (o.items) { DATA.products = { categories: o.categories || DATA.products.categories, items: o.items };
        MQ.got.prod = true; LH.LS.set(LSKEY.prod, o); renderAll(); }
    }
    else if (topic === TP.set) { Object.assign(DATA.settings, o); MQ.got.set = true;
      LH.LS.set(LSKEY.set, o); renderAll(); }
    else if (topic.indexOf(TP.ordBase) === 0) {
      const id = topic.slice(TP.ordBase.length);
      DATA.orders[id] = Object.assign({ code: id }, o);
      renderHome(); renderAnalyze(); renderMsg(); renderBackend();
    }
  }
  function pub(topic, obj) {
    if (!MQ.ready || !MQ.cli) return false;
    try { return !!MQ.cli.publish(topic, JSON.stringify(obj), true); } catch (e) { return false; }
  }

  /* ---------------- 读取 ---------------- */
  async function load() {
    if (GH.ready()) {
      try {
        const [st, p, cp, sh] = await Promise.all([
          GH.getFile('data/settings.json'), GH.getFile('data/products.json'),
          GH.getFile('data/coupons.json'), GH.getFile('data/shop.json')
        ]);
        if (st) DATA.settings = Object.assign({}, LH.DEFAULT_SETTINGS, JSON.parse(st.text));
        if (p) DATA.products = JSON.parse(p.text);
        if (cp) DATA.coupons = JSON.parse(cp.text);
        if (!MQ.got.cfg) DATA.shop = mergeShop(sh ? JSON.parse(sh.text) : LSget(LSKEY.cfg));
        DATA.source = 'github'; DATA.conn = GH.cfg().owner + '/' + GH.cfg().repo;
        applyLocalOverrides(); return;
      } catch (e) { console.warn('[工作台] GitHub 读取失败，转本站/本地', e); }
    }
    const [st, p, cp] = await Promise.all([LH.loadSettings(), LH.loadProducts(), LH.loadCoupons()]);
    DATA.settings = st; DATA.products = p; DATA.coupons = cp;
    if (!MQ.got.cfg) DATA.shop = mergeShop(LSget(LSKEY.cfg));
    DATA.source = LH.guessRepo().owner ? 'site' : 'local';
    applyLocalOverrides();
  }
  function LSget(k, d) { try { const v = localStorage.getItem(k); return v == null ? (d || null) : JSON.parse(v); } catch (e) { return d || null; } }
  function applyLocalOverrides() {
    if (!MQ.got.prod) { const o = LSget(LSKEY.prod); if (o && o.items) DATA.products = { categories: o.categories || DATA.products.categories, items: o.items }; }
    if (!MQ.got.set) { const o = LSget(LSKEY.set); if (o) Object.assign(DATA.settings, o); }
  }

  /* ---------------- 统计 ---------------- */
  function computeMetrics() {
    const codes = Object.keys(DATA.orders);
    if (codes.length && DATA.shop.metrics.autoFromOrders) {
      const today = dayStr(Date.now());
      let sales = 0, pending = 0;
      codes.forEach(c => {
        const o = DATA.orders[c];
        const st = String(o.status || 'PENDING').toUpperCase();
        if (st === 'PAID' && dayStr(o.at || Date.now()) === today) sales += Number(o.total) || 0;
        if (st === 'PENDING') pending++;
      });
      return { sales, pending, fromOrders: true };
    }
    return { sales: Number(DATA.shop.metrics.salesToday) || 0,
             pending: Number(DATA.shop.metrics.pendingOrders) || 0, fromOrders: false };
  }

  /* ---------------- 保存 ---------------- */
  function saveProducts(msg) {
    const payload = { categories: DATA.products.categories, items: DATA.products.items, _at: Date.now() };
    LH.LS.set(LSKEY.prod, payload);
    const ok = pub(TP.prod, payload);
    if (GH.ready()) GH.putFile('data/products.json',
      JSON.stringify({ categories: DATA.products.categories, items: DATA.products.items }, null, 2),
      msg || ('更新商品 ' + new Date().toLocaleString('zh-CN'))).catch(() => {});
    return ok;
  }
  function saveShopCfg() {
    DATA.shop._v = 1; DATA.shop._at = Date.now();
    LH.LS.set(LSKEY.cfg, DATA.shop);
    const ok = pub(TP.cfg, DATA.shop);
    if (GH.ready()) GH.putFile('data/shop.json', JSON.stringify(DATA.shop, null, 2), '更新工作台配置').catch(() => {});
    return ok;
  }
  function saveSettings(patch, msg) {
    Object.assign(DATA.settings, patch);
    LH.LS.set(LSKEY.set, patch);
    const ok = pub(TP.set, patch);
    if (GH.ready()) {
      GH.getFile('data/settings.json').then(f => {
        const cur = f ? JSON.parse(f.text) : {};
        return GH.putFile('data/settings.json', JSON.stringify(Object.assign(cur, patch), null, 2), msg || '更新店铺资料');
      }).catch(() => {});
    }
    return ok;
  }
  const saveTip = ok => ok ? '已实时生效（免 Token）' : '实时通道未连接，已先存本机';

  /* ================= 渲染：通用 ================= */
  function renderTabs() {
    $('#tabbar').innerHTML = TABS.map(t =>
      '<button class="tb" data-tab="' + t.key + '">' + svg(t.icon) +
      (t.dot ? '<span class="dot"></span>' : '') + '<span>' + esc(t.name) + '</span></button>').join('');
    markTab();
  }
  function markTab() { $$('#tabbar .tb').forEach(b => b.classList.toggle('on', b.dataset.tab === ACTIVE)); }

  function renderAll() {
    renderHome(); renderPick(); renderAnalyze(); renderMsg(); renderFoot(); renderBackend();
    if (ACTIVE === 'mine') renderMine();
  }

  /* ================= 渲染：首页 ================= */
  function renderHome() {
    const name = storeName();
    $('#abShop').textContent = name;
    $('#shopName').textContent = name;
    $('#shopAvatar').innerHTML = '<span>' + esc(name.slice(0, 8)) + '</span>';
    $('#shopScore').textContent = DATA.shop.score || '4.5';

    const m = computeMetrics();
    DATA._m = m;
    $('#stSales').textContent = yuan(m.sales);
    $('#stPending').textContent = m.pending;
    $('#stGoods').textContent = (DATA.products.items || []).length;

    const b = DATA.shop.banner || {};
    if (b.on !== false && b.text) { $('#banner').classList.remove('hidden'); $('#bannerText').textContent = b.text; }
    else $('#banner').classList.add('hidden');

    renderMenus(); renderHot(); renderStock(); renderTabs();
  }
  function renderMenus() {
    const m = computeMetrics();
    $('#menuGrid').innerHTML = MENUS.map(x => {
      let badge = '';
      if (x.badge === 'pending' && m.pending > 0) badge = '<span class="mi-badge">' + m.pending + '</span>';
      return '<button class="menu-item" data-menu="' + x.key + '">' +
        '<span class="mi-ic">' + svg(x.icon) + '</span>' + badge +
        '<span class="mi-tx">' + esc(x.name) + '</span></button>';
    }).join('');
  }
  function renderHot() {
    const cfg = DATA.shop.hot || {}, lim = Number(cfg.limit) || 3;
    $('#hotTitle').textContent = cfg.title || '爆款榜单';
    $('#hotTag').textContent = cfg.tag || '热门';
    const list = onItems().slice().sort((a, b) => salesNum(b) - salesNum(a) || (Number(b.stock) || 0) - (Number(a.stock) || 0)).slice(0, lim);
    $('#hotRow').innerHTML = list.length ? list.map((it, i) => {
      const sn = salesNum(it);
      const sub = sn > 0 ? ('销量' + fmtW(sn)) : ('库存' + (Number(it.stock) || 0));
      return '<div class="goods" data-id="' + esc(it.id || '') + '">' +
        '<div class="thumb"><span class="rank">TOP' + (i + 1) + '</span>' +
        (it.tag ? '<span class="ship">' + esc(it.tag) + '</span>' : '') + thumbHTML(it) + '</div>' +
        '<div class="nm">' + esc(it.name || '') + '</div>' +
        '<div class="pr">' + yuan(it.price) + '</div><div class="sl">' + esc(sub) + '</div></div>';
    }).join('') : '<div class="empty-tip">还没有上架商品，去「选品」上架吧～</div>';
  }
  function renderStock() {
    const cfg = DATA.shop.stock || {}, lim = Number(cfg.limit) || 1;
    $('#stockTitle').textContent = cfg.title || '精选现货';
    $('#stockTag').textContent = cfg.tag || 'New';
    const list = onItems().slice(0, lim);
    $('#stockRow').innerHTML = list.length ? list.map(it => {
      const views = Number(it.views || it.look || 0) || 0;
      let meta = '库存' + fmtW(Number(it.stock) || 0);
      if (salesNum(it)) meta += '　销量' + fmtW(salesNum(it));
      return '<div class="stock" data-id="' + esc(it.id || '') + '">' +
        '<div class="thumb">' + thumbHTML(it) + '</div>' +
        '<div class="info"><div class="nm">' + esc(it.name || '') + '</div>' +
        '<div class="meta">' + esc(meta) + '</div><div class="bottom">' +
        '<div class="price">供货价<b>' + yuan(it.price) + '</b></div>' +
        '<div class="views">' + (views ? ('超' + fmtW(views) + '人浏览') : '') + '</div></div></div></div>';
    }).join('') : '<div class="empty-tip">暂无可推荐的现货</div>';
  }

  /* ================= 渲染：选品 ================= */
  function pickList() {
    let arr = (DATA.products.items || []).slice();
    const q = PICK.q.trim();
    if (q) arr = arr.filter(it => (it.name + ' ' + (it.cat || '')).toLowerCase().indexOf(q.toLowerCase()) >= 0);
    if (PICK.cat && PICK.cat !== '全部') arr = arr.filter(it => (it.cat || '未分类') === PICK.cat);
    const s = PICK.sort;
    if (s === '销量') arr.sort((a, b) => salesNum(b) - salesNum(a));
    else if (s === '价格↑') arr.sort((a, b) => (Number(a.price) || 0) - (Number(b.price) || 0));
    else if (s === '价格↓') arr.sort((a, b) => (Number(b.price) || 0) - (Number(a.price) || 0));
    else if (s === '库存') arr.sort((a, b) => (Number(a.stock) || 0) - (Number(b.stock) || 0));
    return arr;
  }
  function renderPick() {
    const cats = ['全部'].concat(DATA.products.categories || []);
    $('#pkCats').innerHTML = cats.map(c =>
      '<button class="cc' + (c === PICK.cat ? ' on' : '') + '" data-cat="' + esc(c) + '">' + esc(c) + '</button>').join('');
    const sorts = ['默认', '销量', '价格↑', '价格↓', '库存'];
    $('#pkSort').innerHTML = sorts.map(s =>
      '<button class="sc' + (s === PICK.sort ? ' on' : '') + '" data-sort="' + s + '">' + s + '</button>').join('');
    const list = pickList();
    const on = list.filter(i => i.on !== false).length;
    $('#pkSum').textContent = '共 ' + list.length + ' 个（在售 ' + on + ' · 下架 ' + (list.length - on) + '）';
    $('#pkList').innerHTML = list.length ? list.map(it =>
      '<div class="pk-row' + (it.on === false ? ' off' : '') + '" data-id="' + esc(it.id || '') + '">' +
      '<div class="t">' + thumbHTML(it) + '</div>' +
      '<div class="m"><b>' + esc(it.name || '') + '</b>' +
      '<small>' + esc(it.cat || '未分类') + ' · 库存' + (Number(it.stock) || 0) +
      ' · 销量' + fmtW(salesNum(it)) + (it.tag ? ' <span class="pk-tag">' + esc(it.tag) + '</span>' : '') + '</small>' +
      '<div class="pz">' + yuan(it.price) + (Number(it.origPrice) ? '<s>' + yuan(it.origPrice) + '</s>' : '') + '</div></div>' +
      '<div class="acts"><button class="pri" data-act="edit">改价</button>' +
      '<button data-act="toggle">' + (it.on === false ? '上架' : '下架') + '</button></div></div>'
    ).join('') : '<div class="empty-tip">没有符合条件的商品，换个关键词或分类试试～</div>';
  }

  /* ================= 渲染：分析 ================= */
  const bar = (label, right, val, max, cls) => '<div class="bar ' + (cls || '') + '"><div class="bl"><span>' +
    esc(label) + '</span><b>' + esc(right) + '</b></div><div class="bt"><div class="bf" style="width:' +
    (max ? Math.max(3, Math.round(val / max * 100)) : 0) + '%"></div></div></div>';
  function renderAnalyze() {
    const items = DATA.products.items || [];
    const live = items.filter(i => i.on !== false).length;
    const off = items.length - live;
    const cats = DATA.products.categories || [];
    const avg = items.length ? items.reduce((a, b) => a + (Number(b.price) || 0), 0) / items.length : 0;
    const stock = items.reduce((a, b) => a + (Number(b.stock) || 0), 0);
    const sales = items.reduce((a, b) => a + salesNum(b), 0);
    const m = DATA._m || computeMetrics();

    $('#anStats').innerHTML = [
      ['在售商品', live, 'b'], ['已下架', off, ''], ['分类数', cats.length, ''],
      ['平均价', yuan(avg), 'o'], ['总库存', fmtW(stock), 'g'], ['总销量', fmtW(sales), 'r']
    ].map(x => '<div class="g2"><div class="n ' + x[2] + '">' + esc(x[1]) + '</div><div class="l">' + x[0] + '</div></div>').join('');

    /* 分类商品数 */
    const catCount = {};
    items.forEach(i => { const c = i.cat || '未分类'; catCount[c] = (catCount[c] || 0) + 1; });
    const cArr = Object.keys(catCount).map(k => [k, catCount[k]]).sort((a, b) => b[1] - a[1]);
    const cMax = cArr.length ? cArr[0][1] : 0;
    $('#anCats').innerHTML = cArr.length ? cArr.map(x => bar(x[0], x[1] + ' 个', x[1], cMax)).join('') : '<div class="empty-sm">还没有商品</div>';

    /* 销量 TOP5 */
    const sArr = items.slice().sort((a, b) => salesNum(b) - salesNum(a)).slice(0, 5);
    const sMax = sArr.length ? salesNum(sArr[0]) : 0;
    $('#anSales').innerHTML = (sMax ? sArr.map(x => bar(x.name, fmtW(salesNum(x)), salesNum(x), sMax, 'o')).join('')
      : '<div class="empty-sm">还没有销量数据</div>');

    /* 价格区间 */
    const buckets = [[0, 10, '10 元以下'], [10, 30, '10 ~ 30 元'], [30, 50, '30 ~ 50 元'], [50, 100, '50 ~ 100 元'], [100, Infinity, '100 元以上']];
    const pb = buckets.map(b => [b[2], items.filter(i => { const p = Number(i.price) || 0; return p >= b[0] && p < b[1]; }).length]);
    const pMax = Math.max.apply(null, pb.map(x => x[1]).concat([1]));
    $('#anPrice').innerHTML = pb.map(x => bar(x[0], x[1] + ' 个', x[1], pMax, 'g')).join('');

    /* 库存预警 */
    const low = items.filter(i => (Number(i.stock) || 0) <= 5 && i.on !== false).sort((a, b) => (Number(a.stock) || 0) - (Number(b.stock) || 0));
    $('#anStock').innerHTML = low.length ? low.map(i =>
      '<div class="bar r"><div class="bl"><span>' + esc(i.name) + '</span><b>剩 ' + (Number(i.stock) || 0) + '</b></div>' +
      '<div class="bt"><div class="bf" style="width:' + Math.max(4, Math.min(100, (Number(i.stock) || 0) / 5 * 100)) + '%"></div></div></div>').join('')
      : '<div class="empty-sm">库存都还充足 ✅</div>';

    /* 顶部订单概览 */
    $('#anRefresh').onclick = () => { renderAnalyze(); LH.toast('已刷新'); };
  }

  /* ================= 渲染：消息 ================= */
  let SEG = 'notice';
  function renderMsg() {
    /* 通知（根据数据自动生成） */
    const m = DATA._m || computeMetrics();
    const items = DATA.products.items || [];
    const low = items.filter(i => (Number(i.stock) || 0) <= 5 && i.on !== false);
    const off = items.filter(i => i.on === false);
    const noImg = items.filter(i => !i.img && i.on !== false);
    const orders = Object.keys(DATA.orders).length;
    const alerts = [];
    if (orders) alerts.push(['🧾', '待处理订单 ' + m.pending + ' 单', '有新订单进来，去「订单管理」看看', 'orders', m.pending ? 'warn' : '']);
    if (low.length) alerts.push(['⚠️', '库存不足 ' + low.length + ' 个商品', low.slice(0, 3).map(i => i.name).join('、') + ' 等，建议补货', 'pick', 'warn']);
    if (off.length) alerts.push(['📦', '已下架 ' + off.length + ' 个商品', off.slice(0, 3).map(i => i.name).join('、') + ' 等', 'pick', '']);
    if (noImg.length) alerts.push(['🖼️', noImg.length + ' 个商品还没配图', '有图点击率更高哦', 'pick', '']);
    if (!DATA.settings.phone && !DATA.settings.wechat) alerts.push(['📞', '还没填联系方式', '顾客下单后找不到你，建议去「我的」填上', 'mine', 'bad']);
    if (!alerts.length) alerts.push(['✅', '一切正常', '暂时没有需要处理的事项', '', '']);

    $('#msgNotice').innerHTML = alerts.map(a =>
      '<div class="msg-item ' + a[4] + '"' + (a[3] ? ' data-goto="' + a[3] + '"' : '') + '>' +
      '<div class="mi">' + a[0] + '</div><div class="mt"><b>' + esc(a[1]) + '</b><small>' + esc(a[2]) + '</small></div></div>').join('');

    /* 聊天 + 话术 */
    const replies = DATA.shop.replies || [];
    $('#msgChat').innerHTML =
      '<div class="msg-item" data-href="chat-admin.html"><div class="mi">💬</div><div class="mt"><b>顾客聊天</b>' +
      '<small>和顾客站内私聊（免登录，走实时通道）</small></div></div>' +
      '<div class="v-title" style="padding:14px 2px 6px"><h2 style="font-size:14.5px">常用话术</h2>' +
      '<button class="mini go" id="rpAdd">＋ 添加</button></div>' +
      (replies.length ? replies.map((r, i) =>
        '<div class="copy-chip"><span>' + esc(r) + '</span><button data-copy="' + i + '">复制</button>' +
        '<button data-delr="' + i + '" style="color:#e5484d">删</button></div>').join('')
        : '<div class="empty-sm">还没有话术，点「＋ 添加」存几句常用的</div>');

    /* 公告 */
    $('#msgBoard').innerHTML =
      '<div class="field"><label>店铺公告（顾客端首页会显示）</label>' +
      '<textarea id="bd_notice" style="min-height:110px" placeholder="例如：每天 17:00 前下单，市区当天送到。">' +
      esc(DATA.settings.notice || '') + '</textarea></div>' +
      '<button class="btn-primary btn-block" id="bd_save">保存公告（免 Token）</button>' +
      '<div class="hint" style="font-size:11.5px;color:#9aa0ab;margin-top:8px">留空表示不显示公告。</div>';

    bindMsg();
  }
  function bindMsg() {
    $('#msgNotice').onclick = e => { const c = e.target.closest('[data-goto]'); if (c) switchTab(c.dataset.goto); };
    $('#msgChat').onclick = e => {
      const h = e.target.closest('[data-href]');
      if (h && !e.target.closest('button')) { location.href = h.dataset.href; return; }
      const cp = e.target.closest('[data-copy]');
      if (cp) { LH.copyText(DATA.shop.replies[Number(cp.dataset.copy)] || '').then(() => LH.toast('已复制')); return; }
      const dl = e.target.closest('[data-delr]');
      if (dl) { DATA.shop.replies.splice(Number(dl.dataset.delr), 1); saveShopCfg(); renderMsg(); return; }
      if (e.target.closest('#rpAdd')) {
        const t = prompt('输入一句常用话术：');
        if (t && t.trim()) { DATA.shop.replies.push(t.trim()); saveShopCfg(); renderMsg(); LH.toast(saveTip(MQ.ready)); }
      }
    };
    const bs = $('#bd_save');
    if (bs) bs.onclick = () => { const v = $('#bd_notice').value; LH.LS.set('lh_wb_shop', DATA.shop);
      saveSettings({ notice: v }, '更新店铺公告'); LH.toast(saveTip(MQ.ready)); };
  }
  function switchSeg(s) {
    SEG = s;
    $$('#msgSeg .seg-b').forEach(b => b.classList.toggle('on', b.dataset.seg === s));
    $('#msgNotice').classList.toggle('hidden', s !== 'notice');
    $('#msgChat').classList.toggle('hidden', s !== 'chat');
    $('#msgBoard').classList.toggle('hidden', s !== 'board');
  }

  /* ================= 渲染：我的 ================= */
  function renderMine() {
    const s = DATA.settings, w = DATA.shop;
    const set = (id, v) => { const el = $(id); if (el && document.activeElement !== el) el.value = v == null ? '' : v; };
    const ck = (id, v) => { const el = $(id); if (el) el.checked = !!v; };
    set('#me_name', w.shopName || s.shopName); set('#me_slogan', s.slogan);
    set('#me_hours', s.hours); set('#me_phone', s.phone || (w.service || {}).phone);
    set('#me_wechat', s.wechat || (w.service || {}).wechat);
    set('#me_score', w.score); set('#me_banner', (w.banner || {}).text);
    ck('#me_bannerOn', (w.banner || {}).on !== false);
    ck('#me_auto', (w.metrics || {}).autoFromOrders !== false);
    set('#me_sales', (w.metrics || {}).salesToday); set('#me_pending', (w.metrics || {}).pendingOrders);
    renderBackend();
  }
  function renderBackend() {
    const el = $('#me_backend'); if (!el) return;
    const rows = [
      ['实时通道（MQTT）', MQ.ready ? '<b class="dot-on">已连接</b>' : '<b class="dot-wait">连接中…</b>'],
      ['通道地址', esc(MQ.broker || '—')],
      ['是否需要 Token', '<b class="dot-on">不需要</b>'],
      ['商品数据来源', DATA.source === 'github' ? 'GitHub 仓库' : (DATA.source === 'site' ? '本站 data/*.json' : '本机')],
      ['GitHub 写入', GH.ready() ? '<b class="dot-on">已配置（可选）</b>' : '<b class="dot-off">未配置（不需要）</b>'],
      ['在售 / 全部商品', onItems().length + ' / ' + (DATA.products.items || []).length],
      ['收到的订单数', Object.keys(DATA.orders).length]
    ];
    el.innerHTML = rows.map(r => '<div class="sl-row"><span>' + r[0] + '</span><span>' + r[1] + '</span></div>').join('');
  }

  /* ================= 底部状态 ================= */
  function renderFoot() {
    const parts = [];
    parts.push(MQ.ready ? '<b>实时通道已连</b>（MQTT · 免 Token）' : (typeof MiniMqtt !== 'undefined' ? '实时通道连接中…' : ''));
    if (DATA.source === 'github') parts.push('商品来自 GitHub <b>' + esc(DATA.conn) + '</b>');
    else if (DATA.source === 'site') parts.push('商品来自本站（免 Token）');
    else parts.push('商品数据：本机');
    $('#connTip').innerHTML = parts.filter(Boolean).join('　·　') +
      '　<a href="javascript:;" data-act="conn">设置 →</a>';
  }

  /* ================= 抽屉 ================= */
  function openSheet(title, html, bind) {
    $('#sheetTitle').textContent = title;
    $('#sheetBody').innerHTML = html;
    $('#mask').classList.add('on'); $('#sheet').classList.add('on');
    if (typeof bind === 'function') { try { bind(); } catch (e) { console.warn(e); } }
  }
  function closeSheet() { $('#mask').classList.remove('on'); $('#sheet').classList.remove('on'); }

  /* ---- 商品编辑 ---- */
  function productSheet(id) {
    const isNew = !id;
    const it = isNew ? { id: '', name: '', cat: (DATA.products.categories || [])[0] || '', price: 0,
      origPrice: 0, unit: '份', stock: 0, on: true, tag: '', desc: '', img: '' }
      : JSON.parse(JSON.stringify((DATA.products.items || []).find(x => String(x.id) === String(id)) || {}));
    if (!isNew && !it.id) return;
    const cats = DATA.products.categories || [];
    openSheet(isNew ? '新增商品' : '编辑商品',
      '<div class="field"><label>名称</label><input type="text" id="f_name" value="' + esc(it.name || '') + '" placeholder="例如 卤猪蹄"></div>' +
      '<div class="field"><label>分类</label><select id="f_cat">' +
      cats.map(c => '<option' + (c === it.cat ? ' selected' : '') + '>' + esc(c) + '</option>').join('') +
      '</select></div>' +
      '<div class="row2"><div class="field"><label>售价</label><input type="number" id="f_price" step="0.01" value="' + (Number(it.price) || 0) + '"></div>' +
      '<div class="field"><label>划线原价（0 不显示）</label><input type="number" id="f_orig" step="0.01" value="' + (Number(it.origPrice) || 0) + '"></div></div>' +
      '<div class="row2"><div class="field"><label>单位</label><input type="text" id="f_unit" value="' + esc(it.unit || '') + '" placeholder="份 / 只"></div>' +
      '<div class="field"><label>库存</label><input type="number" id="f_stock" value="' + (Number(it.stock) || 0) + '"></div></div>' +
      '<div class="row2"><div class="field"><label>标签（可空）</label><input type="text" id="f_tag" value="' + esc(it.tag || '') + '" placeholder="招牌 / 微辣"></div>' +
      '<div class="field"><label>图片地址（可空）</label><input type="text" id="f_img" value="' + esc(it.img || '') + '" placeholder="img/xxx.jpg"></div></div>' +
      '<div class="field"><label>描述</label><textarea id="f_desc" placeholder="一句话卖点">' + esc(it.desc || '') + '</textarea></div>' +
      '<label class="sw-row"><span>上架销售</span><input type="checkbox" class="sw" id="f_on"' + (it.on === false ? '' : ' checked') + '></label>' +
      '<div class="row-actions" style="margin-top:6px"><button class="btn-primary" id="f_save" style="flex:1">保存（免 Token）</button>' +
      (isNew ? '' : '<button class="btn-ghost" id="f_del" style="color:#e5484d">删除</button>') + '</div>',
      () => {
        $('#f_save').onclick = () => {
          const g = k => $('#' + k).value;
          const o = { id: it.id || ('p_' + Date.now().toString(36)), name: g('f_name').trim(),
            cat: g('f_cat'), price: Number(g('f_price')) || 0, origPrice: Number(g('f_orig')) || 0,
            unit: g('f_unit').trim(), stock: Number(g('f_stock')) || 0, tag: g('f_tag').trim(),
            desc: g('f_desc').trim(), img: g('f_img').trim(), on: $('#f_on').checked };
          if (!o.name) { LH.toast('名称不能为空'); return; }
          if (isNew) DATA.products.items.push(o);
          else { const i = DATA.products.items.findIndex(x => String(x.id) === String(it.id)); DATA.products.items[i] = o; }
          const ok = saveProducts((isNew ? '新增商品 ' : '改价 ') + o.name);
          closeSheet(); renderAll(); LH.toast(isNew ? ('已新增 · ' + saveTip(ok)) : ('已改价 · ' + saveTip(ok)));
        };
        if ($('#f_del')) $('#f_del').onclick = () => {
          if (!confirm('确定删除「' + it.name + '」？')) return;
          DATA.products.items = DATA.products.items.filter(x => String(x.id) !== String(it.id));
          const ok = saveProducts('删除商品 ' + it.name); closeSheet(); renderAll(); LH.toast('已删除 · ' + saveTip(ok));
        };
      });
  }

  /* ---- 订单列表 ---- */
  function orderSheet() {
    const codes = Object.keys(DATA.orders).sort((a, b) => (DATA.orders[b].at || 0) - (DATA.orders[a].at || 0));
    if (!codes.length) {
      openSheet('订单管理',
        '<div class="empty-tip" style="font-size:13px;line-height:1.9">还没有收到订单。<br>顾客在店铺首页下单后，会通过实时通道（MQTT）自动出现在这里，<b>不需要任何服务器/Token</b>。</div>' +
        '<div class="row-actions" style="margin-top:12px"><a class="btn-primary" href="orders.html" style="flex:1;text-align:center;text-decoration:none">打开高级订单后台</a></div>');
      return;
    }
    const rows = codes.map(c => {
      const o = DATA.orders[c];
      const st = String(o.status || 'PENDING').toUpperCase();
      const tag = st === 'PAID' ? '<span class="pk-tag" style="background:#e6f7ee;color:#1fae5f">已支付</span>'
        : '<span class="pk-tag" style="background:#fff4e8;color:#c98a00">待处理</span>';
      const its = (o.items || []).map(i => esc(i.name) + '×' + (i.qty || 1)).join('、');
      return '<div class="msg-item" data-oid="' + esc(c) + '"><div class="mi">🧾</div><div class="mt">' +
        '<b>' + esc(o.name || '顾客') + ' ' + tag + '</b>' +
        '<small>' + esc(its || '(无商品明细)') + '<br>' + esc(o.phone || '') + '　' + esc(o.address || '') +
        '<br>合计 <b style="color:#f5333f">' + yuan(o.total) + '</b>　' + esc(o.want || '') + '</small></div></div>';
    }).join('');
    openSheet('订单管理',
      '<div class="pk-sum" style="padding:0 0 8px">共 ' + codes.length + ' 单（待处理 ' + computeMetrics().pending + '）</div>' + rows,
      () => {
        $('#sheetBody').onclick = e => {
          const c = e.target.closest('[data-oid]'); if (!c) return;
          const o = DATA.orders[c.dataset.oid];
          const st = String(o.status || 'PENDING').toUpperCase();
          if (st !== 'PAID') { o.status = 'PAID'; pub(TP.ordBase + c.dataset.oid, o);
            renderHome(); renderAnalyze(); renderMsg(); orderSheet(); LH.toast('已标记为已支付'); }
        };
      });
  }

  /* ---- 其他抽屉 ---- */
  function scoreSheet() {
    const m = DATA._m || computeMetrics();
    openSheet('商家体验分',
      '<div style="text-align:center;padding:6px 0 2px"><div class="big-num">' + esc(DATA.shop.score || '4.5') + '</div>' +
      '<div style="font-size:12.5px;color:#8a8f99">综合分（满分 5.0）</div></div>' +
      '<div class="tip">体验分由「商品质量 · 服务态度 · 发货速度」决定。按时送达、及时回消息就能涨分。</div>' +
      '<div class="stat-list" style="margin-top:10px"><div class="sl-row"><span>在售商品</span><b>' + onItems().length + '</b></div>' +
      '<div class="sl-row"><span>收到订单</span><b>' + Object.keys(DATA.orders).length + '</b></div>' +
      '<div class="sl-row"><span>待处理</span><b>' + m.pending + '</b></div></div>' +
      '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="sc_set" style="flex:1">改分数</button>' +
      '<button class="btn-ghost" id="sc_order">看订单</button></div>',
      () => { $('#sc_set').onclick = () => { closeSheet(); switchTab('mine'); setTimeout(() => $('#me_score').focus(), 260); };
        $('#sc_order').onclick = orderSheet; });
  }
  function soonSheet(name) {
    openSheet(name,
      '<div class="tip" style="font-size:13.5px">「' + esc(name) + '」在工作台里作为入口保留，实际维护建议到电脑版后台操作。</div>' +
      '<div class="row-actions" style="margin-top:12px"><a class="btn-primary" href="admin.html" style="flex:1;text-align:center;text-decoration:none">打开电脑版后台</a></div>');
  }
  function noticeSheet() {
    const n = DATA.settings.notice || '';
    openSheet('店铺公告', n ? '<div style="font-size:14px;line-height:1.9">' + esc(n) + '</div>'
      : '<div class="tip">还没写公告，去「消息 → 公告」写一句吧。</div>',
      () => { if (!n) $('#sheetBody').onclick = () => { closeSheet(); switchTab('msg'); switchSeg('board'); }; });
  }
  function serviceSheet() {
    const sv = DATA.shop.service || {};
    const phone = sv.phone || DATA.settings.phone || '';
    const wechat = sv.wechat || DATA.settings.wechat || '';
    openSheet('联系客服',
      '<div class="kv"><div><b>客服电话</b>' + (phone ? esc(phone) : '<span style="color:#9aa0ab">未填写</span>') + '</div>' +
      '<div><b>客服微信</b>' + (wechat ? esc(wechat) : '<span style="color:#9aa0ab">未填写</span>') + '</div>' +
      '<div><b>营业时间</b>' + (DATA.settings.hours ? esc(DATA.settings.hours) : '<span style="color:#9aa0ab">未填写</span>') + '</div></div>' +
      '<div class="row-actions" style="margin-top:14px">' +
      (phone ? '<a class="btn-primary" href="tel:' + esc(phone) + '" style="flex:1;text-align:center;text-decoration:none">📞 拨打电话</a>' : '') +
      (wechat ? '<button class="btn-ghost" id="c_wx">📋 复制微信号</button>' : '') +
      '<button class="btn-ghost" id="c_set">去填写</button></div>',
      () => { if ($('#c_wx')) $('#c_wx').onclick = () => LH.copyText(wechat).then(() => LH.toast('微信号已复制'));
        $('#c_set').onclick = () => { closeSheet(); switchTab('mine'); }; });
  }
  function moreSheet() {
    const rows = [['refresh', '🔄 从线上重新拉取数据'], ['conn', '🔗 后端连接设置'],
      ['mine', '⚙️ 工作台设置'], ['gh', '🐙 GitHub（可选，不需要）'],
      ['index', '🛒 打开顾客端首页'], ['admin', '🖥️ 打开电脑版后台']];
    openSheet('更多', rows.map(r => '<button class="menu-item" style="flex-direction:row;gap:10px;width:100%;padding:12px 2px;border-bottom:1px solid #f0eef2;justify-content:flex-start" data-more-act="' + r[0] + '"><span style="font-size:15px">' + r[1] + '</span></button>').join(''),
      () => { $('#sheetBody').onclick = e => { const b = e.target.closest('[data-more-act]');
        if (b) moreAct(b.dataset.moreAct); }; });
  }
  async function moreAct(a) {
    if (a === 'refresh') { closeSheet(); await refreshData(); return; }
    if (a === 'conn') return connSheet();
    if (a === 'mine') { closeSheet(); switchTab('mine'); return; }
    if (a === 'gh') return connSheet();
    if (a === 'index') { location.href = 'index.html'; return; }
    if (a === 'admin') { location.href = 'admin.html'; return; }
  }
  async function refreshData() {
    LH.toast('正在拉取…');
    await load(); renderAll();
    LH.toast(MQ.ready ? '已同步最新数据（免 Token）' : '已重新加载本地数据');
  }
  function connSheet() {
    const c = GH.cfg();
    openSheet('后端连接设置',
      '<div class="conn-chips"><span class="chip">默认免 Token</span><span class="chip">数据全公开，无敏感信息</span></div>' +
      '<details class="help-tut" style="background:#eefbf3;border:1px solid #d6f0e0;border-radius:12px;padding:10px 12px;margin-bottom:14px">' +
      '<summary style="cursor:pointer;font-weight:700;font-size:13.5px;color:#12703c">✅ 什么都不用填，打开即用</summary>' +
      '<p style="font-size:12.5px;line-height:1.95;color:#3f6b52;margin:9px 0 2px">' +
      '商品/价格直接读本站 JSON；改价、改资料、订单都走公共 MQTT 实时通道，<b>全程不需要 Token</b>。<br>' +
      '只有想把数据也写进 GitHub 仓库文件时才需要下面的 Token（可选）。</p></details>' +
      '<details class="help-tut" style="background:#f7f8fb;border:1px solid #eceff5;border-radius:12px;padding:10px 12px;margin-bottom:14px">' +
      '<summary style="cursor:pointer;font-weight:700;font-size:13.5px">（可选）GitHub Token 怎么拿</summary>' +
      '<ol style="font-size:12.5px;line-height:1.95;color:#5a6270;margin:9px 0 6px;padding-left:20px">' +
      '<li>打开 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener" style="color:#2f7bf6">github.com/settings/personal-access-tokens/new</a></li>' +
      '<li>Repository access → 勾选店铺仓库；Permissions → Contents 选 Read and write</li>' +
      '<li>Generate token，复制 <code>github_pat_</code> 开头那串填下面</li></ol></details>' +
      '<div class="field"><label>owner</label><input type="text" id="g_owner" value="' + esc(c.owner) + '"></div>' +
      '<div class="field"><label>repo</label><input type="text" id="g_repo" value="' + esc(c.repo) + '"></div>' +
      '<div class="row2"><div class="field"><label>分支</label><input type="text" id="g_branch" value="' + esc(c.branch || 'gh-pages') + '"></div>' +
      '<div class="field"><label>子目录</label><input type="text" id="g_path" value="' + esc(c.path || '') + '"></div></div>' +
      '<div class="field"><label>Token（可留空）</label><input type="password" id="g_token" value="' + esc(c.token) + '" placeholder="留空也能用"></div>' +
      '<div class="row-actions"><button class="btn-primary" id="g_save" style="flex:1">保存并测试</button>' +
      '<button class="btn-ghost" id="g_clear">断开</button></div>' +
      '<div class="status info" id="g_msg" style="margin-top:10px">不填也能正常用。</div>',
      () => {
        $('#g_save').onclick = async () => {
          GH.saveCfg({ owner: $('#g_owner').value.trim(), repo: $('#g_repo').value.trim(),
            branch: $('#g_branch').value.trim() || 'gh-pages', path: $('#g_path').value.trim(), token: $('#g_token').value.trim() });
          const msg = $('#g_msg');
          if (!GH.ready()) { msg.className = 'status info'; msg.textContent = '没填 Token，继续用「免 Token 模式」。'; return; }
          msg.className = 'status info'; msg.textContent = '测试中…';
          try { const r = await GH.testAuth(); msg.className = 'status ok';
            msg.textContent = '✅ 连接成功：' + r.user + ' → ' + (r.repo || '(未指定仓库)'); await refreshData(); setTimeout(closeSheet, 700); }
          catch (e) { msg.className = 'status err'; msg.textContent = '连接失败：' + e.message; }
        };
        $('#g_clear').onclick = () => { GH.clearCfg(); closeSheet(); LH.toast('已断开（依旧免 Token 可用）'); load().then(renderAll); };
      });
  }

  /* ================= 我的：保存 ================= */
  function bindMine() {
    $('#me_save').onclick = () => {
      const name = $('#me_name').value.trim(), slogan = $('#me_slogan').value.trim();
      const hours = $('#me_hours').value.trim(), phone = $('#me_phone').value.trim(), wechat = $('#me_wechat').value.trim();
      DATA.shop.shopName = name; DATA.shop.service = { phone: phone, wechat: wechat, note: '' };
      const ok1 = saveSettings({ shopName: name, slogan: slogan, hours: hours, phone: phone, wechat: wechat }, '更新店铺资料');
      const ok2 = saveShopCfg();
      renderAll(); LH.toast('店铺资料已保存 · ' + saveTip(ok1 || ok2));
    };
    $('#me_saveWb').onclick = () => {
      DATA.shop.score = $('#me_score').value.trim() || '4.5';
      DATA.shop.banner.text = $('#me_banner').value.trim();
      DATA.shop.banner.on = $('#me_bannerOn').checked;
      DATA.shop.metrics.autoFromOrders = $('#me_auto').checked;
      DATA.shop.metrics.salesToday = Number($('#me_sales').value) || 0;
      DATA.shop.metrics.pendingOrders = Number($('#me_pending').value) || 0;
      const ok = saveShopCfg();
      renderAll(); LH.toast('工作台设置已保存 · ' + saveTip(ok));
    };
    $('#me_reconn').onclick = () => { try { if (MQ.cli) MQ.cli.end(); } catch (e) {} MQ.ready = false; initMq(); LH.toast('正在重连…'); };
    $('#me_ghset').onclick = connSheet;
    $('#me_clearlocal').onclick = () => {
      if (!confirm('清空本机缓存（不影响线上数据）？')) return;
      LH.LS.del(LSKEY.cfg); LH.LS.del(LSKEY.prod); LH.LS.del(LSKEY.set);
      LH.toast('已清空，刷新中…'); setTimeout(() => location.reload(), 600);
    };
    $('#me_export').onclick = () => {
      const dump = { shop: DATA.shop, products: DATA.products, settings: DATA.settings, orders: DATA.orders };
      const blob = new Blob([JSON.stringify(dump, null, 2)], { type: 'application/json' });
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = 'workbench-' + Date.now() + '.json'; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000); LH.toast('已导出');
    };
    $('#me_copyall').onclick = () => LH.copyText(JSON.stringify({ products: DATA.products, settings: DATA.settings, shop: DATA.shop }, null, 2))
      .then(() => LH.toast('已复制 JSON'));
    $('#me_import').onclick = () => $('#me_file').click();
    $('#me_file').onchange = ev => {
      const f = ev.target.files && ev.target.files[0]; if (!f) return;
      const fr = new FileReader();
      fr.onload = () => {
        try {
          const d = JSON.parse(fr.result);
          if (d.products) DATA.products = d.products;
          if (d.settings) DATA.settings = Object.assign(DATA.settings, d.settings);
          if (d.shop) DATA.shop = mergeShop(d.shop);
          saveProducts('导入商品'); saveShopCfg(); renderAll(); LH.toast('导入成功');
        } catch (e) { LH.toast('导入失败：' + e.message); }
      };
      fr.readAsText(f); ev.target.value = '';
    };
  }

  /* ================= Tab 切换 ================= */
  function switchTab(k) {
    ACTIVE = k;
    $$('.view').forEach(v => v.classList.toggle('hidden', v.id !== 'view-' + k));
    markTab();
    if (k === 'mine') renderMine();
    if (k === 'msg') switchSeg(SEG);
    window.scrollTo(0, 0);
  }

  /* ================= 事件 ================= */
  function bindGlobal() {
    $('#btnMore').onclick = moreSheet;
    $('#btnService').onclick = serviceSheet;
    $('#banner').onclick = noticeSheet;
    $('#abAdd').onclick = () => productSheet(null);
    $('#abRefresh').onclick = refreshData;

    $('#mask').onclick = closeSheet;
    $$('#sheet [data-close]').forEach(b => b.onclick = closeSheet);

    /* 底部导航 */
    $('#tabbar').onclick = e => { const b = e.target.closest('[data-tab]'); if (b) switchTab(b.dataset.tab); };

    /* 首页菜单 */
    $('#menuGrid').onclick = e => {
      const b = e.target.closest('[data-menu]'); if (!b) return;
      const m = MENUS.find(x => x.key === b.dataset.menu); if (!m) return;
      if (m.tab) return switchTab(m.tab);
      if (m.href) { location.href = m.href; return; }
      if (m.act === 'orders') return orderSheet();
      if (m.act === 'score') return scoreSheet();
      if (m.act === 'soon') return soonSheet(m.name);
    };
    $$('[data-goto]').forEach(b => b.onclick = () => switchTab(b.dataset.goto));

    /* 首页榜单 */
    $('#hotRow').onclick = e => { const c = e.target.closest('[data-id]'); if (c) productSheet(c.dataset.id); };
    $('#stockRow').onclick = e => { const c = e.target.closest('[data-id]'); if (c) productSheet(c.dataset.id); };

    /* 选品 */
    $('#pkAdd2').onclick = () => productSheet(null);
    $('#pkSearch').oninput = e => { PICK.q = e.target.value; $('#pkClear').classList.toggle('hidden', !PICK.q); renderPick(); };
    $('#pkClear').onclick = () => { PICK.q = ''; $('#pkSearch').value = ''; $('#pkClear').classList.add('hidden'); renderPick(); };
    $('#pkCats').onclick = e => { const b = e.target.closest('[data-cat]'); if (b) { PICK.cat = b.dataset.cat; renderPick(); } };
    $('#pkSort').onclick = e => { const b = e.target.closest('[data-sort]'); if (b) { PICK.sort = b.dataset.sort; renderPick(); } };
    $('#pkList').onclick = e => {
      const row = e.target.closest('[data-id]'); if (!row) return;
      const id = row.dataset.id;
      const act = e.target.closest('[data-act]');
      if (!act) return productSheet(id);
      if (act.dataset.act === 'edit') return productSheet(id);
      if (act.dataset.act === 'toggle') {
        const it = (DATA.products.items || []).find(x => String(x.id) === String(id));
        if (!it) return;
        it.on = it.on === false;
        const ok = saveProducts((it.on ? '上架 ' : '下架 ') + it.name);
        renderAll(); LH.toast((it.on ? '已上架' : '已下架') + ' · ' + saveTip(ok));
      }
    };

    /* 消息 */
    $('#msgSeg').onclick = e => { const b = e.target.closest('[data-seg]'); if (b) switchSeg(b.dataset.seg); };
    $('#msgRefresh').onclick = () => { renderMsg(); LH.toast('已刷新'); };

    /* 我的 */
    bindMine();

    $('#connTip').onclick = e => { if (e.target.closest('[data-act="conn"]')) connSheet(); };
  }

  /* ================= 启动 ================= */
  async function boot() {
    const guess = LH.guessRepo(); const c = GH.cfg();
    if (!c.owner && guess.owner) GH.saveCfg(guess);
    bindGlobal();
    initMq();
    await load();
    renderAll();
    switchTab('home');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
