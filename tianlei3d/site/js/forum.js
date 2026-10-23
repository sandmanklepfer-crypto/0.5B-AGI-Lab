/* ==========================================================================
   天泪纪元 · 玩家社区（论坛）
   --------------------------------------------------------------------------
   通信：公共 MQTT(WSS)，用「retain 保留消息」当存储 —— 免注册、免服务器。
     zhz/tianlei/fps/world/forum/<帖子id>            帖子本体（retain）
     zhz/tianlei/fps/world/forum/<帖子id>/r/<回复id>  回复（retain）
     zhz/tianlei/fps/world/forum/<帖子id>/l/<用户id>  点赞（retain）
   → 谁进来订阅 forum/# 就能拉到全部帖子；换设备也在。
   ⚠️ 公开通道，请勿发布隐私信息（页面上也有提示）。
   ========================================================================== */
(function () {
  'use strict';

  var NS = 'zhz/tianlei/fps/world/', ROOT = NS + 'forum/';
  var LS = { nick: 'tl_forum_nick', uid: 'tl_forum_uid' };
  var $ = function (s) { return document.querySelector(s); };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  function rd(k, d) { try { var v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } }
  function wr(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
  function ago(ts) {
    var d = Date.now() - ts; if (d < 0) d = 0;
    var m = Math.floor(d / 60000);
    if (m < 1) return '刚刚';
    if (m < 60) return m + ' 分钟前';
    var h = Math.floor(m / 60); if (h < 24) return h + ' 小时前';
    var dd = Math.floor(h / 24); if (dd < 30) return dd + ' 天前';
    return new Date(ts).toLocaleDateString('zh-CN');
  }

  var uid = rd(LS.uid, '');
  if (!uid) { uid = 'u' + Math.random().toString(36).slice(2, 9); wr(LS.uid, uid); }
  var nick = rd(LS.nick, '');

  var posts = {},     // id -> {id, nick, uid, text, img, at}
      replies = {},   // pid -> { rid -> {…} }
      likes = {};     // pid -> { uid -> 1 }
  var seen = {}, sort = 'new', keyword = '';

  /* ---------------- 连接 ---------------- */
  var mq = null, online = false;

  function setStat(t, ok) {
    var el = $('#stat'); if (!el) return;
    el.innerHTML = '<span class="dot' + (ok ? ' on' : '') + '"></span>' + t;
  }

  function boot() {
    if (typeof MiniMqtt === 'undefined') { setStat('离线（MQTT 未加载）', false); render(); return; }
    mq = MiniMqtt.createClient({ clientId: 'tlforum' + uid.slice(1, 6) });
    mq.on('connect', function () {
      online = true; setStat('已连接 · 帖子实时同步', true);
      mq.subscribe(ROOT + '#');
    });
    mq.on('close', function () { online = false; setStat('重连中…', false); });
    mq.on('message', function (t, p) { onMsg(t, p); });
  }

  function onMsg(topic, payload) {
    var rel = topic.slice(ROOT.length);
    if (!rel) return;
    var parts = rel.split('/');
    var pid = parts[0];

    // 回复 / 点赞
    if (parts.length >= 3) {
      var kind = parts[1], kid = parts.slice(2).join('/');
      if (kind === 'r') {
        if (!payload) return;
        var r; try { r = JSON.parse(payload); } catch (e) { return; }
        if (!r || !r.uid) return;
        (replies[pid] = replies[pid] || {})[kid] = r;
      } else if (kind === 'l') {
        if (!likes[pid]) likes[pid] = {};
        if (payload) likes[pid][kid] = 1; else delete likes[pid][kid];
      }
      if (render._needed !== false) render();
      return;
    }

    // 帖子本体
    if (!payload) { delete posts[pid]; render(); return; }      // 空载荷 = 已删
    var o; try { o = JSON.parse(payload); } catch (e) { return; }
    if (!o || !o.uid) return;
    posts[pid] = o;
    render();
  }

  /* ---------------- 渲染 ---------------- */
  function countLikes(pid) { var L = likes[pid] || {}; return Object.keys(L).length; }
  function iLiked(pid) { var L = likes[pid] || {}; return !!L[uid]; }

  function render() {
    var box = $('#list'); if (!box) return;
    var arr = Object.keys(posts).map(function (k) { return posts[k]; });
    if (keyword) {
      var kw = keyword.toLowerCase();
      arr = arr.filter(function (p) { return (p.text || '').toLowerCase().indexOf(kw) >= 0 || (p.nick || '').toLowerCase().indexOf(kw) >= 0; });
    }
    if (sort === 'hot') {
      arr.sort(function (a, b) {
        var sa = countLikes(a.id) * 3 + Object.keys(replies[a.id] || {}).length;
        var sb = countLikes(b.id) * 3 + Object.keys(replies[b.id] || {}).length;
        return sb - sa || (b.at || 0) - (a.at || 0);
      });
    } else {
      arr.sort(function (a, b) { return (b.at || 0) - (a.at || 0); });
    }

    $('#pcount').textContent = Object.keys(posts).length;

    if (!arr.length) {
      box.innerHTML = '<div class="empty">' + (keyword ? '没找到相关的帖子' : '还没有人发帖<br>你可以抢个沙发 🛋') + '</div>';
      return;
    }

    box.innerHTML = arr.map(function (p) {
      var rs = Object.keys(replies[p.id] || {}).map(function (k) { return replies[p.id][k]; })
        .sort(function (a, b) { return (a.at || 0) - (b.at || 0); });
      var rhtml = rs.map(function (r) {
        return '<div class="reply"><div class="who">' + esc(r.nick || '旅人') + ' · ' + ago(r.at || 0) + '</div>' + esc(r.text || '') + '</div>';
      }).join('');
      return '' +
      '<div class="post" data-pid="' + p.id + '">' +
        '<div class="head">' +
          '<div class="av">' + esc((p.nick || '旅')[0]) + '</div>' +
          '<div class="meta"><b>' + esc(p.nick || '旅人') + (p.uid === uid ? ' <span style="color:#ffd166;font-size:11px">（我）</span>' : '') + '</b>' +
            ago(p.at || 0) + '</div>' +
        '</div>' +
        '<div class="body">' + esc(p.text || '') + (p.img ? '<img src="' + esc(p.img) + '" alt="">' : '') + '</div>' +
        '<div class="acts">' +
          '<span class="lk' + (iLiked(p.id) ? ' on' : '') + '" data-act="like">👍 ' + countLikes(p.id) + '</span>' +
          '<span data-act="reply">💬 ' + rs.length + ' 回复</span>' +
          (p.uid === uid ? '<span data-act="del" style="margin-left:auto;color:#f87171">删除</span>' : '') +
        '</div>' +
        (rhtml ? '<div style="margin-top:10px">' + rhtml + '</div>' : '') +
      '</div>';
    }).join('');
  }

  /* ---------------- 发布 ---------------- */
  function pub(topic, obj, retain) {
    if (!mq || !online) { toast('还没连上，稍等一下'); return false; }
    try { mq.publish(topic, obj === null ? '' : JSON.stringify(obj), !!retain); return true; }
    catch (e) { toast('发送失败'); return false; }
  }

  function needNick() {
    if (nick) return true;
    openName();
    toast('先起个名字吧');
    return false;
  }

  /* ★ 积分：发帖/回复/点赞真到账（rewards.js），没加载就当 0 */
  function award(tag) {
    try { return (window.TLReward && TLReward.add) ? TLReward.add(tag) : 0; } catch (e) { return 0; }
  }

  function post() {
    if (!needNick()) return;
    var ta = $('#text'), text = (ta.value || '').trim();
    if (!text) { toast('说点什么吧'); return; }
    if (text.length > 1200) { toast('太长了（1200 字以内）'); return; }
    var id = 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
    if (!pub(ROOT + id, { id: id, uid: uid, nick: nick, text: text, img: '', at: Date.now() }, true)) return;
    ta.value = '';
    var g = award('post');
    toast(g ? ('已发布 · 积分 +' + g) : '已发布');
  }

  function reply(pid, text) {
    if (!needNick()) return;
    text = (text || '').trim(); if (!text) return;
    var rid = 'r' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
    pub(ROOT + pid + '/r/' + rid, { uid: uid, nick: nick, text: text, at: Date.now() }, true);
    var g = award('reply');
    toast(g ? ('已回复 · 积分 +' + g) : '已回复');
  }

  function like(pid) {
    var mine = iLiked(pid);
    // 取消点赞 = 发空载荷 + retain（broker 会清掉这条）
    pub(ROOT + pid + '/l/' + uid, mine ? null : { at: Date.now() }, true);
    if (!mine) award('like');
  }

  function del(pid) {
    if (!confirm('确定删除这条帖子？')) return;
    pub(ROOT + pid, null, true);
  }

  /* ---------------- 昵称弹窗 ---------------- */
  function openName() {
    $('#mask').classList.add('on'); $('#dlgName').classList.add('on');
    setTimeout(function () { $('#nickIn').focus(); }, 200);
  }
  function closeName() { $('#mask').classList.remove('on'); $('#dlgName').classList.remove('on'); }
  function saveName() {
    var v = ($('#nickIn').value || '').trim();
    if (!v) { $('#nickErr').textContent = '起个名字吧'; return; }
    nick = v.slice(0, 12); wr(LS.nick, nick);
    $('#who').textContent = nick;
    closeName(); toast('欢迎，' + nick);
  }

  /* ---------------- toast ---------------- */
  var tt = null;
  function toast(m) {
    var el = $('#toast'); el.textContent = m; el.classList.add('on');
    clearTimeout(tt); tt = setTimeout(function () { el.classList.remove('on'); }, 2000);
  }

  /* ---------------- 事件 ---------------- */
  document.addEventListener('click', function (e) {
    var t = e.target, pid = t.closest ? (t.closest('.post') || {}).dataset : null;
    var post_ = t.closest && t.closest('.post');
    if (post_) pid = post_.dataset.pid;

    if (t.closest && t.closest('#btnPost')) { post(); return; }
    if (t.closest && t.closest('#btnName')) { openName(); return; }
    if (t.closest && t.closest('#nameOk')) { saveName(); return; }
    if (t.closest && t.closest('#nameCancel')) { closeName(); return; }
    if (t.closest && t.closest('#mask')) { closeName(); return; }
    if (t.id === 'sortNew') { sort = 'new'; t.classList.add('on'); $('#sortHot').classList.remove('on'); render(); return; }
    if (t.id === 'sortHot') { sort = 'hot'; t.classList.add('on'); $('#sortNew').classList.remove('on'); render(); return; }

    var act = t.dataset && t.dataset.act;
    if (act && pid) {
      if (act === 'like') like(pid);
      else if (act === 'del') del(pid);
      else if (act === 'reply') {
        if (!needNick()) return;
        var box = post_.querySelector('.replybox');
        if (box) { box.remove(); return; }
        box = document.createElement('div');
        box.className = 'replybox';
        box.style.cssText = 'margin-top:10px;display:flex;gap:8px';
        box.innerHTML = '<input placeholder="说点什么…" maxlength="300" style="flex:1;background:rgba(6,4,14,.9);border:1px solid var(--line);border-radius:10px;color:#ece7f7;padding:10px 12px;font-size:14px;outline:none;font-family:inherit"><button class="btn sm">回复</button>';
        post_.appendChild(box);
        var inp = box.querySelector('input'); inp.focus();
        box.querySelector('button').onclick = function () { reply(pid, inp.value); };
        inp.onkeydown = function (ev) { if (ev.key === 'Enter') reply(pid, inp.value); };
      }
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && document.activeElement === $('#text')) post();
  });
  document.addEventListener('input', function (e) {
    if (e.target.id === 'search') { keyword = e.target.value.trim(); render(); }
  });

  /* ---------------- 启动 ---------------- */
  if (nick) $('#who').textContent = nick;
  setStat('连接中…', false);
  boot();
  render();
})();
