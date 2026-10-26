#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  node.js —— 节点：一台设备上的微内核群
 *  --------------------------------------------------------------------------
 *  每个节点只知道自己有哪些微内核。它不知道别人在哪，也不需要知道。
 *  聚合（跨端）由上层 shell 负责。
 *
 *  用法：
 *    node shell/node.js --name phone  --port 8901 --dir ./state-phone
 *    node shell/node.js --name laptop --port 8902 --dir ./state-laptop
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const http = require('http');
const { AggregatedShell } = require('./kernel');
const ps = require('../lang/pulsescript');

const argv = process.argv.slice(2);
const arg = (k, d) => { const i = argv.indexOf('--' + k); return i > 0 ? argv[i + 1] : d; };

const NAME = arg('name', 'node-' + Math.random().toString(36).slice(2, 6));
const PORT = parseInt(arg('port', '8901'), 10);
const DIR = path.resolve(arg('dir', './state-' + NAME));
const SRC = arg('src', null);          // 可选：从 .pulse 文件加载

const sh = new AggregatedShell({ root: DIR });
const loaded = [];

if (SRC && fs.existsSync(SRC)) {
  try {
    const added = sh.registerAll(fs.readFileSync(SRC, 'utf8'));
    for (const a of added) loaded.push(a.name);
  } catch (e) {
    console.error('加载失败: ' + e.message);
    process.exit(1);
  }
}

const MIME = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8' };
const ROOT = path.join(__dirname, '..');

function send(res, code, body, type = 'application/json; charset=utf-8') {
  res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type' });
  res.end(body);
}
const json = (res, c, o) => send(res, c, JSON.stringify(o, null, 2));

function readBody(req) {
  return new Promise((res, rej) => {
    const c = []; let n = 0;
    req.on('data', d => { n += d.length; if (n > 1 << 20) { rej(new Error('太大')); req.destroy(); return; } c.push(d); });
    req.on('end', () => { const t = Buffer.concat(c).toString('utf8'); if (!t) return res({}); try { res(JSON.parse(t)); } catch (e) { rej(new Error('JSON 错误')); } });
    req.on('error', rej);
  });
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  const p = u.pathname;
  if (req.method === 'OPTIONS') return send(res, 204, '');

  try {
    if (p === '/' || p === '/index.html') return send(res, 200, fs.readFileSync(path.join(ROOT, 'shell', 'index.html')), MIME['.html']);
    if (p.startsWith('/shell/')) {
      const f = path.join(ROOT, p.slice(1));
      if (!f.startsWith(ROOT)) return send(res, 403, 'no');
      try { return send(res, 200, fs.readFileSync(f), MIME[path.extname(f)] || 'application/octet-stream'); }
      catch (e) { return send(res, 404, 'not found'); }
    }

    /* 节点身份 + 服务清单（这是"无穷微内核"能被发现的前提） */
    if (p === '/api/node') {
      return json(res, 200, {
        node: NAME, port: PORT, dir: DIR,
        services: sh.list().map(k => ({ name: k.name, handlers: k.handlers.map(h => h.op),
          stateBytes: k.stateBytes, pulses: k.pulses })),
        system: sh.systemInfo(),
        ts: Date.now(),
      });
    }

    if (p === '/api/state') {
      return json(res, 200, {
        node: NAME,
        system: sh.systemInfo(),
        services: sh.list(),
        causal: sh.causalLog.slice(-12).map(c => ({
          t: c.t, from: c.service + '.' + c.op,
          chain: c.trace.map(x => x.service + '.' + x.op),
          ms: +c.trace.reduce((a, x) => a + (x.ms || 0), 0).toFixed(3),
        })),
        boot: loaded.map(n => '已装载 ' + n),
      });
    }

    if (p === '/api/pulse' && req.method === 'POST') {
      const b = await readBody(req);
      const r = await sh.callAsync(b.service, b.op || 'ping', b.args || []);
      return json(res, 200, r);
    }

    if (p === '/api/compile' && req.method === 'POST') {
      const b = await readBody(req);
      try {
        const { ast, diag } = ps.compile(b.src || '');
        return json(res, 200, {
          ok: diag.errors.length === 0, errors: diag.errors, warnings: diag.warnings,
          services: ast.services.map(s => {
            const st = ps.makeState(s);
            const size = ps.stateSize(st).raw;
            return { name: s.name, handlers: s.handlers.map(h => h.op), initialBytes: size,
              verdict: size > 1024 ? '偏大' : size > 256 ? '可以' : '极佳' };
          }),
        });
      } catch (e) { return json(res, 200, { ok: false, errors: [e.message] }); }
    }

    if (p === '/api/deploy' && req.method === 'POST') {
      const b = await readBody(req);
      try {
        const added = sh.registerAll(b.src || '');
        return json(res, 200, { ok: true, services: added.map(a => a.name) });
      } catch (e) { return json(res, 200, { ok: false, error: e.message }); }
    }

    if (p.startsWith('/api/export/')) {
      const n = decodeURIComponent(p.slice('/api/export/'.length));
      const k = sh.kernels.get(n);
      if (!k) return json(res, 404, { ok: false, error: '没有 ' + n });
      try {
        const buf = fs.readFileSync(k.statePath);
        return json(res, 200, { ok: true, service: n, bytes: buf.length,
          stateJson: JSON.stringify(k.state), base64: buf.toString('base64') });
      } catch (e) { return json(res, 200, { ok: false, error: e.message }); }
    }

    json(res, 404, { ok: false, error: '未知 ' + p });
  } catch (e) { json(res, 500, { ok: false, error: String(e.message) }); }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('  ▣ 节点 ' + NAME + '  端口 ' + PORT);
  console.log('    微内核: ' + (loaded.join(', ') || '(无)'));
  console.log('    状态目录: ' + DIR);
});
