/* ============================================================================
 *  sw.js —— 天泪纪元 · PWA Service Worker
 *  --------------------------------------------------------------------------
 *  目标：让网页能"添加到桌面"，像 App 一样独立窗口打开、离线也能启动。
 *
 *  ★★★ 最重要的设计：绝不能把用户锁死在旧版本 ★★★
 *    静态站最常见的 PWA 事故，就是用 cache-first 缓存了 HTML/JS，
 *    结果更新后用户永远看到旧版（而且自己不知道）。
 *
 *  所以这里分两类策略：
 *
 *  ①  HTML / JS / CSS / JSON → **network-first**
 *       永远先请求网络，拿到就用新的并顺手更新缓存；
 *       只有断网时才回退到缓存。
 *
 *  ②  图片 / 音频 / 字体 / 3D 模型 → **cache-first**
 *       这些资源文件名带内容特征或很少变，缓存起来最划算。
 *
 *  ③  切网 / 新版本 → 自动清理旧缓存（见 activate）
 * ========================================================================== */
'use strict';

/* ★ 改版本号 = 强制清空旧缓存。每次发版如果改了资源结构，把这个 +1 */
var CACHE = 'tianlei-v1';
var CACHE_STATIC = 'tianlei-static-v1';

/* 预缓存：只放"启动必需 + 很小"的东西。
   ⚠️ 千万不要把 40MB 的 APK 或大图放进来，否则首次安装会卡很久 */
var PRECACHE = [
  './',
  './index.html',
  './manifest.webmanifest',
  './pwa-192.png',
  './pwa-512.png'
];

/* ---------------- 安装：预缓存核心文件 ---------------- */
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      // 用 addAll 会因单个失败整体失败，这里逐个来，容错
      return Promise.all(PRECACHE.map(function (u) {
        return c.add(new Request(u, { cache: 'reload' })).catch(function () { });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

/* ---------------- 激活：清掉旧版本缓存 ---------------- */
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k !== CACHE && k !== CACHE_STATIC) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

/* ---------------- 请求拦截 ---------------- */
self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;

  var url;
  try { url = new URL(req.url); } catch (err) { return; }

  /* 跨域（MQTT broker、IP 查询等）一律不拦，交给浏览器。
     拦了会破坏 WebSocket / 第三方请求，也容易踩 CORS 坑。 */
  if (url.origin !== self.location.origin) return;

  /* 下载的安装包、压缩包：直接走网络，不缓存（太大了） */
  if (/\.(apk|zip|mp4|webm)$/i.test(url.pathname)) return;

  var isDoc = req.mode === 'navigate' ||
    /\.(html|js|css|json|webmanifest)$/i.test(url.pathname) ||
    url.pathname.slice(-1) === '/';

  if (isDoc) {
    /* ① network-first：保证永远拿到最新版本 */
    e.respondWith(
      fetch(req).then(function (res) {
        if (res && res.ok) {
          var copy = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copy); }).catch(function () { });
        }
        return res;
      }).catch(function () {
        /* 断网：回退缓存；导航请求回退到 index.html，保证还能启动 */
        return caches.match(req).then(function (hit) {
          if (hit) return hit;
          if (req.mode === 'navigate') {
            return caches.match('./index.html').then(function (h2) {
              return h2 || new Response('离线中，请联网后再试', {
                status: 503,
                headers: { 'Content-Type': 'text/plain; charset=utf-8' }
              });
            });
          }
          return new Response('', { status: 504 });
        });
      })
    );
    return;
  }

  /* ② cache-first：图片/音频/字体/模型 */
  e.respondWith(
    caches.match(req).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.ok && res.status === 200) {
          var copy = res.clone();
          caches.open(CACHE_STATIC).then(function (c) { c.put(req, copy); }).catch(function () { });
        }
        return res;
      }).catch(function () {
        return new Response('', { status: 504 });
      });
    })
  );
});

/* ---------------- 允许页面主动要求跳过等待 ---------------- */
self.addEventListener('message', function (e) {
  if (e.data === 'skip-waiting') {
    self.skipWaiting();
  }
});
