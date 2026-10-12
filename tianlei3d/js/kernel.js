/* ==========================================================================
   天泪内核 TLKernel —— 把游戏"内核化"：所有按钮 + 画面都能用命令行驱动
   ==========================================================================
   设计来源：车控项目的「公网 MQTT 总线」（比 adb 稳定得多）：
     · 不依赖 adb / 端口 / USB，只要手机能上网
     · 固定 client_id + cleanSession=false → 持久会话，离线命令会补发
     · 分片传大数据（画面回传）
   沙箱侧用 tools/tl 与之对话，就像在 Linux 里敲命令。

   主题（频道 = 暗号，固定）：
     zhz/tl/hello               保留：内核汇报"我在这个 broker/这个页面"
     zhz/tl/<CH>/cmd            沙箱 → 手机   命令(JSON {id,cmd})
     zhz/tl/<CH>/res            手机 → 沙箱   结果(JSON {id,ok,text,data})
     zhz/tl/<CH>/shot           手机 → 沙箱   画面分片(JSON {id,n,part,b64})
     zhz/tl/<CH>/evt            手机 → 沙箱   日志流

   用法（沙箱）：
     node tools/tl.js ping
     node tools/tl.js ui                       # 列出页面上所有可点按钮
     node tools/tl.js click "3D 模式"          # 按文字点按钮（不用坐标！）
     node tools/tl.js open octo.html
     node tools/tl.js shot                     # 截图 → /workspace/shot.png
     node tools/tl.js eval "GameState.currentScene"
   ========================================================================== */
(function () {
  'use strict';
  if (window.TLKernel) return;                 // 只装一次

  var CHAN = 'tl2f7a9c';                       // 频道（与 tools/tl.js 一致）
  var NS   = 'zhz/tl/' + CHAN + '/';
  var HELLO = 'zhz/tl/hello';
  var BROKERS = [
    'wss://broker.hivemq.com:8884/mqtt',     // ★优先：与沙箱侧同名 broker（沙箱只能到 hivemq）
    'wss://broker.emqx.io:8084/mqtt',
    'wss://test.mosquitto.org:8081/mqtt',
  ];

  /* ====================== 内嵌极简 MQTT over WebSocket ======================
     （取自 js/mqtt.js，精简；★支持 cleanSession=false 持久会话） */
  function encStr(s) {
    var b = new TextEncoder().encode(s), o = new Uint8Array(b.length + 2);
    o[0] = b.length >> 8; o[1] = b.length & 255; o.set(b, 2); return o;
  }
  function encLen(n) { var o = []; do { var d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; o.push(d); } while (n > 0); return new Uint8Array(o); }
  function pkt(t, body) { var l = encLen(body.length), o = new Uint8Array(1 + l.length + body.length); o[0] = t; o.set(l, 1); o.set(body, 1 + l.length); return o; }
  function join(ps) { var n = 0, i; for (i = 0; i < ps.length; i++) n += ps[i].length; var o = new Uint8Array(n), p = 0; for (i = 0; i < ps.length; i++) { o.set(ps[i], p); p += ps[i].length; } return o; }

  function createMqtt(opts) {
    opts = opts || {};
    var clientId = opts.clientId, clean = opts.clean !== false;
    var brokers = opts.brokers || BROKERS;
    var bi = 0, ws = null, ready = false, closed = false, gen = 0;
    var keepTimer = null, retryTimer = null, attempts = 0, helloTimer = null;
    var subs = new Set(), handlers = { connect: [], message: [], close: [] };
    var state = { broker: '' };
    function emit(ev, a) { (handlers[ev] || []).forEach(function (f) { try { f(a); } catch (e) {} }); }
    function send(b) { if (ws && ws.readyState === 1) { try { ws.send(b); } catch (e) {} } }
    function msend(t, b) { send(pkt(t, b)); }

    function connect() {
      if (closed) return;
      if (ws) { try { ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null; ws.close(); } catch (e) {} }
      var myGen = ++gen;
      var url = brokers[bi % brokers.length]; state.broker = url;
      var sock;
      try { sock = new WebSocket(url, 'mqtt'); } catch (e) { return retry(); }
      ws = sock; sock.binaryType = 'arraybuffer';
      sock.onopen = function () {
        if (myGen !== gen) return;
        attempts = 0;
        // 连接标志：clean=0x00(持久) / 0x02(清除会话)；keepalive 60s
        var flags = clean ? 0x02 : 0x00;
        var vh = join([encStr('MQTT'), new Uint8Array([0x04, flags, 0x00, 0x3C])]);
        msend(0x10, join([vh, encStr(clientId)]));
      };
      sock.onmessage = function (e) { if (myGen === gen) onMqtt(new Uint8Array(e.data)); };
      sock.onerror = function () {};
      sock.onclose = function () { if (myGen !== gen) return; ready = false; stopKeep(); emit('close'); if (!closed) retry(); };
    }
    function retry() {
      if (closed) return;
      attempts++; if (attempts % 2 === 0) bi++;
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, Math.min(1000 * attempts, 8000));
    }
    function onMqtt(buf) {
      if (!buf.length) return;
      var type = buf[0] >> 4;
      if (type === 2) {                                   // CONNACK
        if (buf[3] !== 0) { try { ws.close(); } catch (e) {} return; }
        ready = true; attempts = 0; startKeep();
        subs.forEach(doSub); emit('connect', state.broker);
        return;
      }
      if (type === 9) return;                             // SUBACK
      if (type === 3) {                                   // PUBLISH
        var i = 2; while (buf[i - 1] & 0x80) i++;
        var tl = (buf[i] << 8) | buf[i + 1];
        var topic = new TextDecoder().decode(buf.slice(i + 2, i + 2 + tl));
        var msg = new TextDecoder().decode(buf.slice(i + 2 + tl));
        emit('message', { topic: topic, payload: msg });
        return;
      }
    }
    function startKeep() { stopKeep(); keepTimer = setInterval(function () { msend(0xC0, new Uint8Array(0)); }, 30000); }
    function stopKeep() { clearInterval(keepTimer); keepTimer = null; }
    function doSub(t) { msend(0x82, join([new Uint8Array([0x00, 0x01]), encStr(t), new Uint8Array([0x00])])); }
    function subscribe(t) { subs.add(t); if (ready) doSub(t); }
    function publish(t, text, retain) {
      if (!ready) return false;
      try { send(pkt(retain ? 0x31 : 0x30, join([encStr(t), new TextEncoder().encode(String(text))]))); return true; }
      catch (e) { return false; }
    }
    function on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); return api; }
    var api = {
      on: on, subscribe: subscribe, publish: publish,
      get connected() { return ready; }, get broker() { return state.broker; },
      end: function () { closed = true; gen++; clearTimeout(retryTimer); stopKeep(); try { msend(0xE0, new Uint8Array(0)); } catch (e) {} try { if (ws) { ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null; ws.close(); } } catch (e) {} ws = null; },
    };
    connect(); return api;
  }

  /* ============================== 内核本体 ============================== */
  var K = {
    chan: CHAN, ns: NS, connected: false, broker: '', page: location.pathname,
    mq: null, _subs: {}, _logOn: false, _shotTimer: null, _shotId: 0,
  };
  window.TLKernel = K;

  function publish(topic, obj, retain) { if (K.mq && K.connected) { try { K.mq.publish(topic, typeof obj === 'string' ? obj : JSON.stringify(obj), !!retain); } catch (e) {} } }
  function res(id, ok, text, data) { publish(NS + 'res', { id: id, ok: ok !== false, text: text || '', data: (data === undefined ? null : data), page: K.page, ts: Date.now() }); }
  function evt(text, data) { publish(NS + 'evt', { text: String(text), data: data || null, page: K.page, ts: Date.now() }); }
  function hello() { publish(HELLO, { chan: CHAN, url: K.broker, page: K.page, href: location.href, ts: Date.now() }, true); }  // ★retain：供沙箱发现

  function boot() {
    if (typeof TextEncoder === 'undefined' || typeof WebSocket === 'undefined') return;
    K.mq = createMqtt({ clientId: 'tlk-' + CHAN, clean: false });   // ★持久会话
    K.mq.on('connect', function (b) {
      K.connected = true; K.broker = b;
      K.mq.subscribe(NS + 'cmd');
      hello(); evt('kernel online', { href: location.href });
      clearInterval(helloTimer); helloTimer = setInterval(hello, 8000);
    });
    K.mq.on('close', function () { K.connected = false; });
    K.mq.on('message', function (m) {
      if (m.topic === NS + 'cmd') handle(m.payload);
    });
  }
  var helloTimer = null;

  /* ------------------------------ 画面捕获 ------------------------------ */
  function capture() {
    var cv = document.querySelector('canvas');
    if (!cv) return { err: '页面无 canvas（DOM 页）→ 用 adb screencap 截图' };
    if (cv.width <= 300 && cv.height <= 150) return { err: 'canvas 是默认空尺寸 ' + cv.width + 'x' + cv.height + '（DOM 页）→ 用 adb screencap' };
    try {
      // WebGL 需要 preserveDrawingBuffer，否则可能全黑（页面里已强制开启）
      return { url: cv.toDataURL('image/jpeg', 0.72), w: cv.width, h: cv.height };
    } catch (e) { return { err: 'toDataURL 失败: ' + e.message }; }
  }
  function sendShot(id) {
    var c = capture();
    if (!c || c.err) { res(id, false, (c && c.err) || 'capture failed'); return; }
    var b64 = c.url.split(',')[1] || '';
    var CH = 18000, n = Math.max(1, Math.ceil(b64.length / CH));
    for (var i = 0; i < n; i++) {
      publish(NS + 'shot', { id: id, n: n, part: i, w: c.w, h: c.h, b64: b64.slice(i * CH, (i + 1) * CH) });
    }
    publish(NS + 'shot', { id: id, n: n, done: true, w: c.w, h: c.h });
    res(id, true, 'shot ' + c.w + 'x' + c.h + ' ' + b64.length + 'B64Ch');
  }

  /* ------------------------------ 事件合成 ------------------------------ */
  function fireAt(x, y) {
    var el = document.elementFromPoint(x, y) || document.body;
    var opt = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, screenX: x, screenY: y, view: window, button: 0 };
    function mk(type) {
      try { if (type.indexOf('pointer') === 0 && typeof PointerEvent !== 'undefined') return new PointerEvent(type, Object.assign({ pointerId: 1, pointerType: 'touch', isPrimary: true }, opt)); } catch (e) {}
      return new MouseEvent(type, opt);
    }
    ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(function (t) {
      try { el.dispatchEvent(mk(t)); } catch (e) {}
    });
    return el;
  }
  function realClick(el) {
    // ★ 只触发一次！以前先 el.click() 又补发 dispatchEvent('click')，
    //    对「开关型」按钮等于点了两下 = 没变。现在统一走原生 click()。
    try { el.click(); return true; } catch (e) { }
    try { el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window })); return true; } catch (e) { }
    return false;
  }
  function clickBy(sel) {
    var el = null;
    try { el = document.querySelector(sel); } catch (e) {}
    if (!el) return null;
    realClick(el);
    return el;
  }
  function listUI() {
    var els = document.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"],.btn,.menu-item,li[onclick],[onclick]');
    var out = [];
    for (var i = 0; i < els.length; i++) {
      var el = els[i], r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      out.push({
        id: el.id || '', tag: el.tagName, text: (el.textContent || '').trim().slice(0, 24),
        x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2),
        w: Math.round(r.width), h: Math.round(r.height),
      });
    }
    return out;
  }
  function key(k) {
    function mk(type) { return new KeyboardEvent(type, { key: k, code: k, bubbles: true, cancelable: true, view: window, keyCode: (k.length === 1 ? k.toUpperCase().charCodeAt(0) : 0) }); }
    document.dispatchEvent(mk('keydown')); window.dispatchEvent(mk('keydown'));
    setTimeout(function () { document.dispatchEvent(mk('keyup')); window.dispatchEvent(mk('keyup')); }, 60);
  }

  /* ------------------------------ 命令分发 ------------------------------ */
  function handle(payload) {
    var m; try { m = JSON.parse(payload); } catch (e) { m = { id: '?', cmd: String(payload) }; }
    var id = m.id || '?';
    var line = String(m.cmd === undefined ? '' : m.cmd).trim();
    var parts = line.split(/\s+/);
    var c = (parts[0] || '').toLowerCase(), a = parts.slice(1);
    try {
      switch (c) {
        case '': case 'ping':
          return res(id, true, 'pong', { page: K.page, href: location.href, broker: K.broker, dpr: window.devicePixelRatio, res: [innerWidth, innerHeight] });

        case 'help':
          return res(id, true, 'ping|info|ui|text|shot|shotloop <fps|off>|tap <x> <y>|click <sel|文字>|key <k>|open <page>|back|reload|eval <js>|log on|off|state');

        case 'info': {
          var cv = document.querySelector('canvas');
          return res(id, true, 'info', {
            url: location.href, title: document.title, dpr: window.devicePixelRatio,
            view: [innerWidth, innerHeight], canvas: cv ? [cv.width, cv.height] : null,
            buttons: listUI().length, kernel: 'tlk-v1', broker: K.broker,
          });
        }

        case 'ui':
          return res(id, true, listUI().length + ' 个控件', listUI());

        case 'text': case 'dom': {
          var t = (document.body && document.body.innerText) ? document.body.innerText.replace(/\n{2,}/g, '\n').trim() : '';
          return res(id, true, '正文 ' + t.length + ' 字', t.slice(0, 4000));
        }

        case 'shot': case 'screenshot': case 'screencap':
          return sendShot(id);

        case 'shotloop': {
          var v = (a[0] || 'off').toLowerCase();
          clearInterval(K._shotTimer); K._shotTimer = null;
          if (v !== 'off' && v !== '0') {
            var fps = Math.max(0.2, Math.min(10, parseFloat(v) || 1));
            K._shotTimer = setInterval(function () { sendShot('loop' + (++K._shotId)); }, 1000 / fps);
          }
          return res(id, true, 'shotloop ' + v);
        }

        case 'tap': case 'touch': {
          var x = parseFloat(a[0]), y = parseFloat(a[1]);
          if (!isFinite(x) || !isFinite(y)) return res(id, false, 'tap 用法: tap <x> <y>');
          var el = fireAt(x, y);
          return res(id, true, 'tap ' + x + ',' + y + ' → ' + el.tagName + (el.id ? '#' + el.id : ''));
        }

        case 'click': {
          var arg = a.join(' ');
          if (!arg) return res(id, false, 'click 用法: click <#id|css|按钮文字>');
          var el2 = null;
          if (/^[#.\[]/.test(arg)) el2 = clickBy(arg);
          if (!el2) {                                   // 按文字找按钮
            var list = document.querySelectorAll('button,a,[role="button"],.hud button');
            for (var i = 0; i < list.length; i++) {
              var t = (list[i].textContent || '').trim();
              if (t === arg || t.indexOf(arg) >= 0) { el2 = list[i]; try { list[i].click(); } catch (e) {} break; }
            }
          }
          return res(id, !!el2, el2 ? ('clicked ' + (el2.id ? '#' + el2.id : '"' + (el2.textContent || '').trim().slice(0, 20) + '"')) : ('未找到控件: ' + arg));
        }

        case 'key': case 'press':
          if (!a[0]) return res(id, false, 'key 用法: key <键名>');
          key(a[0]); return res(id, true, 'key ' + a[0]);

        case 'open': case 'goto':
          if (!a[0]) return res(id, false, 'open 用法: open <page.html>');
          res(id, true, 'navigating → ' + a[0]);
          setTimeout(function () { location.href = a[0]; }, 120);
          return;

        case 'back':
          res(id, true, 'back'); setTimeout(function () { if (history.length > 1) history.back(); else location.href = 'index.html'; }, 120); return;

        case 'reload':
          res(id, true, 'reload'); setTimeout(function () { location.reload(); }, 120); return;

        case 'eval': {
          var js = line.slice(4).trim();
          if (!js) return res(id, false, 'eval 用法: eval <js>');
          var out = (0, eval)(js);                       // eslint-disable-line no-eval
          var ser; try { ser = JSON.parse(JSON.stringify(out === undefined ? null : out)); } catch (e) { ser = String(out); }
          return res(id, true, 'eval ok', ser);
        }

        case 'log':
          K._logOn = (a[0] !== 'off'); return res(id, true, 'log ' + (K._logOn ? 'on' : 'off'));

        case 'state': case 'debug': {
          if (window.DebugConsole && DebugConsole.handle) { DebugConsole.handle(line); return res(id, true, '→ DebugConsole'); }
          return res(id, true, 'no DebugConsole on this page', { page: K.page });
        }

        default:
          if (window.DebugConsole && DebugConsole.handle) { DebugConsole.handle(line); return res(id, true, '→ DebugConsole: ' + c); }
          return res(id, false, '未知命令: ' + c + '（用 help）');
      }
    } catch (e) {
      return res(id, false, '执行出错: ' + (e && e.message));
    }
  }

  /* ------------------------------ 日志桥 ------------------------------ */
  (function () {
    var origErr = console.error, origLog = console.log;
    console.error = function () { try { if (K._logOn) evt('ERROR ' + Array.prototype.map.call(arguments, String).join(' ')); } catch (e) {} return origErr.apply(console, arguments); };
    window.addEventListener('error', function (e) { try { evt('UNCAUGHT ' + (e.message || '') + ' @' + (e.filename || '').split('/').pop() + ':' + e.lineno); } catch (x) {} });
  })();

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
