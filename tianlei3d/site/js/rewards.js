/* ============================================================================
 *  rewards.js —— 天泪纪元 · 福利与积分（官网 / 论坛 / 游戏 通用，零依赖）
 *  --------------------------------------------------------------------------
 *  为什么要有：光写「有奖励」不算数，玩家攒不到就是骗人。这里是真账本。
 *
 *  ▍日常积分（有每日上限，0 点重置）
 *    enter  每日首次进游戏        +10   （上限 10）
 *    play   游玩中每分钟          +2    （上限 40 = 20 分钟）
 *    post   论坛发帖              +10   （上限 30）
 *    reply  论坛回复              +5    （上限 30）
 *    like   点赞                  +1    （上限 10）
 *
 *  ▍邀请裂变（★ 重奖，不占每日上限）
 *    老玩家在「我的海报」拿到 ?inv=<我的uid> 的链接 → 发出去
 *    新玩家点开（官网 / 游戏都算）→
 *        新玩家  见面礼 +50 分（普通自然进来只有 +10）
 *        老玩家  每人 +30 分
 *        里程碑  3 人 → 神器「虚空之刃」直接解锁
 *                5 人 → 称号·引路人 +100 分
 *                10 人 → 称号·开城者 +300 分
 *                20 人 → 称号·筑城之魂 +800 分
 *
 *  ▍为什么"按人数算总额"而不是"收到一条加一次分"
 *    换设备 / 清缓存后会重新收到全部 retained 消息。逐条加分 → 重复累加、分数虚高。
 *    这里改成  invBonus = 人数*30 + 里程碑，只补差额 → 天然幂等，随便刷新都不会多算。
 *
 *  ▍存储
 *    localStorage 'tianlei_rewards'  本机账本（pts / invBonus / 每日额度）
 *    retained  zhz/tianlei/reward/<uid>     积分跨设备同步（取较大值）
 *    retained  zhz/tianlei/inv/<邀请人>/<新人>  一条邀请记录，一对一，天然去重
 *  身份：复用 fp.js 的 Fp.uid()（清缓存/换浏览器仍是同一个人）
 *  ========================================================================== */
(function (root) {
  'use strict';

  var K = 'tianlei_rewards';
  var TOPIC = 'zhz/tianlei/reward/';

  var RULES = {
    enter:   { pts: 10, cap: 10, name: '每日首次进游戏' },
    play:    { pts: 2,  cap: 40, name: '游玩每分钟' },
    post:    { pts: 10, cap: 30, name: '论坛发帖' },
    reply:   { pts: 5,  cap: 30, name: '论坛回复' },
    like:    { pts: 1,  cap: 10, name: '点赞' },
    invitee: { pts: 50, cap: 50, name: '好友送的见面礼' }   // 只发一次（本地标记），上限形同摆设
  };

  var GOALS = [
    { at: 100, k: 'relic', name: '天泪·虚空之刃', desc: '神器提前解锁' },
    { at: 300, k: 'title', name: '建筑师', desc: '论坛专属称号' }
  ];

  /* ---------- ★ 邀请裂变参数 ---------- */
  var INVT = 'zhz/tianlei/inv/';          // zhz/tianlei/inv/<邀请人uid>/<新人uid>
  var INV = {
    newbieGift: 50,                       // 新玩家见面礼
    perFriend: 30,                        // 老玩家每拉来一人
    mile: [
      { n: 3,  pts: 0,   relic: true, name: '天泪·虚空之刃', desc: '神器直接解锁' },
      { n: 5,  pts: 100, name: '引路人',      desc: '称号 + 100 分' },
      { n: 10, pts: 300, name: '开城者',      desc: '称号 + 300 分' },
      { n: 20, pts: 800, name: '筑城之魂',    desc: '称号 + 800 分' }
    ],
    _by: null, _cnt: 0, _members: {}, _ready: false
  };

  var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
  function dstr(d) { d = d || new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }

  var _s = null;
  function load() {
    if (_s) return _s;
    var o = null;
    try { o = JSON.parse(localStorage.getItem(K) || 'null'); } catch (e) {}
    if (!o || typeof o.pts !== 'number') o = { pts: 0, day: dstr(), gain: {}, playSec: 0, firstEnter: '' };
    o.gain = o.gain || {};
    _s = o; return _s;
  }
  function save() {
    // 多标签页防覆盖：写回前先看磁盘上有没有更高的总分（另一个标签页刚攒的）
    try {
      var cur = JSON.parse(localStorage.getItem(K) || 'null');
      if (cur && typeof cur.pts === 'number' && cur.pts > _s.pts) _s.pts = cur.pts;
      if (cur && typeof cur.invBonus === 'number' && cur.invBonus > (_s.invBonus || 0)) _s.invBonus = cur.invBonus;
    } catch (e) {}
    try { localStorage.setItem(K, JSON.stringify(_s)); } catch (e) {}
  }
  function roll() {                       // 跨天就清当日额度
    var s = load(), t = dstr();
    if (s.day !== t) { s.day = t; s.gain = {}; s.playSec = 0; save(); }
    return s;
  }

  /* ---------- 身份 ---------- */
  var _uid = '';
  function uid() {
    if (_uid) return _uid;
    var u = '';
    try { if (root.Fp && Fp.uid) u = Fp.uid(); } catch (e) {}
    if (!u) {
      try { u = localStorage.getItem('tianlei_uid') || ''; } catch (e) {}
      if (!u) { u = 'u' + Math.random().toString(36).slice(2, 12); try { localStorage.setItem('tianlei_uid', u); } catch (e) {} }
    }
    _uid = u; return u;
  }
  function nick() {
    var n = '';
    try { n = localStorage.getItem('tl_forum_nick') || ''; } catch (e) {}
    if (!n) { try { n = (JSON.parse(localStorage.getItem('tianlei_profile') || '{}') || {}).name || ''; } catch (e) {} }
    return n;
  }

  /* ---------- 加分 ---------- */
  function add(tag, n, opts) {
    var r = RULES[tag]; if (!r) return 0;
    var s = roll(), had = s.gain[tag] || 0, room = r.cap - had;
    if (room <= 0) return 0;
    var g = Math.min(n == null ? r.pts : n, room);
    if (g <= 0) return 0;
    var before = s.pts;
    s.pts += g; s.gain[tag] = had + g;
    if (tag === 'enter') s.firstEnter = dstr();
    save(); push(); paint();
    // 跨过里程碑：游戏里弹一条
    GOALS.forEach(function (go) {
      if (before < go.at && s.pts >= go.at) {
        try {
          if (root.HUD && HUD.center) {
            HUD.center('🎉 积分达成 ' + go.at + ' · ' + go.name,
              go.k === 'relic' ? '神器「天泪·虚空之刃」已解锁，按 8 切出' : '论坛称号已到账，去社区看看', 4200);
          }
        } catch (e) {}
        try { console.log('[TLReward] 达成里程碑', go.at, go.name); } catch (e) {}
      }
    });
    return g;
  }

  function pts() { return roll().pts; }
  function todayGain() { var s = roll(), n = 0; for (var k in s.gain) n += s.gain[k]; return n; }

  /* ---------- ★ 邀请：识别我是谁请来的 ---------- */
  function inviterBy() {
    if (INV._by !== null) return INV._by;
    var fromUrl = '';
    try {
      var q = new URLSearchParams(location.search);
      fromUrl = (q.get('inv') || q.get('from') || '').trim();
    } catch (e) {}
    var stored = '';
    try { stored = localStorage.getItem('tl_invite_by') || ''; } catch (e) {}
    if (stored) { INV._by = stored; return INV._by; }        // 认第一次，不被后来的链接覆盖
    if (fromUrl && fromUrl !== uid()) {
      try { localStorage.setItem('tl_invite_by', fromUrl); } catch (e) {}
      INV._by = fromUrl;
    } else INV._by = '';
    return INV._by;
  }

  /* ---------- ★ 新玩家：领见面礼（一辈子一次）---------- */
  function claimGift() {
    var by = inviterBy();
    if (!by || by === uid()) return 0;
    var got = '';
    try { got = localStorage.getItem('tl_invite_gift') || ''; } catch (e) {}
    if (got) return 0;                                       // 已经领过
    try { localStorage.setItem('tl_invite_gift', by); } catch (e) {}
    var g = add('invitee', INV.newbieGift);
    if (g > 0) {
      try {
        if (root.HUD && HUD.center) HUD.center('🎁 好友送的见面礼 +' + g + ' 分',
          '邀请你的人也能拿奖励 —— 现在换你发海报了', 5200);
      } catch (e) {}
    }
    return g;
  }

  /* ---------- ★ 上报：我通过谁的链接来的（retained，一对一自然去重）---------- */
  function reportInvite() {
    var by = inviterBy();
    if (!by || by === uid()) return;
    if (!mq || !mq.connected) return;
    var page = 'site';
    try { page = (document.body && document.body.getAttribute('data-track')) || 'site'; } catch (e) {}
    try {
      mq.publish(INVT + by + '/' + uid(), JSON.stringify({
        uid: uid(), name: nick(), at: Date.now(), page: page
      }), true);
    } catch (e) {}
  }

  /* ---------- ★ 结算：按"我拉来的人数"算总奖励，只补差额（幂等）---------- */
  function syncBonus() {
    var n = INV._cnt || 0;
    if (!n) return 0;
    var want = 0, hit = null;
    want = n * INV.perFriend;
    for (var i = 0; i < INV.mile.length; i++) {
      if (n >= INV.mile[i].n) { want += INV.mile[i].pts; hit = INV.mile[i]; }
    }
    var s = roll(), had = s.invBonus || 0;
    if (want <= had) return 0;
    var d = want - had;
    s.pts += d; s.invBonus = want;
    save(); push(); paint();

    try {
      if (root.HUD && HUD.center) {
        HUD.center('🎉 邀请奖励到账 +' + d + ' 分',
          '已拉来 ' + n + ' 位好友' + (hit ? ' · 达成「' + hit.name + '」' : ''), 5200);
      }
    } catch (e) {}

    // 3 人 → 游戏内神器直接解锁（Ref 是游戏页的东西，有就同步过去）
    if (n >= 3) {
      try {
        if (root.Ref && root.Ref.invited) {
          INV._members && Object.keys(INV._members).forEach(function (k) { root.Ref.invited[k] = 1; });
          if (root.Ref.refresh) root.Ref.refresh(false);
        }
      } catch (e) {}
    }
    return d;
  }

  function syncTitle() {
    var n = INV._cnt || 0, t = '';
    for (var i = 0; i < INV.mile.length; i++) if (n >= INV.mile[i].n && INV.mile[i].name.indexOf('神器') < 0) t = INV.mile[i].name;
    return t;
  }

  function title() {
    var p = pts();
    var it = syncTitle();
    if (it) return it;                       // 邀请称号优先（它更值钱）
    return p >= 300 ? '建筑师' : (p >= 100 ? '拓荒者' : '旅人');
  }
  function nextGoal() {
    var p = pts();
    for (var i = 0; i < GOALS.length; i++) if (p < GOALS[i].at) return GOALS[i];
    return null;
  }

  /* ---------- 跨设备同步（保留消息，取大值） ---------- */
  var mq = null, started = false;
  function push() {
    if (!mq || !mq.connected) return;
    try {
      mq.publish(TOPIC + uid(), JSON.stringify({
        uid: uid(), pts: pts(), title: title(), name: nick(), at: Date.now()
      }), true);
    } catch (e) {}
  }

  function connect() {
    if (started) return; started = true;
    if (typeof root.MiniMqtt === 'undefined') return;
    try {
      mq = MiniMqtt.createClient({ clientId: 'tlrw' + uid().slice(-6) });
      mq.on('connect', function () {
        try { mq.subscribe(TOPIC + uid()); } catch (e) {}
        try { mq.subscribe(INVT + uid() + '/+'); } catch (e) {}          // ★ 新版邀请记录
        try { mq.subscribe('zhz/tianlei/fps/+/ref/' + uid() + '/+'); } catch (e) {}  // ★ 旧版邀请（老玩家别丢）
        push();
        reportInvite();                                                  // ★ 上报"我是谁请来的"
      });
      mq.on('message', function (t, p) {
        /* ★ 记一个新邀请成员（新旧两套 topic 都走这里，天然去重） */
        function addMember(who) {
          if (!who || who === uid()) return;
          if (INV._members[who]) return;
          INV._members[who] = 1;
          INV._cnt = Object.keys(INV._members).length;
          syncBonus();
          paint();
        }

        // 新版：zhz/tianlei/inv/<邀请人>/<新人>
        var pre = INVT + uid() + '/';
        if (t.indexOf(pre) === 0) { addMember(t.slice(pre.length)); return; }

        // 旧版：zhz/tianlei/fps/<房间>/ref/<邀请人>/<新人>
        var legacy = '/ref/' + uid() + '/';
        var li = t.indexOf(legacy);
        if (t.indexOf('zhz/tianlei/fps/') === 0 && li > 0) {
          addMember(t.slice(li + legacy.length));
          return;
        }

        if (t !== TOPIC + uid()) return;
        try {
          var o = JSON.parse(p || '{}');
          if (o && typeof o.pts === 'number') {
            var s = roll();
            if (o.pts > s.pts) { s.pts = o.pts; save(); paint(); }   // 别的设备攒的分，合并过来
          }
        } catch (e) {}
      });
    } catch (e) {}
  }

  /* ---------- 渲染（官网 / 论坛共用 id） ---------- */
  function paint() {
    if (!root.document) return;
    var p = pts(), nx = nextGoal();
    var a = document.getElementById('ptsNow'); if (a) a.textContent = p;
    var f = document.getElementById('ptsNowFix'); if (f) f.textContent = p;
    var b = document.getElementById('ptsBar');
    if (b) {
      var tgt = nx ? nx.at : 300;
      b.style.width = Math.max(2, Math.min(100, p / tgt * 100)) + '%';
    }
    var c = document.getElementById('ptsBadge');
    if (c) c.textContent = '积分 ' + p + ' · ' + title();
    var d = document.getElementById('ptsToday');
    if (d) d.textContent = todayGain();
    var g = document.getElementById('ptsChipN'); if (g) g.textContent = p;
    var h = document.getElementById('ptsChip');
    if (h) { h.className = 'chip' + (p >= 100 ? ' on' : ''); h.title = '今日已得 ' + todayGain() + ' 分 · 攒满 100 分解锁神器'; }
    var e = document.getElementById('ptsNext');
    if (e) e.textContent = nx ? ('再攒 ' + (nx.at - p) + ' 分解锁「' + nx.name + '」') : '全部解锁 ✓';

    /* ---------- ★ 邀请进度显示（官网 / 海报页共用这几个 id） ---------- */
    var n = INV._cnt || 0;
    var iv = document.getElementById('invCount'); if (iv) iv.textContent = n;
    var ir = document.getElementById('invReward'); if (ir) ir.textContent = n * INV.perFriend;
    var im = document.getElementById('invMile');
    if (im) {
      var nxt = null;
      for (var i = 0; i < INV.mile.length; i++) {
        if (n < INV.mile[i].n) { nxt = INV.mile[i]; break; }
      }
      im.textContent = nxt
        ? ('再来 ' + (nxt.n - n) + ' 人 → ' + nxt.name + '（' + nxt.desc + '）')
        : '邀请奖励全部拿到 ✓';
    }
    var ib = document.getElementById('invBar');
    if (ib) {
      var tgt2 = 3;
      for (var j = 0; j < INV.mile.length; j++) {
        if (n < INV.mile[j].n) { tgt2 = INV.mile[j].n; break; }
      }
      ib.style.width = Math.max(2, Math.min(100, n / tgt2 * 100)) + '%';
    }
    var iby = document.getElementById('invBy');
    if (iby) {
      var by = inviterBy();
      if (by) { iby.style.display = 'block'; } else { iby.style.display = 'none'; }
    }
    var ic = document.getElementById('invTitle'); if (ic) ic.textContent = title();
  }

  /* ---------- 官网实时人气（真数据：玩家心跳 + 今日访客） ---------- */
  function watchLive(el) {
    if (!el || typeof root.MiniMqtt === 'undefined') return;
    var players = {}, visits = {};
    var c;
    try { c = MiniMqtt.createClient({ clientId: 'tllive' + Math.random().toString(36).slice(2, 7) }); }
    catch (e) { return; }
    c.on('connect', function () {
      try {
        c.subscribe('zhz/tianlei/fps/+/p/+');     // 玩家状态心跳（8Hz，非保留）
        c.subscribe('zhz/tianlei/stats/v/+');     // 访客留痕（保留，含历史）
      } catch (e) {}
    });
    c.on('message', function (t, p) {
      var now = Date.now();
      if (/\/p\/[^\/]+$/.test(t)) { players[t] = now; }
      else if (t.indexOf('zhz/tianlei/stats/v/') === 0) { visits[t] = p; }
    });
    function render() {
      var now = Date.now(), on = 0, k;
      for (k in players) { if (now - players[k] > 30000) delete players[k]; else on++; }
      var d0 = new Date(); d0.setHours(0, 0, 0, 0); var tv = 0;
      for (k in visits) {
        try { if ((JSON.parse(visits[k]) || {}).at >= d0.getTime()) tv++; } catch (e) {}
      }
      el.innerHTML = on > 0
        ? '<i class="dot on"></i>此刻 <b>' + on + '</b> 人在世界里 · 今天 <b>' + tv + '</b> 人进来过'
        : '<i class="dot"></i>世界此刻空着 · 今天 <b>' + tv + '</b> 人进来过 — <b>来当第一个</b>';
      el.classList.add('ready');
    }
    setInterval(render, 4000); setTimeout(render, 1500);
  }

  /* ---------- 自动埋点：进游戏就记 ---------- */
  function isGame() {
    try { return !/\/site\//.test(location.pathname); } catch (e) { return false; }
  }
  var tickTimer = null;
  function startPlayClock() {
    if (tickTimer) return;
    tickTimer = setInterval(function () {
      var s = roll(); s.playSec = (s.playSec || 0) + 60; save();
      var g = add('play', 2);
      if (g) { try { if (root.HUD && HUD.mini) HUD.mini('⏱ +' + g + ' 分 · 共 ' + pts()); } catch (e) {} }
    }, 60000);
  }

  function boot() {
    connect();
    // ★ 新玩家：如果是被邀请来的，先领见面礼（一辈子只领一次）
    claimGift();
    if (isGame()) {
      var s = roll();
      if (s.firstEnter !== dstr()) add('enter', 10);   // 每天第一次进来
      startPlayClock();
    }
    paint();
    watchLive(document.getElementById('liveChip'));
    document.addEventListener('visibilitychange', function () { if (!document.hidden) paint(); });
  }

  root.TLReward = {
    add: add, pts: pts, todayGain: todayGain, title: title, uid: uid,
    rules: RULES, goals: GOALS, nextGoal: nextGoal, paint: paint, watchLive: watchLive,
    /* ★ 邀请相关，给官网 / 海报页用 */
    invite: {
      rules: INV,
      by: inviterBy,          // 我是谁请来的
      count: function () { return INV._cnt || 0; },
      members: function () { return Object.keys(INV._members || {}); },
      gift: claimGift,        // 手动补领（例如先看了官网再点进游戏）
      report: reportInvite,
      nextMile: function () {
        var n = INV._cnt || 0;
        for (var i = 0; i < INV.mile.length; i++) if (n < INV.mile[i].n) return INV.mile[i];
        return null;
      },
      link: function (base) {
        var b = base || (location.origin + location.pathname.replace(/[^/]*$/, ''));
        return b + 'index.html?inv=' + encodeURIComponent(uid());
      }
    }
  };

  if (root.document) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else setTimeout(boot, 0);
  }
})(typeof self !== 'undefined' ? self : this);
