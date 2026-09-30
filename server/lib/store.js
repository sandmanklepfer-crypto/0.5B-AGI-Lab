'use strict';
/*
 * 订单存储（可插拔，全部 async）
 *
 *   local  —— 写服务器本地 JSON 文件（自有服务器 / 挂载了持久盘的场景）
 *   github —— 写你 GitHub 仓库里的一个文件（免费 PaaS 磁盘会清空时用它）
 *
 * 两者接口完全一致，切换只改 .env 里的 STORAGE。
 */

/* ============================================================
 *  本地文件存储
 * ============================================================ */
function createLocalStore(file) {
  const fs = require('fs');
  const path = require('path');
  const dir = path.dirname(file);

  let data = { orders: {} };
  try {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    if (fs.existsSync(file)) data = JSON.parse(fs.readFileSync(file, 'utf8') || '{"orders":{}}');
  } catch (e) { console.warn('[store] 读取失败，重建：' + e.message); }
  if (!data.orders) data.orders = {};

  function persist() {
    const tmp = file + '.tmp';
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2));
    fs.renameSync(tmp, file);          // 原子替换，避免写一半断电
  }

  return {
    kind: 'local',
    async load() { return data; },
    async create(order) { data.orders[order.outTradeNo] = order; persist(); return order; },
    async get(no) { return data.orders[no] || null; },
    async update(no, patch) {
      const cur = data.orders[no];
      if (!cur) return null;
      Object.assign(cur, patch, { updatedAt: Date.now() });
      persist();
      return cur;
    },
    async list() {
      return Object.values(data.orders).sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
    },
  };
}

/* ============================================================
 *  GitHub 仓库存储（免费 PaaS 用，重启不丢单）
 * ============================================================ */
function createGitHubStore(opts) {
  const https = require('https');
  const { token, owner, repo, file: filePath, branch } = opts;

  let cache = null;      // { orders: {} }
  let sha = null;        // 文件当前 sha
  let queue = Promise.resolve();

  function api(method, path, body) {
    const raw = body ? JSON.stringify(body) : '';
    const headers = {
      'Authorization': 'Bearer ' + token,
      'Accept': 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'luhuo-pay/1.0',
    };
    if (raw) { headers['Content-Type'] = 'application/json'; headers['Content-Length'] = Buffer.byteLength(raw); }
    return new Promise((resolve, reject) => {
      const req = https.request({ host: 'api.github.com', method, path, headers }, res => {
        let buf = '';
        res.on('data', c => buf += c);
        res.on('end', () => {
          let d = null;
          try { d = buf ? JSON.parse(buf) : null; } catch (e) { d = { raw: buf }; }
          if (res.statusCode >= 200 && res.statusCode < 300) resolve(d);
          else reject(Object.assign(new Error((d && d.message) || ('HTTP ' + res.statusCode)), { status: res.statusCode, data: d }));
        });
      });
      req.on('error', reject);
      if (raw) req.write(raw);
      req.end();
    });
  }

  async function load() {
    if (cache) return cache;
    try {
      const d = await api('GET', `/repos/${owner}/${repo}/contents/${filePath}?ref=${branch}&t=${Date.now()}`);
      sha = d.sha;
      let text = '';
      if (d.encoding === 'base64' && d.content) {
        text = Buffer.from(String(d.content).replace(/\s/g, ''), 'base64').toString('utf8');
      } else if (d.download_url) {
        text = await new Promise((res, rej) => https.get(d.download_url, r => { let b = ''; r.on('data', c => b += c); r.on('end', () => res(b)); }).on('error', rej));
      }
      cache = JSON.parse(text || '{"orders":{}}');
    } catch (e) {
      if (e.status === 404) { cache = { orders: {} }; sha = null; }   // 文件还不存在，第一次写会自动创建
      else throw e;
    }
    if (!cache.orders) cache.orders = {};
    return cache;
  }

  async function flush(message) {
    const content = Buffer.from(JSON.stringify(cache, null, 2)).toString('base64');
    for (let attempt = 0; attempt < 3; attempt++) {
      const body = { message: message || ('orders ' + new Date().toISOString()), content, branch };
      if (sha) body.sha = sha;
      try {
        const r = await api('PUT', `/repos/${owner}/${repo}/contents/${filePath}`, body);
        sha = r && r.content && r.content.sha;
        return true;
      } catch (e) {
        if (e.status === 409 || e.status === 422) {
          // sha 冲突：别人（或上一次重试）改过，重新拉一次再写
          const raw = Buffer.from(JSON.parse(JSON.stringify(content)), 'base64');
          try {
            const cur = await api('GET', `/repos/${owner}/${repo}/contents/${filePath}?ref=${branch}&t=${Date.now()}`);
            sha = cur.sha;
            const remote = JSON.parse(Buffer.from(String(cur.content).replace(/\s/g, ''), 'base64').toString('utf8'));
            if (remote && remote.orders) {
              // 合并：远端已有的 + 本地新增的（本地为准）
              cache.orders = Object.assign({}, remote.orders, cache.orders);
            }
          } catch (e2) { /* 下一轮重试 */ }
          await new Promise(r => setTimeout(r, 300 * (attempt + 1)));
          continue;
        }
        throw e;
      }
    }
    return false;
  }

  // 串行化写操作，避免并发冲突
  function serial(fn) {
    const next = queue.then(fn, fn);
    queue = next.catch(() => {});
    return next;
  }

  return {
    kind: 'github',
    async load() { return serial(() => load()); },
    async create(order) {
      return serial(async () => { await load(); cache.orders[order.outTradeNo] = order; await flush('新建订单 ' + order.outTradeNo); return order; });
    },
    async get(no) { return serial(async () => { await load(); return cache.orders[no] || null; }); },
    async update(no, patch) {
      return serial(async () => {
        await load();
        const cur = cache.orders[no];
        if (!cur) return null;
        Object.assign(cur, patch, { updatedAt: Date.now() });
        await flush('更新订单 ' + no + ' → ' + (patch.status || ''));
        return cur;
      });
    },
    async list() {
      return serial(async () => {
        await load();
        return Object.values(cache.orders).sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
      });
    },
  };
}

/* ============================================================
 *  工厂
 * ============================================================ */
function createStore(cfg) {
  if (String(cfg.storage || 'local').toLowerCase() === 'github') {
    if (!cfg.ghToken || !cfg.ghOwner || !cfg.ghRepo) {
      console.warn('[store] STORAGE=github 但 GH_TOKEN / GH_OWNER / GH_REPO 没配全，回退到本地文件存储');
    } else {
      console.log('[store] 订单存储：GitHub 仓库 ' + cfg.ghOwner + '/' + cfg.ghRepo + ' → ' + cfg.ghFile);
      return createGitHubStore({
        token: cfg.ghToken, owner: cfg.ghOwner, repo: cfg.ghRepo,
        file: cfg.ghFile, branch: cfg.ghBranch,
      });
    }
  }
  console.log('[store] 订单存储：本地文件');
  return createLocalStore(cfg.ordersFile);
}

module.exports = { createStore, createLocalStore, createGitHubStore };
