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
    showBanner();
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

    /* 没有原生安装框 → 给对应平台的手动指引 */
    var msg;
    if (isWeChat()) {
      msg = '微信里不能安装。点右上角「···」→「在浏览器打开」，再用浏览器菜单「添加到主屏幕」';
    } else if (isIOS()) {
      msg = 'iPhone：点 Safari 底部「分享」按钮 →「添加到主屏幕」→ 右上角「添加」';
    } else if (!isSecure()) {
      msg = '当前不是 https 环境，无法安装';
    } else if (!PWA.registered) {
      msg = 'Service Worker 未就绪：' + (PWA.reason || '可能刚打开，请刷新一次再试');
    } else {
      msg = '点浏览器右上角菜单 →「安装应用 / 添加到主屏幕」';
    }
    say('📲 添加到桌面', msg, 8000);
  };

  /* ---------------- 底部安装条 ---------------- */
  var banner = null;
  function showBanner() {
    if (!WANT_BANNER || isStandalone() || banner) return;
    if (sessionStorage && sessionStorage.getItem('pwa_banner_off') === '1') return;

    banner = document.createElement('div');
    banner.id = 'pwaBanner';
    banner.innerHTML =
      '<span class="pb-ico">📲</span>' +
      '<span class="pb-txt">装到桌面，像 App 一样玩<small>全屏 · 无地址栏 · 桌面图标</small></span>' +
      '<button class="pb-go" id="pbGo">安装</button>' +
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
