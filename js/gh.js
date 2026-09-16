/* GitHub Contents API 封装：把 GitHub 仓库当成"后台数据库 + 服务器" */
window.GH = (function () {
  const KEY = 'lh_gh';
  const DEF = { owner: '', repo: '', branch: 'gh-pages', token: '', path: '' };

  const cfg = () => Object.assign({}, DEF, LH.LS.get(KEY, {}));
  const saveCfg = c => LH.LS.set(KEY, Object.assign(cfg(), c));
  const clearCfg = () => LH.LS.del(KEY);

  const b64enc = str => btoa(unescape(encodeURIComponent(str)));
  const b64dec = b => decodeURIComponent(escape(atob(String(b).replace(/\s/g, ''))));

  function ready() { const c = cfg(); return !!(c.owner && c.repo && c.token); }
  function fullPath(p) { const c = cfg(); return (c.path ? c.path.replace(/\/$/, '') + '/' : '') + p; }

  async function api(path, opts) {
    const c = cfg();
    opts = opts || {};
    const res = await fetch('https://api.github.com' + path, Object.assign({}, opts, {
      headers: Object.assign({
        'Authorization': 'Bearer ' + c.token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28'
      }, opts.headers || {})
    }));
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { raw: text }; }
    if (!res.ok) {
      const msg = (data && data.message) || ('HTTP ' + res.status);
      const err = new Error(msg);
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }

  async function testAuth() {
    const u = await api('/user');
    const c = cfg();
    if (c.owner && c.repo) {
      const r = await api('/repos/' + c.owner + '/' + c.repo);
      return { user: u.login, repo: r.full_name, private: r.private, perms: r.permissions };
    }
    return { user: u.login };
  }

  /* 读文件：返回 { sha, text, base64 } 或 null */
  async function getFile(path) {
    const c = cfg();
    try {
      const d = await api('/repos/' + c.owner + '/' + c.repo + '/contents/' + fullPath(path) + '?ref=' + encodeURIComponent(c.branch));
      return { sha: d.sha, base64: d.content, text: d.encoding === 'base64' ? b64dec(d.content) : d.content };
    } catch (e) {
      if (e.status === 404) return null;
      throw e;
    }
  }

  /* 写文件。contentB64 为 true 表示传的是 base64（图片） */
  async function putFile(path, content, message, contentB64) {
    const c = cfg();
    const p = fullPath(path);
    let sha = null;
    try {
      const cur = await getFile(path);
      if (cur) sha = cur.sha;
    } catch (e) { /* 忽略 */ }
    const body = {
      message: message || ('update ' + path),
      content: contentB64 ? content : b64enc(content),
      branch: c.branch
    };
    if (sha) body.sha = sha;
    return api('/repos/' + c.owner + '/' + c.repo + '/contents/' + p, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
  }

  /* 删除文件 */
  async function delFile(path, message) {
    const c = cfg();
    const cur = await getFile(path);
    if (!cur) return null;
    return api('/repos/' + c.owner + '/' + c.repo + '/contents/' + fullPath(path), {
      method: 'DELETE',
      body: JSON.stringify({ message: message || ('delete ' + path), sha: cur.sha, branch: c.branch })
    });
  }

  function decodeDataUrl(dataUrl) {
    const i = dataUrl.indexOf(',');
    return { base64: dataUrl.slice(i + 1), mime: dataUrl.slice(5, dataUrl.indexOf(';')) };
  }

  return { cfg, saveCfg, clearCfg, ready, testAuth, getFile, putFile, delFile, decodeDataUrl, api };
})();
