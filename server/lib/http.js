'use strict';
/* 零依赖 HTTP 小工具：读 body / 响应 / 静态文件 */
const fs = require('fs');
const path = require('path');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.gif': 'image/gif', '.webp': 'image/webp', '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon', '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
};

function readBody(req, limit = 256 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0; const chunks = [];
    req.on('data', c => {
      size += c.length;
      if (size > limit) { reject(new Error('请求体过大')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

async function readJson(req) {
  const raw = await readBody(req);
  if (!raw) return {};
  try { return JSON.parse(raw); } catch (e) { throw new Error('JSON 格式错误'); }
}

function json(res, code, obj, extraHeaders) {
  const body = JSON.stringify(obj);
  res.writeHead(code, Object.assign({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': '*',
  }, extraHeaders || {}));
  res.end(body);
}

function text(res, code, body, type) {
  res.writeHead(code, { 'Content-Type': type || 'text/plain; charset=utf-8' });
  res.end(body);
}

/* 解析路由：支持 /a/:id/b */
function match(pattern, pathname) {
  const p = pattern.split('/').filter(Boolean);
  const u = pathname.split('/').filter(Boolean);
  if (p.length !== u.length) return null;
  const params = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(':')) params[p[i].slice(1)] = decodeURIComponent(u[i]);
    else if (p[i] !== u[i]) return null;
  }
  return params;
}

const DENY = /(^|\/)(\.env|\.git|server|node_modules)(\/|$)/;

function serveStatic(root, urlPath, res) {
  let rel = decodeURIComponent(urlPath.split('?')[0]);
  if (rel.endsWith('/')) rel += 'index.html';
  if (DENY.test(rel)) { text(res, 403, 'Forbidden'); return true; }
  const file = path.join(root, path.normalize(rel).replace(/^(\.\.[\/\\])+/, ''));
  if (!file.startsWith(root)) { text(res, 403, 'Forbidden'); return true; }
  let st;
  try { st = fs.statSync(file); } catch (e) { return false; }
  if (st.isDirectory()) return serveStatic(root, rel + '/index.html', res);
  const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
  res.writeHead(200, {
    'Content-Type': type,
    'Content-Length': st.size,
    'Cache-Control': file.endsWith('.html') ? 'no-cache' : 'public, max-age=300',
  });
  fs.createReadStream(file).pipe(res);
  return true;
}

module.exports = { readBody, readJson, json, text, match, serveStatic, MIME };
