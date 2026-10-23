/* ============================================================================
 *  hearth.js —— 天泪纪元 · 守夜灯（离线发育 + 极强留存钩子）
 *  --------------------------------------------------------------------------
 *  为什么要有这个
 *    这套联机走公共 broker，实测延迟 4~5 秒、单人流量约 1.6KB/s。
 *    对抗类玩法在这种条件下天生吃亏（人一多就崩）。
 *    但建造用的是 retained 消息：发一次永久在，天然适合「累积型」玩法。
 *    所以这里把游戏重心搬到发育流 —— 离线也在长，但人必须回来。
 *
 *  ▍核心：一座城的「守夜灯」
 *    雨夜之城靠灯亮着才有人住。灯要每天添一次柴（3 秒钟的动作）。
 *    灯亮 → 居民留下、建筑产出全速、离线累积翻倍
 *    灯灭 → 居民开始离开、建筑开始腐化、产出归零
 *
 *  ▍火的分级（按离上次添柴多久）
 *    < 20h  旺   🔥  产出 100%，居民不流失
 *    20~32h 微   🌤  产出  60%
 *    32~56h 将熄 🕯  产出  25%，HUD 红色倒计时警告
 *    56~80h 灭   💀  产出   0%，居民每小时走一个
 *    > 80h  废墟 🏚  建筑进入废墟态（不删除数据，但没法用、看得见破败）
 *
 *  ▍居民（这是"宠物会死"的等价物，但更贴合建造游戏）
 *    每 3 小时自然来 1 位（城越大来得越快，上限 20 位）
 *    每位居民 +8% 产出
 *    火灭后每小时走 1 位 —— 走了就是走了，不会自己回来
 *    回来的玩家要重新攒人 → 这就是"必须回来"的最强理由
 *
 *  ▍离线产出
 *    回来时一次性结算：离开多久就产多少（旺时上限 24h，微时 12h，将熄 6h，灭 0）
 *    结算必须点一下「收取」才入账 → 玩家有"我回来领东西"的爽感
 *
 *  ▍连击
 *    连续每天添柴 → streak+1，产出倍率 1.0 ~ 2.0（20 天满）
 *    断一天 → streak 归 1（不清零到 0，避免玩家破罐破摔）
 *
 *  ▍为什么不做"真的删数据"
 *    废墟只是状态位（从时间戳算出来的），方块的 retained 消息一条都不删。
 *    原因：删数据是不可逆的，一个时间戳算错的 bug 就能把玩家几周的城清空。
 *    而"看得见自己的城变成废墟"在情绪上跟删掉几乎一样重，还留了修复的可能。
 *
 *  依赖：无（只用 localStorage + 可选 Net/HUD/Build，没有也能跑）
 * ========================================================================== */
(function (root) {
  'use strict';

  var K = 'tianlei_hearth';
  var TOPIC = 'zhz/tianlei/hearth/';       // retained：跨设备同步自己城的状态

  var HOUR = 3600 * 1000;
  var DAY = 24 * HOUR;

  /* ---------- 参数（全部集中在这里，好调）---------- */
  var CFG = {
    fire: [
      { h: 20, key: 'blaze', name: '旺',   icon: '🔥', mult: 1.00, awayCap: 24 },
      { h: 32, key: 'dim',   name: '微',   icon: '🌤', mult: 0.50, awayCap: 12 },
      { h: 56, key: 'dying', name: '将熄', icon: '🕯', mult: 0.10, awayCap: 6 },
      { h: 80, key: 'out',   name: '已灭', icon: '💀', mult: 0.00, awayCap: 0 },
      { h: 1e9, key: 'ruin', name: '废墟', icon: '🏚', mult: 0.00, awayCap: 0 }
    ],
    residentEvery: 3 * HOUR,   // 自然来一个居民的间隔（会按城规模缩短）
    residentMax: 20,
    residentBonus: 0.03,       // 每个居民 +3% 产出（上限 20 位 → +60%）
    leavePerHour: 1,           // 火灭后每小时走几个
    streakMax: 20,             // 连击满级天数
    streakPer: 0.03,           // 每天 +3%（20 天 = +60%）

    /* 每种方块每小时产出（木/石/晶）。没列到的按 fallback 给一点点 */
    prod: {
      wall_wood: { wood: 3.0 }, wall_metal: { stone: 2.0 }, wall_stone: { stone: 3.0 },
      wall_brick: { stone: 2.4 }, wall_conc: { stone: 2.6 }, glass: { crystal: 0.6 },
      floor: { wood: 1.2 }, slab: { stone: 0.8 }, step: { stone: 0.8 },
      crate: { wood: 6.0 }, barrel: { wood: 4.0 }, lamp: { crystal: 2.0 },
      crystal: { crystal: 5.0 }, planter: { wood: 2.0 }
    },
    prodFallback: { wood: 0.5, stone: 0.5, crystal: 0.1 }
  };

  /* ---------- 存档 ---------- */
  var S = null;
  function blank() {
    return {
      v: 1,
      res: { wood: 0, stone: 0, crystal: 0 },
      pend: { wood: 0, stone: 0, crystal: 0 },   // 待收取（离线产出）
      pendH: 0,                                  // 待收取覆盖了多少小时
      fireAt: 0,          // 上次添柴时间
      streak: 0,
      lastDay: '',        // 上次添柴的日期（YYYY-MM-DD）
      lastSeen: 0,        // 上次在线时间
      lastAccrue: 0,      // 上次结算时间
      residents: 0,
      resAt: 0,           // 上次"来居民"的基准时间
      totalProduced: { wood: 0, stone: 0, crystal: 0 },
      daysVisited: 0,
      eventDay: '',       // 今日事件是哪天领的
      best: 0             // 居民历史最高（掉了会心疼）
    };
  }
  function load() {
    if (S) return S;
    var o = null;
    try { o = JSON.parse(localStorage.getItem(K) || 'null'); } catch (e) {}
    S = o && typeof o === 'object' ? Object.assign(blank(), o) : blank();
    if (!S.res) S.res = { wood: 0, stone: 0, crystal: 0 };
    if (!S.pend) S.pend = { wood: 0, stone: 0, crystal: 0 };
    if (!S.totalProduced) S.totalProduced = { wood: 0, stone: 0, crystal: 0 };
    return S;
  }
  function save() {
    try { localStorage.setItem(K, JSON.stringify(S)); } catch (e) {}
  }

  /* ---------- 时间小工具 ---------- */
  function pad(n) { return n < 10 ? '0' + n : '' + n; }
  function dstr(t) { var d = new Date(t || Date.now()); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
  function hours(ms) { return ms / HOUR; }

  /* ---------- 火的状态 ---------- */
  function fire() {
    load();
    var since = S.fireAt ? (Date.now() - S.fireAt) : 1e12;   // 从没点过 = 废墟
    var h = hours(since);
    for (var i = 0; i < CFG.fire.length; i++) {
      if (h < CFG.fire[i].h) {
        var f = CFG.fire[i];
        return {
          key: f.key, name: f.name, icon: f.icon, mult: f.mult, awayCap: f.awayCap,
          hoursSince: h,
          leftH: Math.max(0, f.h - h),          // 距离下一档还有几小时
          nextAt: f.h
        };
      }
    }
    return { key: 'ruin', name: '废墟', icon: '🏚', mult: 0, awayCap: 0, hoursSince: h, leftH: 0, nextAt: 0 };
  }

  /* ---------- 建筑统计 → 每小时产出 ---------- */
  function rates() {
    var out = { wood: 0, stone: 0, crystal: 0 };
    var n = 0;
    try {
      var list = root.Build && root.Build.list;
      if (list && list.size) {
        list.forEach(function (v) {
          n++;
          var t = (v && v.t) || '';
          var p = CFG.prod[t] || CFG.prodFallback;
          out.wood += p.wood || 0;
          out.stone += p.stone || 0;
          out.crystal += p.crystal || 0;
        });
      }
    } catch (e) {}

    var f = fire();
    // ★ 加成走"加法封顶"，再乘火倍率。
    //   之前是 residents × streak 连乘：20 位居民(+160%) × 20 天(+100%) = 5.2 倍，
    //   会把"将熄只有 25%"的惩罚完全抵消掉 —— 惩罚形同虚设。
    var buffPct = Math.min(1.2,
      (S.residents || 0) * CFG.residentBonus +
      Math.min(CFG.streakMax, S.streak || 0) * CFG.streakPer);
    var scale = f.mult * (1 + buffPct);
    out.wood *= scale; out.stone *= scale; out.crystal *= scale;
    out.blocks = n;
    out.scale = scale;
    return out;
  }

  /* ---------- 居民：自然增长 + 火灭流失 ---------- */
  function syncResidents(now) {
    load();
    now = now || Date.now();
    var f = fire();
    var changed = false;

    if (!S.resAt) { S.resAt = now; changed = true; }

    if (f.key === 'blaze' || f.key === 'dim' || f.key === 'dying') {
      /* 火还亮着 → 居民自然增长；城越大来得越快 */
      var blocks = 0;
      try { blocks = (root.Build && root.Build.list && root.Build.list.size) || 0; } catch (e) {}
      var speed = 1 + Math.min(2, blocks / 40);            // 40 块以上速度 3x
      var every = CFG.residentEvery / speed;
      var elapsed = now - S.resAt;
      if (elapsed >= every && S.residents < CFG.residentMax) {
        var add = Math.floor(elapsed / every);
        S.residents = Math.min(CFG.residentMax, S.residents + add);
        S.resAt = now - (elapsed % every);
        if (S.residents > (S.best || 0)) S.best = S.residents;
        changed = true;
        if (add > 0) notify('🏠 城里来了 ' + add + ' 位居民', '现在共有 ' + S.residents + ' 位 · 产出 +' + Math.round(S.residents * CFG.residentBonus * 100) + '%', 3600);
      } else if (S.residents >= CFG.residentMax) {
        S.resAt = now;
        changed = true;
      }
    } else {
      /* 火灭了 → 每小时走一个，走了不回来 */
      var e2 = now - S.resAt;
      var gone = Math.floor(hours(e2) * CFG.leavePerHour);
      if (gone > 0 && S.residents > 0) {
        var real = Math.min(gone, S.residents);
        S.residents -= real;
        S.resAt = now;
        changed = true;
        notify('💀 ' + real + ' 位居民离开了你的城',
          '灯灭太久了 —— 回来添柴才能留住人（还剩 ' + S.residents + ' 位）', 6000);
      } else if (gone > 0) {
        S.resAt = now; changed = true;
      }
    }
    if (changed) { save(); push(); }
  }

  /* ---------- 离线产出结算（累加到 pend，等玩家手动收取）---------- */
  function accrue(now) {
    load();
    now = now || Date.now();
    if (!S.lastAccrue) { S.lastAccrue = now; save(); return { wood: 0, stone: 0, crystal: 0, h: 0 }; }

    var f = fire();
    var awayH = hours(now - S.lastAccrue);
    var capH = f.awayCap;                       // 旺 24h / 微 12h / 将熄 6h / 灭 0
    var effH = Math.min(awayH, capH);
    if (effH <= 0) { S.lastAccrue = now; save(); return { wood: 0, stone: 0, crystal: 0, h: 0 }; }

    var r = rates();
    var got = {
      wood: r.wood * effH,
      stone: r.stone * effH,
      crystal: r.crystal * effH,
      h: effH,
      capped: awayH > capH
    };
    S.pend.wood += got.wood;
    S.pend.stone += got.stone;
    S.pend.crystal += got.crystal;
    S.pendH += effH;
    S.lastAccrue = now;
    save();
    return got;
  }

  /* ---------- 收取 ---------- */
  function claim() {
    load();
    var g = { wood: Math.floor(S.pend.wood), stone: Math.floor(S.pend.stone), crystal: Math.floor(S.pend.crystal) };
    if (g.wood + g.stone + g.crystal <= 0) return null;
    S.res.wood += g.wood; S.res.stone += g.stone; S.res.crystal += g.crystal;
    S.totalProduced.wood += g.wood; S.totalProduced.stone += g.stone; S.totalProduced.crystal += g.crystal;
    S.pend = { wood: 0, stone: 0, crystal: 0 };
    var h = S.pendH; S.pendH = 0;
    save(); push();
    notify('📦 收下了 ' + Math.floor(h) + ' 小时的产出',
      '木 +' + g.wood + ' · 石 +' + g.stone + ' · 晶 +' + g.crystal, 4200);
    try { if (root.Sfx && Sfx.pickup) Sfx.pickup(); } catch (e) {}
    paint();
    return g;
  }

  /* ---------- 添柴（每天一次的核心动作）---------- */
  function tend() {
    load();
    var today = dstr();
    if (S.lastDay === today) {
      notify('🔥 今天已经添过柴了', '明天再来 · 连续 ' + S.streak + ' 天', 2600);
      return false;
    }
    // 先结算离线产出，避免添柴后按新倍率重算历史
    accrue();

    var last = S.lastDay;
    S.fireAt = Date.now();
    S.resAt = Date.now();
    if (last) {
      var d1 = new Date(last + 'T00:00:00'), d2 = new Date(today + 'T00:00:00');
      var gap = Math.round((d2 - d1) / DAY);
      S.streak = (gap === 1) ? Math.min(CFG.streakMax, (S.streak || 0) + 1) : 1;
    } else {
      S.streak = 1;
    }
    S.lastDay = today;
    S.daysVisited = (S.daysVisited || 0) + 1;
    save(); push();

    var f = fire();
    notify('🔥 守夜灯添好了 · 连续 ' + S.streak + ' 天',
      '产出倍率 ' + (1 + Math.min(CFG.streakMax, S.streak) * CFG.streakPer).toFixed(2) + 'x · 灯能撑 20 小时', 4200);
    try { if (root.Sfx && Sfx.waveUp) Sfx.waveUp(); } catch (e) {}
    paint();
    return true;
  }

  /* ---------- 建筑腐化判定（给渲染用，不改数据）---------- */
  function ruined() {
    var f = fire();
    return f.key === 'ruin' || f.key === 'out';
  }
  /* 废墟程度 0~1，给材质做灰化/破损用 */
  function ruinLevel() {
    var f = fire();
    if (f.key === 'blaze') return 0;
    if (f.key === 'dim') return 0.06;
    if (f.key === 'dying') return 0.22;
    if (f.key === 'out') return Math.min(0.75, 0.4 + (f.hoursSince - 56) / 60);
    return 1;
  }

  /* ---------- 每日事件（只有当天上线才能领）---------- */
  var EVENTS = [
    { id: 'drift',  n: '雨夜里漂来一只箱子',  r: { wood: 120, stone: 60,  crystal: 4  } },
    { id: 'wander', n: '有位旅人想留下',      r: { resident: 1 } },
    { id: 'vein',   n: '发现一条晶石矿脉',    r: { crystal: 18 } },
    { id: 'forest', n: '西边的林子长得很快',  r: { wood: 260 } },
    { id: 'quake',  n: '旧墙里露出石料',      r: { stone: 240 } }
  ];
  function todayEvent() {
    var h = 0, s = dstr();
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return EVENTS[h % EVENTS.length];
  }
  function eventReady() { load(); return S.eventDay !== dstr(); }
  function claimEvent() {
    load();
    if (!eventReady()) return null;
    var ev = todayEvent();
    S.eventDay = dstr();
    if (ev.r.resident) {
      S.residents = Math.min(CFG.residentMax, (S.residents || 0) + ev.r.resident);
      if (S.residents > (S.best || 0)) S.best = S.residents;
    } else {
      for (var k in ev.r) {
        if (S.res[k] != null) { S.res[k] += ev.r[k]; S.totalProduced[k] += ev.r[k]; }
      }
    }
    save(); push();
    notify('🎁 ' + ev.n, '已领取 · 明天会换一个新的', 4600);
    try { if (root.Sfx && Sfx.waveUp) Sfx.waveUp(); } catch (e) {}
    paint();
    return ev;
  }

  /* ---------- 通知（有 HUD 就用 HUD，没有就 console）---------- */
  function notify(t, s, ms) {
    try {
      if (root.HUD && HUD.center) { HUD.center(t, s, ms || 3000); return; }
    } catch (e) {}
    try { console.log('[Hearth]', t, '—', s || ''); } catch (e) {}
  }

  /* ---------- 跨设备同步（retained）---------- */
  var mq = null, sentOnce = false;
  function push() {
    if (!mq || !mq.connected) return;
    load();
    try {
      mq.publish(TOPIC + uid(), JSON.stringify({
        res: S.res, residents: S.residents, best: S.best, streak: S.streak,
        fireAt: S.fireAt, lastDay: S.lastDay, at: Date.now()
      }), true);
    } catch (e) {}
  }
  function uid() {
    try { if (root.Fp && Fp.uid) return Fp.uid(); } catch (e) {}
    var u = '';
    try { u = localStorage.getItem('tianlei_uid') || ''; } catch (e) {}
    return u || 'anon';
  }
  function connect() {
    if (mq || typeof root.MiniMqtt === 'undefined') return;
    try {
      mq = MiniMqtt.createClient({ clientId: 'tlht' + uid().slice(-6) });
      mq.on('connect', function () {
        try { mq.subscribe(TOPIC + uid()); } catch (e) {}
        push();
      });
      mq.on('message', function (t, p) {
        if (t !== TOPIC + uid()) return;
        try {
          var o = JSON.parse(p || '{}');
          if (!o) return;
          // 只合并"更富有"的存档，避免被旧数据覆盖
          var mine = S.res.wood + S.res.stone + S.res.crystal * 10;
          var his = (o.res ? (o.res.wood || 0) + (o.res.stone || 0) + (o.res.crystal || 0) * 10 : 0);
          if (his > mine) {
            S.res = o.res; S.residents = o.residents || 0;
            S.best = Math.max(S.best || 0, o.best || 0);
            S.streak = Math.max(S.streak || 0, o.streak || 0);
            if ((o.fireAt || 0) > (S.fireAt || 0)) S.fireAt = o.fireAt;
            if (o.lastDay) S.lastDay = o.lastDay;
            save(); paint();
          }
        } catch (e) {}
      });
    } catch (e) {}
  }

  /* ---------- HUD 渲染 ---------- */
  function fmt(n) {
    n = Math.floor(n || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 10000) return (n / 1000).toFixed(1) + 'k';
    return '' + n;
  }
  function paint() {
    if (!root.document) return;
    load();
    var f = fire(), r = rates();
    var $ = function (s) { return document.querySelector(s); };

    var set = function (sel, v) { var e = $(sel); if (e) e.textContent = v; };
    set('#htWood', fmt(S.res.wood));
    set('#htStone', fmt(S.res.stone));
    set('#htCrystal', fmt(S.res.crystal));
    set('#htRes', S.residents || 0);
    set('#htStreak', S.streak || 0);
    set('#htFire', f.icon + ' ' + f.name);
    set('#htRate', '+' + fmt(r.wood + r.stone) + '/h');
    set('#htBlocks', r.blocks || 0);

    /* ★ 废墟/将熄：整屏降饱和。只改 CSS filter，绝不动共享材质（否则会污染别人的方块） */
    try {
      var cvEl = document.getElementById('cv');
      if (cvEl) {
        var rl = ruinLevel();
        cvEl.classList.toggle('ruined', rl >= 0.75);
        cvEl.classList.toggle('dying', rl > 0 && rl < 0.75);
      }
    } catch (e) {}

    var chip = $('#htChip');
    if (chip) {
      chip.className = 'ht-chip ' + f.key;
      var pend = S.pend.wood + S.pend.stone + S.pend.crystal;
      chip.textContent = f.icon + ' ' + f.name + (pend >= 1 ? ' · 📦' : '');
    }

    var tip = $('#htTip');
    if (tip) {
      if (f.key === 'blaze' || f.key === 'dim') {
        tip.textContent = '灯还能撑 ' + f.leftH.toFixed(1) + ' 小时 · 记得回来添柴';
        tip.className = 'ht-tip ok';
      } else if (f.key === 'dying') {
        tip.textContent = '⚠ 只剩 ' + f.leftH.toFixed(1) + ' 小时灯就灭了，居民要开始走';
        tip.className = 'ht-tip warn';
      } else {
        tip.textContent = '💀 灯已经灭了 —— 居民在离开，快添柴';
        tip.className = 'ht-tip bad';
      }
    }

    var pn = $('#htPend');
    if (pn) {
      var have = S.pend.wood + S.pend.stone + S.pend.crystal;
      pn.style.display = have >= 1 ? 'block' : 'none';
      pn.innerHTML = '📦 离线产出：木 <b>' + fmt(S.pend.wood) + '</b> · 石 <b>' +
        fmt(S.pend.stone) + '</b> · 晶 <b>' + fmt(S.pend.crystal) + '</b>' +
        '<button id="htClaim">收取</button>';
      var cb = $('#htClaim');
      if (cb) cb.onclick = function () { claim(); };
    }
    var ev = $('#htEvent');
    if (ev) {
      if (eventReady()) {
        ev.style.display = 'block';
        ev.innerHTML = '🎁 今日事件：<b>' + todayEvent().n + '</b><button id="htEv">领取</button>';
        var eb = $('#htEv');
        if (eb) eb.onclick = function () { claimEvent(); };
      } else { ev.style.display = 'none'; }
    }
    var tb = $('#htTend');
    if (tb) {
      var done = S.lastDay === dstr();
      tb.textContent = done ? '🔥 今天已添柴' : '🔥 添柴（点亮守夜灯）';
      tb.disabled = done;
      tb.className = 'ht-tend' + (done ? ' done' : '');
    }
  }

  /* ---------- 面板开关 ---------- */
  function bindUI() {
    var $ = function (s) { return document.querySelector(s); };
    var chip = $('#htChip'), panel = $('#htPanel'), close = $('#htClose'), tend = $('#htTend');
    if (chip && panel) chip.onclick = function () {
      panel.classList.toggle('on');
      paint();
      try { if (root.Sfx && Sfx.ui) Sfx.ui(); } catch (e) {}
    };
    if (close && panel) close.onclick = function () { panel.classList.remove('on'); };
    if (tend) tend.onclick = function () { tend_(); };
  }
  function tend_() {
    var ok = tend();
    if (ok) {
      // 添柴后立刻结算一次，让玩家看到"我又能攒了"
      try { if (root.HUD && HUD.center) { } } catch (e) {}
      paint();
    }
  }

  /* ---------- 启动 ---------- */
  var tickT = null;
  function boot() {
    load();
    connect();

    var now = Date.now();
    // 结算离开这段时间的产出
    var got = accrue(now);
    syncResidents(now);
    S.lastSeen = now;
    save();

    // 回来时的"大字报"—— 这是让人第二天还想来的关键一击
    if (got.h >= 1) {
      var tot = got.wood + got.stone + got.crystal;
      notify('📦 你离开的 ' + got.h.toFixed(0) + ' 小时里，城一直在运转',
        '木 +' + Math.floor(got.wood) + ' · 石 +' + Math.floor(got.stone) +
        ' · 晶 +' + Math.floor(got.crystal) + (got.capped ? '（已达上限，早点回来能拿更多）' : ''),
        6200);
    }

    syncResidents();
    paint();
    bindUI();

    if (tickT) clearInterval(tickT);
    tickT = setInterval(function () {
      try { syncResidents(); paint(); } catch (e) {}
    }, 30000);

    // 离开时存一次
    root.addEventListener && root.addEventListener('pagehide', function () {
      try { S.lastSeen = Date.now(); save(); push(); } catch (e) {}
    });
    root.addEventListener && root.addEventListener('visibilitychange', function () {
      try {
        if (root.document && !root.document.hidden) { accrue(); syncResidents(); paint(); }
      } catch (e) {}
    });
  }

  /* ---------- 对外 ---------- */
  root.Hearth = {
    cfg: CFG,
    state: function () { return load(); },
    fire: fire, rates: rates, tend: tend, claim: claim, accrue: accrue,
    residents: function () { return load().residents || 0; },
    ruined: ruined, ruinLevel: ruinLevel,
    event: { today: todayEvent, ready: eventReady, claim: claimEvent },
    paint: paint,
    /* 给测试/调试用 */
    _boot: boot,
    _reset: function () { try { localStorage.removeItem(K); } catch (e) {} S = null; },
    _save: save, _load: load
  };

  if (root.document) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else setTimeout(boot, 0);
  }
})(typeof self !== 'undefined' ? self : this);
