/* ============================================================================
 *  rewards.js —— 天泪纪元 · 福利与积分（官网 / 论坛 / 游戏 通用，零依赖）
 *  --------------------------------------------------------------------------
 *  为什么要有：光写「有奖励」不算数，玩家攒不到就是骗人。这里是真账本。
 *
 *  积分来源（每日上限，0 点重置）：
 *    enter  每日首次进游戏        +10   （上限 10）
 *    play   游玩中每分钟          +2    （上限 40 = 20 分钟）
 *    post   论坛发帖              +10   （上限 30）
 *    reply  论坛回复              +5    （上限 30）
 *    like   点赞                  +1    （上限 10）
 *
 *  里程碑（真的会生效）：
 *    100 分 → 神器「天泪·虚空之刃」提前解锁（游戏内 canUse 已接）
 *    300 分 → 论坛称号「建筑师」
 *
 *  存储：localStorage 'tianlei_rewards'（本机账本）
 *        + broker 保留消息 zhz/tianlei/reward/<uid>（跨设备同步，取较大值）
 *  身份：复用 fp.js 的 Fp.uid()（清缓存/换浏览器仍是同一个人）
 *  ========================================================================== */
(function (root) {
  'use strict';

  var K = 'tianlei_rewards';
  var TOPIC = 'zhz/tianlei/reward/';

  var RULES = {
    enter: { pts: 10, cap: 10, name: '每日首次进游戏' },
    play:  { pts: 2,  cap: 40, name: '游玩每分钟' },
    post:  { pts: 10, cap: 30, name: '论坛发帖' },
    reply: { pts: 5,  cap: 30, name: '论坛回复' },
    like:  { pts: 1,  cap: 10, name: '点赞' }
  };

  var GOALS = [
    { at: 100, k: 'relic', name: '天泪·虚空之刃', desc: '神器提前解锁' },
    { at: 300, k: 'title', name: '建筑师', desc: '论坛专属称号' }
  ];

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
  function add(tag, n) {
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
  function title() { var p = pts(); return p >= 300 ? '建筑师' : (p >= 100 ? '拓荒者' : '旅人'); }
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
        push();
      });
      mq.on('message', function (t, p) {
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
    rules: RULES, goals: GOALS, nextGoal: nextGoal, paint: paint, watchLive: watchLive
  };

  if (root.document) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
    else setTimeout(boot, 0);
  }
})(typeof self !== 'undefined' ? self : this);
