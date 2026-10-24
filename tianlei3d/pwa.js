/* ============================================================================
 *  pwa.js —— 天泪纪元 · PWA 共用逻辑（游戏页 / 官网 / 论坛 都用这一份）
 *  --------------------------------------------------------------------------
 *  为什么单独抽出来
 *    第一版把逻辑内联在 index.html 里，结果：
 *      · 官网和论坛完全没有 PWA（用户在那里找不到"添加到桌面"）
 *      · 按钮藏在 ☰ 菜单第三层，没人找得到
 *      · 注册挂在 load 事件上，某些情况下永远不触发
 *
 *  这一版：
 *    · 注册提前到 DOMContentLoaded（不等 load，避免被慢资源卡住）
 *    · 除了菜单按钮，还会在页面底部弹一个可见的安装条
 *    · 提供 window.PWA.diagnose()，能当场查出"为什么装不了"
 *
 *  用法（在页面里）：
 *    <script src="pwa.js" data-sw="sw.js" data-scope="./" defer></script>
 *  可选 data-banner="0" 关掉底部安装条
 * ========================================================================== */
(function () {
  'use strict';

  var self = document.currentScript || (function () {
    var s = document.getElementsByTagName('script');
    for (var i = s.length - 1; i >= 0; i--) if (/pwa\.js/.test(s[i].src)) return s[i];
    return null;
  })();

  var SW_URL = (self && self.dataset && self.dataset.sw) || 'sw.js';
  var SCOPE = (self && self.dataset && self.dataset.scope) || './';
  var WANT_BANNER = !(self && self.dataset && self.dataset.banner === '0');

  var PWA = {
    deferred: null,
    registered: false,
    swError: null,
    installable: false,
    reason: ''
  };

  /* ---------------- 环境判定 ---------------- */
  function isStandalone() {
    return (window.matchMedia && (
      window.matchMedia('(display-mode: standalone)').matches ||
      window.matchMedia('(display-mode: fullscreen)').matches ||
      window.matchMedia('(display-mode: minimal-ui)').matches)) ||
      window.navigator.standalone === true;
  }
  function isIOS() {
    var ua = navigator.userAgent;
    return /iPad|iPhone|iPod/.test(ua) ||
      (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua));
  }
  function isWeChat() { return /MicroMessenger/i.test(navigator.userAgent); }
  function isQQ() { return /\sQQ\/|QQBrowser/i.test(navigator.userAgent); }
  function isFile() { return location.protocol === 'file:'; }
  function isSecure() {
    return location.protocol === 'https:' ||
      location.hostname === 'localhost' || location.hostname === '127.0.0.1';
  }

  /* ---------------- 为什么装不了（诊断） ---------------- */
  PWA.diagnose = function () {
    var out = [];
    out.push('协议: ' + location.protocol + (isSecure() ? ' ✅' : ' ❌ 需要 https'));
    out.push('SW 支持: ' + ('serviceWorker' in navigator ? '✅' : '❌'));
    out.push('SW 已注册: ' + (PWA.registered ? '✅' : '❌ ' + (PWA.swError || '')));
    out.push('已安装(独立窗口): ' + (isStandalone() ? '是' : '否'));
    out.push('installable: ' + (PWA.installable ? '✅' : '❌ ' + PWA.reason));
    out.push('微信内: ' + (isWeChat() ? '是（微信不支持安装，需用浏览器打开）' : '否'));
    out.push('iOS: ' + (isIOS() ? '是（用 Safari 分享→添加到主屏幕）' : '否'));
    return out.join('\n');
  };

  /* ---------------- 注册 Service Worker ---------------- */
  function registerSW() {
    if (!('serviceWorker' in navigator)) {
      PWA.reason = '浏览器不支持 Service Worker';
      return;
    }
    if (!isSecure()) {
      PWA.reason = '不是 https（PWA 必须 https）';
      return;
    }
    if (isFile()) {
      PWA.reason = 'file:// 协议下无法注册';
      return;
    }

    /* ★ 不等 load：某些页面资源慢会一直不触发 load，SW 就永远装不上 */
    navigator.serviceWorker.register(SW_URL, { scope: SCOPE }).then(function (reg) {
      PWA.registered = true;
      PWA.swReg = reg;

      reg.addEventListener('updatefound', function () {
        var nw = reg.installing; if (!nw) return;
        nw.addEventListener('statechange', function () {
          if (nw.state === 'installed' && navigator.serviceWorker.controller) {
            try { nw.postMessage('skip-waiting'); } catch (e) {}
          }
        });
      });
    }).catch(function (e) {
      PWA.swError = (e && e.message) || String(e);
      PWA.reason = 'SW 注册失败: ' + PWA.swError;
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', registerSW);
  } else {
    registerSW();
  }
  /* 兜底：再挂一次 load，防止上面那次因为时序错过 */
  window.addEventListener('load', function () { if (!PWA.registered) registerSW(); });

  /* ---------------- 安装事件 ---------------- */
  window.addEventListener('beforeinstallprompt', function (e) {
    e.preventDefault();
    PWA.deferred = e;
    PWA.installable = true;
    PWA.reason = '';
    showBanner(true);        /* true = 有原生安装框，按钮写"安装" */
    var b = document.getElementById('bInstall');
    if (b) { b.textContent = '📲 添加到桌面'; b.className = 'on'; }
  });

  window.addEventListener('appinstalled', function () {
    hideBanner();
    say('✅ 已安装到桌面', '以后从桌面图标打开，全屏无地址栏');
  });

  /* ---------------- 提示 ---------------- */
  function say(t, s, ms) {
    try { if (window.HUD && HUD.center) { HUD.center(t, s, ms || 4000); return; } } catch (e) {}
    try { if (window.toast) { window.toast(t); return; } } catch (e) {}
    try { console.log('[PWA]', t, s || ''); } catch (e) {}
  }

  /* ---------------- 安装动作 ---------------- */
  PWA.install = function () {
    if (PWA.deferred) {
      PWA.deferred.prompt();
      PWA.deferred.userChoice.then(function (r) {
        var ok = r && r.outcome === 'accepted';
        say(ok ? '✅ 已添加到桌面' : '已取消', ok ? '以后从桌面图标直接打开' : '', 3200);
        PWA.deferred = null;
        hideBanner();
      });
      return;
    }
    /* 没有原生安装框 → 弹出图文步骤面板（不是一闪而过的 toast） */
    showHelp();
  };

  /* ---------------- 帮助面板样式（注入，不用改各页 CSS）---------------- */
  function injectCSS() {
    if (document.getElementById('pwaCSS')) return;
    var st = document.createElement('style');
    st.id = 'pwaCSS';
    st.textContent = [
      '#pwaHelp{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center}',
      '#pwaHelp .ph-mask{position:absolute;inset:0;background:rgba(3,3,8,.82);backdrop-filter:blur(4px)}',
      '#pwaHelp .ph-box{position:relative;width:min(90vw,380px);max-height:82vh;overflow:auto;',
      '  background:rgba(16,12,32,.99);border:1px solid rgba(168,85,247,.55);border-radius:18px;',
      '  padding:20px;box-shadow:0 24px 80px rgba(0,0,0,.8);color:#ece7f7;',
      '  font-family:"Noto Sans SC",system-ui,-apple-system,sans-serif}',
      '#pwaHelp .ph-h{display:flex;justify-content:space-between;align-items:center;',
      '  font-size:16px;font-weight:800;margin-bottom:14px;color:#e9d5ff}',
      '#pwaHelp .ph-x{cursor:pointer;color:#a78bfa;font-size:17px;padding:0 6px}',
      '#pwaHelp .ph-li{font-size:14px;line-height:2.05;color:#ddd2f5}',
      '#pwaHelp .ph-li b{color:#ffd166}',
      '#pwaHelp .ph-note{margin-top:12px;padding:9px 12px;border-radius:10px;font-size:11.5px;line-height:1.8;',
      '  background:rgba(255,209,102,.1);border:1px solid rgba(255,209,102,.4);color:#ffe9b8}',
      '#pwaHelp .ph-diag{margin-top:12px;font-size:11.5px;color:#9b93b3}',
      '#pwaHelp .ph-ok{margin-top:16px;width:100%;padding:12px;border:0;border-radius:11px;cursor:pointer;',
      '  font-family:inherit;font-size:14.5px;font-weight:800;color:#fff;',
      '  background:linear-gradient(100deg,#a855f7,#22d3ee)}'
    ].join('');
    document.head.appendChild(st);
  }

  /* ---------------- 安装帮助面板 ---------------- */
  function helpSteps() {
    var ua = navigator.userAgent;
    if (isWeChat()) {
      return {
        title: '微信里装不了，先换浏览器',
        steps: [
          '1. 点右上角「···」',
          '2. 选「在浏览器打开」',
          '3. 在浏览器里再点「装到桌面」'
        ],
        note: '微信内置浏览器禁止安装 PWA，这是微信的限制'
      };
    }
    if (isIOS()) {
      return {
        title: 'iPhone / iPad 安装方法',
        steps: [
          '1. 必须用 <b>Safari</b> 打开（Chrome 不行）',
          '2. 点底部中间「分享」按钮 ⬆️',
          '3. 往下滑，选「添加到主屏幕」',
          '4. 右上角点「添加」'
        ],
        note: 'iOS 不支持自动弹安装框，只能手动添加'
      };
    }
    return {
      title: '安装到桌面',
      steps: [
        '1. 点浏览器右上角「⋮」或「≡」菜单',
        '2. 找「安装应用」/「添加到主屏幕」/「添加到桌面」',
        '3. 点确认',
        '',
        '<span style="opacity:.7">如果菜单里没有这一项，说明当前浏览器不支持，建议换 Chrome / Edge / 三星浏览器</span>'
      ],
      note: ''
    };
  }

  function showHelp() {
    if (document.getElementById('pwaHelp')) return;
    injectCSS();
    var h = helpSteps();
    var d = document.createElement('div');
    d.id = 'pwaHelp';
    d.innerHTML =
      '<div class="ph-mask"></div>' +
      '<div class="ph-box">' +
        '<div class="ph-h">📲 ' + h.title + '<span class="ph-x" id="phX">✕</span></div>' +
        '<div class="ph-body">' + h.steps.map(function (s) {
          return s ? '<div class="ph-li">' + s + '</div>' : '<div style="height:6px"></div>';
        }).join('') + '</div>' +
        (h.note ? '<div class="ph-note">' + h.note + '</div>' : '') +
        '<div class="ph-diag" id="phDiag">' +
          (PWA.registered ? '✅ 页面已就绪（可安装）' : '⚠️ Service Worker 未就绪，可能影响安装') +
        '</div>' +
        '<button class="ph-ok" id="phOk">知道了</button>' +
      '</div>';
    document.body.appendChild(d);

    function close() { if (d && d.parentNode) d.parentNode.removeChild(d); }
    var x = document.getElementById('phX'), ok = document.getElementById('phOk');
    var mask = d.querySelector('.ph-mask');
    if (x) x.onclick = close;
    if (ok) ok.onclick = close;
    if (mask) mask.onclick = close;
  }
  PWA.help = showHelp;

  /* ---------------- 底部安装条 ---------------- */
  var banner = null;
  /* native = 有 beforeinstallprompt（能弹原生框）
     ★ 关键：没有 native 事件时也要显示，改成"看安装方法" */
  function showBanner(native) {
    if (!WANT_BANNER || isStandalone() || banner) return;
    if (isFile()) return;
    try { if (sessionStorage && sessionStorage.getItem('pwa_banner_off') === '1') return; } catch (e) { }
    if (document.getElementById('pwaBanner')) return;

    var isN = !!native || !!PWA.deferred;
    banner = document.createElement('div');
    banner.id = 'pwaBanner';
    banner.innerHTML =
      '<span class="pb-ico">📲</span>' +
      '<span class="pb-txt">装到桌面，像 App 一样玩' +
      '<small>' + (isN ? '全屏 · 无地址栏 · 桌面图标' : '看这里 → 怎么装（安卓/iOS 不同）') + '</small></span>' +
      '<button class="pb-go" id="pbGo">' + (isN ? '安装' : '怎么装') + '</button>' +
      '<button class="pb-x" id="pbX" aria-label="关闭">✕</button>';
    document.body.appendChild(banner);

    var g = document.getElementById('pbGo');
    var x = document.getElementById('pbX');
    if (g) g.onclick = function () { PWA.install(); };
    if (x) x.onclick = function () {
      try { sessionStorage.setItem('pwa_banner_off', '1'); } catch (e) {}
      hideBanner();
    };
    setTimeout(function () { if (banner) banner.classList.add('on'); }, 900);
  }

  /* ★ 无条件在 2.5 秒后显示安装条。
     不管 beforeinstallprompt 有没有来，用户都得能看到入口。
     （以前只在事件里 showBanner()，事件不来就一片空白 —— 这就是"哪里都看不到"的原因） */
  function autoBanner() {
    if (isStandalone()) return;
    if (PWA.deferred) { showBanner(true); return; }
    showBanner(false);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(autoBanner, 2500); });
  } else {
    setTimeout(autoBanner, 2500);
  }
  function hideBanner() {
    if (!banner) return;
    banner.classList.remove('on');
    var b = banner; banner = null;
    setTimeout(function () { if (b && b.parentNode) b.parentNode.removeChild(b); }, 300);
  }

  /* ---------------- 菜单按钮兜底绑定 ---------------- */
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t && t.id === 'bInstall') { PWA.install(); }
  }, true);

  /* ---------------- 已安装则隐藏入口 ---------------- */
  function tidy() {
    if (isStandalone()) {
      var b = document.getElementById('bInstall');
      if (b) b.style.display = 'none';
      hideBanner();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tidy);
  else tidy();

  window.PWA = PWA;
})();
