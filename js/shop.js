/* ============================================================
   商家工作台（移动端店面风格）
   - 界面：复刻「满满小店」商家端首页
   - 后端：复用 js/gh.js 走 GitHub 仓库（读 data/*.json，可写 data/shop.json）
   - 不改动原有 index / admin / orders 等页面
   ============================================================ */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc;
  const yuan = n => '¥' + (Number(n) || 0).toFixed(2);   // 工作台统一两位小数，更贴近电商展示

  /* ---------------- 图标（线性 SVG） ---------------- */
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
  const svg = (n, cls) => '<svg class="ic' + (cls ? ' ' + cls : '') +
    '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
    'stroke-linecap="round" stroke-linejoin="round">' + (ICONS[n] || '') + '</svg>';

  /* ---------------- 工作台默认配置 ---------------- */
  const DEFAULT_SHOP = {
    shopName: '',                 // 留空则用 data/settings.json 的店名
    score: '4.5',
    banner: { on: true, text: '盛世华诞启新章 好物相伴度金秋' },
    metrics: { autoFromOrders: true, salesToday: 0, pendingOrders: 0 },
    hot: { title: '爆款榜单', tag: '热门', limit: 3 },
    stock: { title: '精选现货', tag: 'New', limit: 1 },
    service: { phone: '', wechat: '', note: '' }
  };

  /* ---------------- 功能菜单 ---------------- */
  const MENUS = [
    { key: 'goods',     name: '商品管理',   icon: 'bag',   href: 'admin.html' },
    { key: 'team',      name: '团队店铺',   icon: 'team',  href: 'tuiguang.html' },
    { key: 'order',     name: '订单管理',   icon: 'order', href: 'orders.html', badge: 'pending' },
    { key: 'score',     name: '商家体验分', icon: 'score', act: 'score' },
    { key: 'pick',      name: '智能选品',   icon: 'pick',  act: 'scroll', target: 'hotSec' },
    { key: 'account',   name: '账户中心',   icon: 'user',  act: 'account' },
    { key: 'deposit',   name: '保证金账户', icon: 'coin',  act: 'soon' },
    { key: 'license',   name: '店铺资质',   icon: 'cert',  act: 'soon' },
    { key: 'violation', name: '违规管理',   icon: 'ban',   act: 'soon' }
  ];

  /* ---------------- 底部导航 ---------------- */
  const TABS = [
    { key: 'home',    name: '首页', icon: 'home',  act: 'home' },
    { key: 'pick',    name: '选品', icon: 'check', act: 'scroll', target: 'hotSec' },
    { key: 'analyze', name: '分析', icon: 'chart', href: 'orders.html' },
    { key: 'msg',     name: '消息', icon: 'chat',  href: 'chat-admin.html' },
    { key: 'mine',    name: '我的', icon: 'user',  href: 'admin.html', dot: true }
  ];

  /* ---------------- 数据 ---------------- */
  const D = { settings: {}, products: { categories: [], items: [] }, coupons: { items: [] },
              shop: null, metrics: { sales: 0, pending: 0 }, source: 'local', conn: '' };

  /* ================= 工具 ================= */
  function mergeShop(s) {
    const out = JSON.parse(JSON.stringify(DEFAULT_SHOP));
    if (!s || typeof s !== 'object') return out;
    Object.keys(out).forEach(k => {
      if (s[k] && typeof s[k] === 'object' && !Array.isArray(s[k])) Object.assign(out[k], s[k]);
      else if (s[k] !== undefined && s[k] !== null && s[k] !== '') out[k] = s[k];
    });
    return out;
  }
  const onItems = () => (D.products.items || []).filter(it => it && it.on !== false);
  const salesNum = it => Number(it.sales || it.sold || 0) || 0;
  function fmtW(n) {
    n = Number(n) || 0;
    if (n >= 10000) { const v = Math.round(n / 1000) / 10; return v + 'w'; }
    return String(n);
  }
  function thumbHTML(it) {
    if (it && it.img) return '<img src="' + esc(it.img) + '" alt="" loading="lazy">';
    const ch = (it && it.name ? it.name : '?').slice(0, 1);
    return '<div class="ph">' + esc(ch) + '</div>';
  }

  /* ================= 读取数据 ================= */
  async function load() {
    if (GH.ready()) {
      try {
        const [st, p, cp, sh] = await Promise.all([
          GH.getFile('data/settings.json'),
          GH.getFile('data/products.json'),
          GH.getFile('data/coupons.json'),
          GH.getFile('data/shop.json')
        ]);
        if (st) D.settings = Object.assign({}, LH.DEFAULT_SETTINGS, JSON.parse(st.text));
        if (p) D.products = JSON.parse(p.text);
        if (cp) D.coupons = JSON.parse(cp.text);
        if (!MQ.got) D.shop = mergeShop(sh ? JSON.parse(sh.text) : null);  // MQTT 实时配置优先
        D.source = 'github';
        D.conn = GH.cfg().owner + '/' + GH.cfg().repo;
        return;
      } catch (e) {
        console.warn('[工作台] GitHub 读取失败，转本地', e);
        D.err = e.message;
      }
    }
    const [st, p, cp] = await Promise.all([LH.loadSettings(), LH.loadProducts(), LH.loadCoupons()]);
    D.settings = st; D.products = p; D.coupons = cp;
    if (!MQ.got) D.shop = mergeShop(LH.LS.get('lh_wb_shop', null));      // MQTT 实时配置优先
    D.source = LH.guessRepo().owner ? 'site' : 'local';
  }

  /* 统计：有 data/orders.json 就按真实订单算，否则用工作台里手填的数 */
  async function computeMetrics() {
    let sales = null, pending = null;
    if (GH.ready() && D.shop.metrics.autoFromOrders) {
      try {
        const f = await GH.getFile('data/orders.json');
        if (f) {
          const d = JSON.parse(f.text);
          const arr = Array.isArray(d) ? d : (d.orders || []);
          const today = new Date().toISOString().slice(0, 10);
          let s = 0, p = 0;
          arr.forEach(o => {
            const stt = String(o.status || '').toUpperCase();
            const amt = Number(o.amount != null ? o.amount : (o.total != null ? o.total : o.money)) || 0;
            const t = o.createdAt || o.created_at || o.time || o.ts || '';
            const isToday = !t || String(t).slice(0, 10) === today;
            if (stt === 'PAID' && isToday) s += amt;
            if (stt === 'PENDING' || stt === 'WAIT' || !stt) p++;
          });
          sales = s; pending = p;
        }
      } catch (e) { /* 忽略，走手填值 */ }
    }
    if (sales == null) sales = Number(D.shop.metrics.salesToday) || 0;
    if (pending == null) pending = Number(D.shop.metrics.pendingOrders) || 0;
    return { sales, pending };
  }

  /* ================= 实时通道（公共 MQTT，免注册 / 免 Token） =================
   * 和聊天页一个思路：公共 broker + retain（保留消息）当小存储。
   * 只用来存工作台自己的小配置（横幅/体验分/手填统计），不存商品和价格。
   */
  const MQ = { cli: null, ready: false, broker: '', got: false };
  function storeKey() {
    const c = GH.cfg(), g = LH.guessRepo();
    const o = c.owner || g.owner || 'anon', r = c.repo || g.repo || 'luhuo';
    return (o + '__' + r).toLowerCase().replace(/[^a-z0-9_]/g, '');
  }
  const mqTopic = () => 'zhz/luhuo/wb/' + storeKey() + '/cfg';

  function initMq() {
    if (typeof MiniMqtt === 'undefined') return;
    try {
      MQ.cli = MiniMqtt.createClient({ clientId: 'wbshop' });
      MQ.cli.on('connect', b => {
        MQ.ready = true; MQ.broker = b;
        MQ.cli.subscribe(mqTopic());
        renderFoot();
      });
      MQ.cli.on('close', () => { MQ.ready = false; renderFoot(); });
      MQ.cli.on('message', (topic, msg) => {
        if (topic !== mqTopic()) return;
        try {
          const obj = JSON.parse(msg);
          if (obj && obj._v) { MQ.got = true; D.shop = mergeShop(obj); renderAll(); }
        } catch (e) { /* 忽略脏数据 */ }
      });
    } catch (e) { console.warn('[工作台] MQTT 初始化失败', e); }
  }
  function mqPublish(cfg) {
    if (!MQ.ready || !MQ.cli) return false;
    return !!MQ.cli.publish(mqTopic(),
      JSON.stringify(Object.assign({}, cfg, { _v: 1, _at: Date.now() })), true);
  }

  /* ================= 渲染 ================= */
  function renderAll() {
    const name = D.shop.shopName || D.settings.shopName || '满满小店';
    $('#shopName').textContent = name;
    $('#shopAvatar').innerHTML = '<span>' + esc(name.slice(0, 8)) + '</span>';
    $('#shopScore').textContent = D.shop.score || '4.5';

    $('#stGoods').textContent = (D.products.items || []).length;
    $('#stSales').textContent = yuan(D.metrics.sales);
    $('#stPending').textContent = D.metrics.pending;

    /* 横幅 */
    const b = D.shop.banner || {};
    if (b.on !== false && b.text) {
      $('#banner').classList.remove('hidden');
      $('#bannerText').textContent = b.text;
    } else $('#banner').classList.add('hidden');

    renderMenus(); renderTabs(); renderHot(); renderStock(); renderFoot();
  }

  /* 底部状态：实时通道（MQTT）+ 数据来源 */
  function renderFoot() {
    const parts = [];
    if (MQ.ready) parts.push('<b>实时通道已连</b>（MQTT · 免 Token）');
    else if (typeof MiniMqtt !== 'undefined') parts.push('实时通道连接中…');
    if (D.source === 'github') parts.push('商品数据来自 GitHub <b>' + esc(D.conn) + '</b>');
    else if (D.source === 'site') parts.push('商品数据来自本站 <b>' + esc(LH.guessRepo().owner) + '</b>（免 Token）');
    else parts.push('商品数据：本机预览');
    $('#connTip').innerHTML = parts.join('　·　') +
      '　<a href="javascript:;" data-act="conn">设置 →</a>';
  }

  function renderMenus() {
    $('#menuGrid').innerHTML = MENUS.map(m => {
      let badge = '';
      if (m.badge === 'pending' && D.metrics.pending > 0) badge =
        '<span class="mi-badge">' + D.metrics.pending + '</span>';
      return '<button class="menu-item" data-menu="' + m.key + '">' +
        '<span class="mi-ic">' + svg(m.icon) + '</span>' + badge +
        '<span class="mi-tx">' + esc(m.name) + '</span></button>';
    }).join('');
  }

  function renderTabs() {
    $('#tabbar').innerHTML = TABS.map(t =>
      '<button class="tb' + (t.key === 'home' ? ' on' : '') + '" data-tab="' + t.key + '">' +
      svg(t.icon) + (t.dot ? '<span class="dot"></span>' : '') +
      '<span>' + esc(t.name) + '</span></button>').join('');
  }

  function renderHot() {
    const cfg = D.shop.hot || {};
    const lim = Number(cfg.limit) || 3;
    $('#hotTitle').textContent = cfg.title || '爆款榜单';
    $('#hotTag').textContent = cfg.tag || '热门';
    const list = onItems().slice()
      .sort((a, b) => salesNum(b) - salesNum(a) || (Number(b.stock) || 0) - (Number(a.stock) || 0))
      .slice(0, lim);
    if (!list.length) { $('#hotRow').innerHTML = '<div class="empty-tip">还没有上架商品，去「商品管理」上架吧～</div>'; return; }
    $('#hotRow').innerHTML = list.map((it, i) => {
      const sn = salesNum(it);
      const sub = sn > 0 ? ('销量' + fmtW(sn)) : ('库存' + (Number(it.stock) || 0));
      return '<div class="goods" data-id="' + esc(it.id || '') + '">' +
        '<div class="thumb"><span class="rank">TOP' + (i + 1) + '</span>' +
        (it.tag ? '<span class="ship">' + esc(it.tag) + '</span>' : '') +
        thumbHTML(it) + '</div>' +
        '<div class="nm">' + esc(it.name || '') + '</div>' +
        '<div class="pr">' + yuan(it.price) + '</div>' +
        '<div class="sl">' + esc(sub) + '</div></div>';
    }).join('');
  }

  function renderStock() {
    const cfg = D.shop.stock || {};
    const lim = Number(cfg.limit) || 1;
    $('#stockTitle').textContent = cfg.title || '精选现货';
    $('#stockTag').textContent = cfg.tag || 'New';
    const list = onItems().slice(0, lim);
    if (!list.length) { $('#stockRow').innerHTML = '<div class="empty-tip">暂无可推荐的现货</div>'; return; }
    $('#stockRow').innerHTML = list.map(it => {
      const views = Number(it.views || it.look || 0) || 0;
      let meta = '库存' + fmtW(Number(it.stock) || 0);
      if (salesNum(it)) meta += '　销量' + fmtW(salesNum(it));
      return '<div class="stock" data-id="' + esc(it.id || '') + '">' +
        '<div class="thumb">' + thumbHTML(it) + '</div>' +
        '<div class="info"><div class="nm">' + esc(it.name || '') + '</div>' +
        '<div class="meta">' + esc(meta) + '</div>' +
        '<div class="bottom"><div class="price">供货价<b>' + yuan(it.price) + '</b></div>' +
        '<div class="views">' + (views ? ('超' + fmtW(views) + '人浏览') : '') + '</div></div></div></div>';
    }).join('');
  }

  /* ================= 抽屉 ================= */
  function openSheet(title, html, bind) {
    $('#sheetTitle').textContent = title;
    $('#sheetBody').innerHTML = html;
    $('#mask').classList.add('on'); $('#sheet').classList.add('on');
    if (typeof bind === 'function') { try { bind(); } catch (e) { console.warn(e); } }
  }
  function closeSheet() { $('#mask').classList.remove('on'); $('#sheet').classList.remove('on'); }

  /* ---- 更多菜单 ---- */
  function moreSheet() {
    const rows = [
      ['refresh', '🔄 从 GitHub 重新拉取数据'],
      ['conn', '🔗 ' + (GH.ready() ? 'GitHub 连接设置（已连接）' : '连接 GitHub 后端')],
      ['setting', '⚙️ 工作台设置'],
      ['index', '🛒 打开顾客端首页'],
      ['admin', '🖥️ 打开电脑版后台'],
      ['orders', '🧾 打开订单后台']
    ];
    openSheet('更多', rows.map(r => '<button class="menu-item" style="flex-direction:row;gap:10px;width:100%;padding:12px 2px;border-bottom:1px solid #f0eef2;justify-content:flex-start" data-more-act="' + r[0] + '"><span style="font-size:15px">' + r[1] + '</span></button>').join(''), () => {
      $$('#sheetBody [data-more-act]').forEach(b => b.onclick = () => onMoreAct(b.dataset.moreAct));
    });
  }
  async function onMoreAct(a) {
    if (a === 'refresh') { closeSheet(); await refreshData(); return; }
    if (a === 'conn') return connSheet();
    if (a === 'setting') return settingSheet();
    if (a === 'index') { location.href = 'index.html'; return; }
    if (a === 'admin') { location.href = 'admin.html'; return; }
    if (a === 'orders') { location.href = 'orders.html'; return; }
  }

  async function refreshData() {
    LH.toast('正在拉取…');
    await load();
    D.metrics = await computeMetrics();
    renderAll();
    LH.toast(D.source === 'github' ? '已同步 GitHub 最新数据' : '未连接 GitHub，显示本机数据');
  }

  /* ---- 连接 GitHub ---- */
  function connSheet() {
    const c = GH.cfg();
    openSheet('GitHub 后端',
      '<div class="conn-chips"><span class="chip">读数据免 Token</span><span class="chip">MQTT 实时通道免 Token</span><span class="chip">Token 仅用于写回仓库</span></div>' +
      '<details class="help-tut" style="background:#eefbf3;border:1px solid #d6f0e0;border-radius:12px;padding:10px 12px;margin-bottom:14px">' +
      '<summary style="cursor:pointer;font-weight:700;font-size:13.5px;color:#12703c">✅ 这里其实可以完全不填 Token</summary>' +
      '<p style="font-size:12.5px;line-height:1.95;color:#3f6b52;margin:9px 0 2px">' +
      '商品、价格、店名这些都存在你 GitHub 仓库的 <code>data/*.json</code> 里，网页是<b>直接读文件</b>的，不需要任何令牌；<br>' +
      '工作台自己的设置（横幅文案、体验分等）走公共 MQTT 实时通道，同样免令牌（和聊天页同一套 broker）。<br>' +
      '只有想把配置<b>长期写进仓库文件</b>时才需要 Token，属于可选项。</p>' +
      '</details>' +
      '<details class="help-tut" open style="background:#f7f8fb;border:1px solid #eceff5;border-radius:12px;padding:10px 12px;margin-bottom:14px">' +
      '<summary style="cursor:pointer;font-weight:700;font-size:13.5px">（可选）怎么拿到 GitHub Token？（30 秒）</summary>' +
      '<ol style="font-size:12.5px;line-height:1.95;color:#5a6270;margin:9px 0 6px;padding-left:20px">' +
      '<li>打开 <a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener" style="color:#2f7bf6">github.com/settings/personal-access-tokens/new</a>（先登录你的 GitHub）</li>' +
      '<li>Token name 随便填，例如 <code>luhuo-workbench</code>；Expiration 选 90 天或自定义</li>' +
      '<li>Repository access 选 <b>Only select repositories</b> → 勾选你这个店铺仓库</li>' +
      '<li>Permissions → Repository permissions → 找到 <b>Contents</b> 选 <b>Read and write</b></li>' +
      '<li>点 <b>Generate token</b>，复制以 <code>github_pat_</code> 开头的那串字符，粘到下面的输入框</li>' +
      '</ol>' +
      '<p style="font-size:12px;color:#8a6100;background:#fdf5e3;padding:8px 10px;border-radius:8px;margin:8px 0 2px">' +
      'Token 相当于你这间仓库的钥匙，只存在你自己手机里，不会上传。别把它发/截图给别人；过期了重新建一个即可。</p>' +
      '</details>' +
      '<div class="field"><label>owner（用户名/组织）</label><input type="text" id="g_owner" value="' + esc(c.owner) + '" placeholder="例如 sandmanklepfer-crypto"></div>' +
      '<div class="field"><label>repo（仓库名）</label><input type="text" id="g_repo" value="' + esc(c.repo) + '" placeholder="例如 0.5B-AGI-Lab"></div>' +
      '<div class="field"><label>分支</label><input type="text" id="g_branch" value="' + esc(c.branch || 'gh-pages') + '"></div>' +
      '<div class="field"><label>子目录（可留空）</label><input type="text" id="g_path" value="' + esc(c.path || '') + '"></div>' +
      '<div class="field"><label>Token（Contents: Read and write）</label><input type="password" id="g_token" value="' + esc(c.token) + '" placeholder="github_pat_..."></div>' +
      '<div class="row-actions"><button class="btn-primary" id="g_save" style="flex:1">保存并测试</button>' +
      '<button class="btn-ghost" id="g_clear">断开</button></div>' +
      '<div class="status info" id="g_msg" style="margin-top:10px">Token 只存你这台手机，不会上传。</div>',
      () => {
        $('#g_save').onclick = async () => {
          GH.saveCfg({
            owner: $('#g_owner').value.trim(), repo: $('#g_repo').value.trim(),
            branch: $('#g_branch').value.trim() || 'gh-pages',
            path: $('#g_path').value.trim(), token: $('#g_token').value.trim()
          });
          const msg = $('#g_msg');
          if (!GH.ready()) { msg.className = 'status err'; msg.textContent = '信息没填全'; return; }
          msg.className = 'status info'; msg.textContent = '测试连接中…';
          try {
            const r = await GH.testAuth();
            msg.className = 'status ok';
            msg.textContent = '✅ 连接成功：' + r.user + ' → ' + (r.repo || '(未指定仓库)');
            await refreshData();
            setTimeout(closeSheet, 700);
          } catch (e) {
            msg.className = 'status err';
            msg.textContent = '连接失败：' + e.message + '（确认 Token 权限勾了 Contents: Read and write）';
          }
        };
        $('#g_clear').onclick = () => { GH.clearCfg(); closeSheet(); LH.toast('已断开，转为本机模式'); load().then(async () => { D.metrics = await computeMetrics(); renderAll(); }); };
      });
  }

  /* ---- 工作台设置（写回 data/shop.json） ---- */
  function settingSheet() {
    const s = D.shop;
    openSheet('工作台设置',
      '<div class="field"><label>店铺名（留空用店铺数据里的店名）</label><input type="text" id="s_name" value="' + esc(s.shopName || '') + '" placeholder="' + esc(D.settings.shopName || '满满小店') + '"></div>' +
      '<div class="field"><label>商家体验分</label><input type="text" id="s_score" value="' + esc(s.score || '4.5') + '"></div>' +
      '<div class="field"><label>活动横幅文案</label><input type="text" id="s_banner" value="' + esc(s.banner.text || '') + '"></div>' +
      '<label class="opt" style="display:flex;gap:8px;align-items:center;font-size:13.5px;margin:2px 0 12px"><input type="checkbox" id="s_bannerOn" ' + (s.banner.on !== false ? 'checked' : '') + '> 显示活动横幅</label>' +
      '<label class="opt" style="display:flex;gap:8px;align-items:center;font-size:13.5px;margin:2px 0 12px"><input type="checkbox" id="s_auto" ' + (s.metrics.autoFromOrders ? 'checked' : '') + '> 有 data/orders.json 时按真实订单统计</label>' +
      '<div class="field"><label>今日销售额（手填，未接订单时用）</label><input type="number" id="s_sales" step="0.01" value="' + (Number(s.metrics.salesToday) || 0) + '"></div>' +
      '<div class="field"><label>待处理订单（手填，未接订单时用）</label><input type="number" id="s_pending" value="' + (Number(s.metrics.pendingOrders) || 0) + '"></div>' +
      '<div class="field"><label>客服电话</label><input type="text" id="s_phone" value="' + esc(s.service.phone || D.settings.phone || '') + '"></div>' +
      '<div class="field"><label>客服微信</label><input type="text" id="s_wechat" value="' + esc(s.service.wechat || D.settings.wechat || '') + '"></div>' +
      '<div class="row-actions"><button class="btn-primary" id="s_mq" style="flex:1">保存（免 Token）</button>' +
      '<button class="btn-ghost" id="s_gh">写入 GitHub</button>' +
      '<button class="btn-ghost" id="s_local">仅本机</button></div>' +
      '<div class="hint" style="font-size:11.5px;color:#8a8f99;margin-top:8px">' +
      '「保存（免 Token）」走公共 MQTT 实时通道（和聊天同一套），<b>立即生效、跨设备可见、不需要令牌</b>；<br>' +
      '「写入 GitHub」需要 Token，会把配置写进仓库 <code>data/shop.json</code> 长期保存（可选）。</div>',
      () => {
        $('#s_mq').onclick = () => saveSetting('mq');
        $('#s_gh').onclick = () => saveSetting('gh');
        $('#s_local').onclick = () => saveSetting('local');
      });
  }

  function collectSetting() {
    const g = id => { const el = $('#' + id); return el ? el.value : ''; };
    const ck = id => { const el = $('#' + id); return el ? el.checked : false; };
    const s = D.shop;
    s.shopName = g('s_name').trim();
    s.score = g('s_score').trim() || '4.5';
    s.banner.text = g('s_banner').trim();
    s.banner.on = ck('s_bannerOn');
    s.metrics.autoFromOrders = ck('s_auto');
    s.metrics.salesToday = Number(g('s_sales')) || 0;
    s.metrics.pendingOrders = Number(g('s_pending')) || 0;
    s.service.phone = g('s_phone').trim();
    s.service.wechat = g('s_wechat').trim();
    return s;
  }

  async function saveSetting(mode) {
    const s = collectSetting();
    LH.LS.set('lh_wb_shop', s);
    const oks = [];
    if (mode === 'mq') {
      if (mqPublish(s)) oks.push('✅ 已实时生效（免 Token）');
      else { oks.push('实时通道还没连上，已先存本机'); LH.LS.set('lh_wb_shop', s); }
    } else if (mode === 'gh') {
      if (mqPublish(s)) oks.push('已实时生效');
      if (!GH.ready()) oks.push('未连接 GitHub，跳过写入');
      else {
        try {
          await GH.putFile('data/shop.json', JSON.stringify(s, null, 2),
            '更新工作台配置 ' + new Date().toLocaleString('zh-CN'));
          oks.push('✅ 已写入 GitHub');
        } catch (e) { oks.push('⚠ GitHub 写入失败：' + e.message); }
      }
    } else {
      oks.push('已存本机');
    }
    LH.toast(oks.join('；'));
    D.metrics = await computeMetrics();
    renderAll();
    closeSheet();
  }

  /* ---- 联系客服 ---- */
  function serviceSheet() {
    const sv = D.shop.service || {};
    const phone = sv.phone || D.settings.phone || '';
    const wechat = sv.wechat || D.settings.wechat || '';
    const hours = D.settings.hours || '';
    let html = '<div class="kv">' +
      '<div><b>客服电话</b>' + (phone ? esc(phone) : '<span style="color:#9aa0ab">未填写</span>') + '</div>' +
      '<div><b>客服微信</b>' + (wechat ? esc(wechat) : '<span style="color:#9aa0ab">未填写</span>') + '</div>' +
      '<div><b>营业时间</b>' + (hours ? esc(hours) : '<span style="color:#9aa0ab">未填写</span>') + '</div>' +
      '</div>';
    if (sv.note) html += '<div class="tip">' + esc(sv.note) + '</div>';
    html += '<div class="row-actions" style="margin-top:14px">' +
      (phone ? '<a class="btn-primary" href="tel:' + esc(phone) + '" style="flex:1;text-align:center;text-decoration:none">📞 拨打电话</a>' : '') +
      (wechat ? '<button class="btn-ghost" id="c_wx">📋 复制微信号</button>' : '') +
      '<button class="btn-ghost" id="c_help">🛠️ 去后台设置</button></div>';
    openSheet('联系客服', html, () => {
      if ($('#c_wx')) $('#c_wx').onclick = () => LH.copyText(wechat).then(() => LH.toast('微信号已复制'));
      $('#c_help').onclick = () => location.href = 'admin.html';
    });
  }

  /* ---- 体验分 / 账户中心 / 待接入 ---- */
  function scoreSheet() {
    openSheet('商家体验分',
      '<div style="text-align:center;padding:6px 0 2px"><div class="big-num">' + esc(D.shop.score || '4.5') + '</div>' +
      '<div style="font-size:12.5px;color:#8a8f99">综合分（满分 5.0）</div></div>' +
      '<div class="tip">体验分由「商品质量 · 服务态度 · 发货速度」决定。保持按时送达、及时回消息就能涨分。</div>' +
      '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="sc_order" style="flex:1">查看订单表现</button>' +
      '<button class="btn-ghost" id="sc_set">改分数</button></div>',
      () => { $('#sc_order').onclick = () => location.href = 'orders.html'; $('#sc_set').onclick = () => settingSheet(); });
  }

  function accountSheet() {
    const s = D.settings;
    const name = D.shop.shopName || s.shopName || '满满小店';
    openSheet('账户中心',
      '<div class="kv">' +
      '<div><b>店铺名</b>' + esc(name) + '</div>' +
      '<div><b>营业时间</b>' + (s.hours ? esc(s.hours) : '未填写') + '</div>' +
      '<div><b>联系电话</b>' + (s.phone ? esc(s.phone) : '未填写') + '</div>' +
      '<div><b>微信号</b>' + (s.wechat ? esc(s.wechat) : '未填写') + '</div>' +
      '<div><b>数据来源</b>' + (D.source === 'github' ? 'GitHub 仓库' : '本机预览') + '</div>' +
      '</div>' +
      '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="ac_admin" style="flex:1">去后台维护资料</button></div>',
      () => { $('#ac_admin').onclick = () => location.href = 'admin.html'; });
  }

  function soonSheet(title) {
    openSheet(title,
      '<div class="tip" style="font-size:13.5px">「' + esc(title) + '」在工作台里先做展示入口，实际维护请到电脑版后台操作。<br><br>' +
      '本页所有数据都来自你的 GitHub 仓库（<code>data/products.json</code> / <code>data/settings.json</code>），和顾客端、后台看到的完全一致。</div>' +
      '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="sn_admin" style="flex:1">打开电脑版后台</button></div>',
      () => { $('#sn_admin').onclick = () => location.href = 'admin.html'; });
  }

  /* ---- 公告 ---- */
  function noticeSheet() {
    const n = D.settings.notice || '';
    openSheet('店铺公告',
      n ? '<div style="font-size:14px;line-height:1.9">' + esc(n) + '</div>'
        : '<div class="tip">还没写公告。到电脑版后台「店铺设置 → 公告」里写一句吧。</div>' +
          '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="nt_set" style="flex:1">去写公告</button></div>',
      () => { if ($('#nt_set')) $('#nt_set').onclick = () => location.href = 'admin.html'; });
  }

  /* ---- 全部商品 ---- */
  function allGoodsSheet(sortBySales) {
    let list = onItems().slice();
    if (sortBySales) list.sort((a, b) => salesNum(b) - salesNum(a));
    const html = list.length
      ? '<div class="plist">' + list.map(it =>
          '<div class="row"><div class="t">' + thumbHTML(it) + '</div>' +
          '<div class="m"><b>' + esc(it.name || '') + '</b>' +
          '<small>' + esc((it.cat || '') + (salesNum(it) ? '　销量' + fmtW(salesNum(it)) : '　库存' + (Number(it.stock) || 0))) + '</small></div>' +
          '<div class="p">' + yuan(it.price) + '</div></div>').join('') + '</div>'
      : '<div class="empty-tip">还没有上架商品</div>';
    openSheet('全部商品', html + '<div class="row-actions" style="margin-top:12px"><button class="btn-primary" id="ag_admin" style="flex:1">去商品管理</button></div>',
      () => { $('#ag_admin').onclick = () => location.href = 'admin.html'; });
  }

  /* ---- 商品详情 ---- */
  function itemSheet(id) {
    const it = (D.products.items || []).find(x => String(x.id) === String(id));
    if (!it) return;
    openSheet(it.name || '商品',
      '<div style="display:flex;gap:12px"><div class="t" style="width:96px;height:96px;border-radius:12px;overflow:hidden;background:#f2f3f5;flex:0 0 auto;display:flex;align-items:center;justify-content:center">' + thumbHTML(it) + '</div>' +
      '<div style="flex:1;min-width:0"><div style="font-size:15px;font-weight:700;line-height:1.4">' + esc(it.name || '') + '</div>' +
      '<div class="big-num" style="font-size:20px;margin-top:6px">' + yuan(it.price) + '</div>' +
      '<div style="font-size:12.5px;color:#8a8f99;margin-top:4px">库存 ' + (Number(it.stock) || 0) + (it.cat ? '　' + esc(it.cat) : '') + '</div></div></div>' +
      (it.desc ? '<div class="tip">' + esc(it.desc) + '</div>' : '') +
      '<div class="row-actions" style="margin-top:14px"><button class="btn-primary" id="it_admin" style="flex:1">去改价 / 编辑</button>' +
      '<button class="btn-ghost" id="it_copy">复制名称</button></div>',
      () => {
        $('#it_admin').onclick = () => location.href = 'admin.html';
        $('#it_copy').onclick = () => LH.copyText(it.name || '').then(() => LH.toast('已复制'));
      });
  }

  /* ================= 事件 ================= */
  function bindGlobal() {
    $('#btnMore').onclick = moreSheet;
    $('#btnService').onclick = serviceSheet;
    $('#banner').onclick = noticeSheet;

    $('#mask').onclick = closeSheet;
    $$('#sheet [data-close]').forEach(b => b.onclick = closeSheet);

    $('#menuGrid').onclick = e => {
      const b = e.target.closest('[data-menu]'); if (!b) return;
      const m = MENUS.find(x => x.key === b.dataset.menu); if (!m) return;
      if (m.href) { location.href = m.href; return; }
      if (m.act === 'scroll') { const el = document.getElementById(m.target); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
      if (m.act === 'score') return scoreSheet();
      if (m.act === 'account') return accountSheet();
      if (m.act === 'soon') return soonSheet(m.name);
    };

    $('#tabbar').onclick = e => {
      const b = e.target.closest('[data-tab]'); if (!b) return;
      const t = TABS.find(x => x.key === b.dataset.tab); if (!t) return;
      if (t.href) { location.href = t.href; return; }
      if (t.act === 'scroll') { const el = document.getElementById(t.target); if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
      if (t.act === 'home') window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    document.querySelectorAll('[data-more]').forEach(b => b.onclick = () => allGoodsSheet(b.dataset.more === 'hot'));

    $('#hotRow').onclick = e => { const c = e.target.closest('[data-id]'); if (c) itemSheet(c.dataset.id); };
    $('#stockRow').onclick = e => { const c = e.target.closest('[data-id]'); if (c) itemSheet(c.dataset.id); };

    $('#connTip').onclick = e => { if (e.target.closest('[data-act="conn"]')) connSheet(); };
  }

  /* ================= 启动 ================= */
  async function boot() {
    const guess = LH.guessRepo(); const c = GH.cfg();
    if (!c.owner && guess.owner) GH.saveCfg(guess);
    bindGlobal();
    initMq();
    await load();
    D.metrics = await computeMetrics();
    renderAll();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
