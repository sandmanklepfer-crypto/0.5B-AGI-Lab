#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  server.js —— 聚合态 OS 的本地外壳服务
 *  --------------------------------------------------------------------------
 *  用最少的代码把「散落的微内核」聚合成一个能看见、能操作的系统。
 *
 *    GET  /                 控制台界面
 *    GET  /api/state        系统总览 + 每个服务的状态
 *    POST /api/pulse        { service, op, args } → 一次脉冲
 *    POST /api/compile      { src } → 编译 PulseScript，返回诊断 + 状态预估
 *    POST /api/deploy       { src } → 编译并注册为新服务
 *    DELETE /api/service/:n 卸载服务
 *    GET  /api/export/:n    导出状态箱（base64）
 *
 *  启动：node shell/server.js [--port 8899]
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const http = require('http');
const { AggregatedShell } = require('./kernel');
const ps = require('../lang/pulsescript');

const PORT = (() => {
  const i = process.argv.indexOf('--port');
  return i > 0 ? parseInt(process.argv[i + 1], 10) : 8899;
})();

const ROOT = path.join(__dirname, '..');
const STATE_DIR = process.env.PULSE_STATE_DIR || path.join(ROOT, 'state');
const EX_DIR = path.join(ROOT, 'examples');

const sh = new AggregatedShell({ root: STATE_DIR });
const bootLog = [];

/* ---------- 源码持久化：每个服务存一份 .pulse，重启时重建 ---------- */
const SRC_DIR = path.join(STATE_DIR, '_src');

function persistSource(name, src) {
  try {
    fs.mkdirSync(SRC_DIR, { recursive: true });
    fs.writeFileSync(path.join(SRC_DIR, name + '.pulse'), src);
  } catch (e) {}
}

function loadPersistedSources() {
  if (!fs.existsSync(SRC_DIR)) return [];
  const out = [];
  for (const f of fs.readdirSync(SRC_DIR).filter(x => x.endsWith('.pulse'))) {
    try {
      out.push({ name: f.replace(/\.pulse$/, ''), src: fs.readFileSync(path.join(SRC_DIR, f), 'utf8') });
    } catch (e) {}
  }
  return out;
}

/* ---------- 启动：先恢复持久化的，再装 examples/ ---------- */
function bootup() {
  /* ① 恢复之前部署过的服务 */
  for (const { name, src } of loadPersistedSources()) {
    try {
      const added = sh.registerAll(src);
      bootLog.push('恢复 ' + added.map(a => a.name).join(',') + '（持久化）');
    } catch (e) {
      bootLog.push('恢复失败 ' + name + ': ' + e.message.split('\n')[0]);
    }
  }

  /* ② 装 examples/（不覆盖已有的） */
  if (fs.existsSync(EX_DIR)) {
    for (const f of fs.readdirSync(EX_DIR).filter(x => x.endsWith('.pulse'))) {
      try {
        const src = fs.readFileSync(path.join(EX_DIR, f), 'utf8');
        const { ast } = ps.compile(src);
        const names = ast.services.map(s => s.name);
        const fresh = names.filter(n => !sh.kernels.has(n));
        if (!fresh.length) continue;
        const r = sh.register(src);
        bootLog.push('已装载 ' + r.name + '（' + f + '）');
      } catch (e) {
        bootLog.push('装载失败 ' + f + ': ' + e.message.split('\n')[0]);
      }
    }
  }
}
bootup();

/* ---------- 工具 ---------- */
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
};

function send(res, code, body, type = 'application/json; charset=utf-8') {
  res.writeHead(code, {
    'Content-Type': type,
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET,POST,DELETE,OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(body);
}
const json = (res, code, o) => send(res, code, JSON.stringify(o, null, 2));

function readBody(req) {
  return new Promise((resolve, reject) => {
    let n = 0;
    const chunks = [];
    req.on('data', d => {
      n += d.length;
      if (n > 1 << 20) { reject(new Error('请求体超过 1MB')); req.destroy(); return; }
      chunks.push(d);
    });
    req.on('end', () => {
      const t = Buffer.concat(chunks).toString('utf8');
      if (!t) return resolve({});
      try { resolve(JSON.parse(t)); } catch (e) { reject(new Error('JSON 解析失败')); }
    });
    req.on('error', reject);
  });
}

function serveStatic(res, rel) {
  const p = path.join(ROOT, rel);
  if (!p.startsWith(ROOT)) return send(res, 403, 'forbidden', 'text/plain');
  fs.readFile(p, (e, buf) => {
    if (e) return send(res, 404, 'not found: ' + rel, 'text/plain');
    send(res, 200, buf, MIME[path.extname(p)] || 'application/octet-stream');
  });
}

/* ---------- 路由 ---------- */
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const p = url.pathname;

  if (req.method === 'OPTIONS') return send(res, 204, '');

  try {
    /* 静态 */
    if (p === '/' || p === '/index.html') return serveStatic(res, 'shell/index.html');
    if (p.startsWith('/shell/') || p.startsWith('/css/') || p.startsWith('/lang/')) {
      return serveStatic(res, p.slice(1));
    }

    /* 总览 */
    if (p === '/api/state' && req.method === 'GET') {
      return json(res, 200, {
        system: sh.systemInfo(),
        services: sh.list(),
        causal: sh.causalLog.slice(-12).map(c => ({
          t: c.t, from: c.service + '.' + c.op,
          chain: c.trace.map(x => x.service + '.' + x.op),
          ms: +c.trace.reduce((a, x) => a + (x.ms || 0), 0).toFixed(3),
        })),
        boot: bootLog,
        lang: {
          keywords: ['service', 'state', 'on', 'let', 'set', 'append', 'return', 'emit', 'if', 'else'],
          types: ['int', 'str', 'list', 'map', 'bool'],
          builtins: Object.keys(ps.BUILTINS),
        },
      });
    }

    /* 脉冲 */
    if (p === '/api/pulse' && req.method === 'POST') {
      const b = await readBody(req);
      if (!b.service) return json(res, 400, { ok: false, error: '缺少 service' });
      const r = sh.call(b.service, b.op || 'ping', b.args || []);
      return json(res, 200, r);
    }

    /* 编译（只检查，不注册） */
    if (p === '/api/compile' && req.method === 'POST') {
      const b = await readBody(req);
      try {
        const { ast, diag } = ps.compile(b.src || '');
        const est = ast.services.map(s => {
          const st = ps.makeState(s);
          const size = ps.stateSize(st).raw;
          return {
            name: s.name,
            fields: s.state.length,
            handlers: s.handlers.map(h => h.op),
            initialBytes: size,
            verdict: size > 1024 ? '偏大' : size > 256 ? '可以' : '极佳',
          };
        });
        return json(res, 200, { ok: diag.errors.length === 0, errors: diag.errors, warnings: diag.warnings, services: est });
      } catch (e) {
        return json(res, 200, { ok: false, errors: [e.message] });
      }
    }

    /* 部署 */
    if (p === '/api/deploy' && req.method === 'POST') {
      const b = await readBody(req);
      try {
        const r = sh.register(b.src || '');
        persistSource(r.name, b.src || '');
        return json(res, 200, { ok: true, ...r });
      } catch (e) {
        return json(res, 200, { ok: false, error: e.message });
      }
    }

    /* 卸载 */
    if (p.startsWith('/api/service/') && req.method === 'DELETE') {
      const name = decodeURIComponent(p.slice('/api/service/'.length));
      sh.unregister(name);
      try { fs.unlinkSync(path.join(SRC_DIR, name + '.pulse')); } catch (e) {}
      return json(res, 200, { ok: true, removed: name });
    }

    /* 导出状态箱 */
    if (p.startsWith('/api/export/') && req.method === 'GET') {
      const name = decodeURIComponent(p.slice('/api/export/'.length));
      const k = sh.kernels.get(name);
      if (!k) return json(res, 404, { ok: false, error: '没有服务 ' + name });
      try {
        const buf = fs.readFileSync(k.statePath);
        return json(res, 200, {
          ok: true, service: name,
          bytes: buf.length,
          stateJson: JSON.stringify(k.state),
          base64: buf.toString('base64'),
        });
      } catch (e) {
        return json(res, 200, { ok: false, error: e.message });
      }
    }

    json(res, 404, { ok: false, error: '未知路由 ' + p });
  } catch (e) {
    json(res, 500, { ok: false, error: String(e.message) });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log('');
  console.log('  ◈ PulseOS 聚合态外壳');
  console.log('  ─────────────────────────────────────');
  for (const l of bootLog) console.log('  ' + l);
  console.log('  ─────────────────────────────────────');
  console.log('  http://127.0.0.1:' + PORT);
  console.log('  状态目录 ' + STATE_DIR);
  console.log('');
});
