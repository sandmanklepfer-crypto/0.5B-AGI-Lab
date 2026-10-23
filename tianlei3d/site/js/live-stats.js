/* ============================================================================
 *  site/js/live-stats.js —— 官网「世界数据」板块
 *  --------------------------------------------------------------------------
 *  数据源：tianlei3d/stats/history.json + stats/<今天>.json（每天自动归档）
 *  展示：累计真人 / 今日 / 今日新面孔 / 已记录天数
 *        近 14 天柱状趋势、今日城市分布、最近 12 位访客（昵称+地区）
 *
 *  隐私原则（重要）
 *   · 只显示昵称 + 地区，**绝不输出 IP**（即使 JSON 里有）
 *   · 机房/代理 IP 的访问标为 suspect，不进任何公开数字
 *   · 昵称留空显示「神秘旅人」，不显示 uid
 * ========================================================================== */
(function () {
  'use strict';

  var $ = function (s) { return document.querySelector(s); };
  if (!$('#stChart')) return;                 // 页面上没有这块就什么都不做

  var CACHE = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function pad(n) { return n < 10 ? '0' + n : n; }
  function dayStr(d) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }

  /* 给每个昵称配一个稳定的表情头像（同一个名字永远同一个） */
  var FACES = ['🌙', '⚡', '🦊', '🌸', '🗡', '🔮', '🌧', '🏮', '🐉', '⭐', '🎴', '🌊', '🔥', '🍃', '🪐', '🕯'];
  function face(name) {
    var h = 0, s = String(name || 'x');
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return FACES[h % FACES.length];
  }

  /* 把 "中国 广东 深圳" 压成 "广东·深圳"，太长就只留城市 */
  function shortRegion(geo) {
    if (!geo) return '未知';
    var parts = geo.trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '未知';
    if (parts.length === 1) return parts[0];
    var city = parts[parts.length - 1];
    var prov = parts[parts.length - 2] || '';
    // 去掉"省/市/区"后缀，读起来更干净：江西省·南昌市 → 江西·南昌
    var trim = function (x) { return String(x || '').replace(/[省市]$/, '').replace(/區$/, ''); };
    var out = (prov && prov !== city) ? (trim(prov) + '·' + trim(city)) : trim(city);
    return out.replace(/^中國|^中華人民共和國|^中国\s*/, '').slice(0, 14);
  }

  function renderHead(h) {
    var daily = h.daily || {};
    var today = dayStr(new Date());
    var t = daily[today] || null;
    var sum = h.summary || {};

    var el;
    if ((el = $('#stAll'))) el.textContent = sum.allReal || 0;
    if ((el = $('#stToday'))) el.textContent = t ? t.real : 0;
    if ((el = $('#stNew'))) el.textContent = t ? t.new : 0;
    if ((el = $('#stDays'))) el.textContent = sum.days || 0;
  }

  function renderChart(h) {
    var box = $('#stChart');
    var daily = h.daily || {};
    var today = dayStr(new Date());
    var days = Object.keys(daily).sort().slice(-14);
    if (!days.length) { box.innerHTML = '<div class="st-empty">还没有数据<br>第一位访客出现后就会显示</div>'; return; }

    var max = 1;
    days.forEach(function (d) { max = Math.max(max, daily[d].real || 0); });

    box.innerHTML = days.map(function (d) {
      var v = daily[d].real || 0;
      var hh = Math.max(3, Math.round(v / max * 118));
      return '<div class="b' + (d === today ? ' today' : '') + '" title="' + d + '：' + v + ' 人">' +
        '<div class="v">' + v + '</div>' +
        '<div class="bar" style="height:' + hh + 'px"></div>' +
        '<div class="d">' + d.slice(5) + '</div></div>';
    }).join('');
  }

  function renderRegions(doc) {
    var box = $('#stRegion');
    if (!box) return;
    var regs = (doc && doc.regions) || {};
    var ks = Object.keys(regs).sort(function (a, b) { return regs[b] - regs[a]; }).slice(0, 7);
    if (!ks.length) { box.innerHTML = '<div class="st-empty">今天还没有真人访客<br>来当第一个</div>'; return; }
    var mx = regs[ks[0]] || 1;
    box.innerHTML = ks.map(function (k) {
      return '<div class="st-reg">' +
        '<span class="name" title="' + esc(k) + '">' + esc(shortRegion(k)) + '</span>' +
        '<span class="track"><i style="width:' + Math.max(6, regs[k] / mx * 100) + '%"></i></span>' +
        '<span class="num">' + regs[k] + '</span></div>';
    }).join('');
  }

  function renderWall(doc) {
    var box = $('#stWall');
    if (!box) return;
    var vs = ((doc && doc.visitors) || []).filter(function (x) { return !x.suspect; }).slice(0, 12);
    if (!vs.length) { box.innerHTML = '<div class="st-empty">今天还没有人来过</div>'; return; }
    box.innerHTML = vs.map(function (x) {
      var nm = (x.name || '').trim() || '神秘旅人';
      return '<div class="st-av' + (x.isNew ? ' new' : '') + '" title="' + esc(nm) + '">' +
        '<span class="face">' + face(nm) + '</span>' +
        '<span class="info"><span class="nm">' + esc(nm) + '</span>' +
        '<span class="rg">' + esc(shortRegion(x.geo)) + '</span></span></div>';
    }).join('');
  }

  function fail(msg) {
    ['#stChart', '#stRegion', '#stWall'].forEach(function (s) {
      var e = $(s);
      if (e) e.innerHTML = '<div class="st-empty">' + esc(msg) + '</div>';
    });
  }

  function loadDay(today) {
    return fetch('../stats/' + today + '.json', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('no day file'); return r.json(); })
      .catch(function () { return null; });
  }

  fetch('../stats/history.json', { cache: 'no-store' })
    .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function (h) {
      CACHE = h;
      renderHead(h);
      renderChart(h);
      var today = dayStr(new Date());
      return loadDay(today).then(function (doc) {
        // 今天的快照可能还没生成 → 退而用 history 里的当日汇总画个最小视图
        renderRegions(doc);
        renderWall(doc);
        if (!doc) {
          var d = (h.daily || {})[today];
          if (d) {
            var e = $('#stRegion');
            if (e) e.innerHTML = '<div class="st-empty">今天有 ' + d.real + ' 位真人来访<br>' +
              '<span style="font-size:11.5px">详细地区与昵称将在今晚归档后显示</span></div>';
            var w = $('#stWall');
            if (w) w.innerHTML = '<div class="st-empty">今晚 23:40 归档后这里会出现今天的旅人</div>';
          }
        }
      });
    })
    .catch(function (e) {
      fail('数据读取失败：' + (e.message || e) + '（每日归档可能还没跑）');
    });
})();
