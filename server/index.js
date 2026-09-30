'use strict';
/* 启动入口：node server/index.js */
const http = require('http');
const path = require('path');
const { route } = require('./app');
const { serveStatic } = require('./lib/http');
const { cfg, summary, SHOP_ROOT } = require('./lib/config');

const server = http.createServer(async (req, res) => {
  const p = (req.url || '/').split('?')[0];

  // 1) 先走 API
  if (p.startsWith('/api/')) {
    try {
      const handled = await route(req, res);
      if (!handled) {
        res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: '接口不存在' }));
      }
    } catch (e) {
      console.error('[api] 500', e);
      if (!res.headersSent) {
        res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(JSON.stringify({ ok: false, error: e.message }));
      }
    }
    return;
  }

  // 2) 托管卤味网页（index.html / pay.html / css / js / img / data）
  const root = path.resolve(SHOP_ROOT);
  if (p === '/pay' || p === '/pay/') {
    if (serveStatic(root, '/pay.html', res)) return;
  }
  if (serveStatic(root, p, res)) return;

  res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end('<h1>404</h1><p>页面不存在，<a href="/">回首页</a></p>');
});

server.listen(cfg.port, () => {
  const s = summary();
  console.log('\n🍲 卤味小店 · 支付服务器已启动');
  console.log('   地址：http://localhost:' + cfg.port + '/');
  console.log('   模式：' + s.mode);
  console.log('   回调：' + s.notifyUrl);
  console.log('   商户号：' + s.mchid + '   私钥：' + (s.hasPrivateKey ? '已加载' : '缺失') + '   APIv3Key：' + s.apiV3Key);
  if (cfg.mock) console.log('   ⚠️  演示模式：不会真实扣款，用 /pay.html 上的「模拟支付成功」按钮测试回调链路');
  console.log('');
});
