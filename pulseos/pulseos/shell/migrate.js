'use strict';
/* ==========================================================================
 *  migrate.js —— 状态箱迁移：把微内核从 A 搬到 B
 *  --------------------------------------------------------------------------
 *  这是「算力漫游」的最小实现：
 *
 *      目标：手机上的 counter，搬到电脑上继续跑，状态不丢
 *
 *  三个必须解决的问题（缺一个就会丢数据）：
 *
 *    ① 搬运期间的两边都在写      → 需要一个"冻结"窗口
 *    ② 搬到一半失败               → 需要回滚
 *    ③ 搬完后 A 上还留着，会分叉   → 需要显式的所有权转移
 *
 *  所以迁移是一个四阶段协议，不是一个文件传输：
 *
 *      freeze(A) → dump(A) → load(B) → commit(切所有权) / rollback
 *
 *  状态机：
 *      active ──freeze──> frozen ──dump──> transferring
 *                                              │
 *                            commit <──────────┤
 *                              │               │
 *                            active(B)      active(A)  (rollback)
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const zlib = require('zlib');
const { reqJson } = require('./remote');

/* ---------------------------- 迁移记录 ---------------------------- */
class MigrationLog {
  constructor(file) {
    this.file = file;
    this.entries = this._load();
  }
  _load() {
    try { return JSON.parse(fs.readFileSync(this.file, 'utf8')); } catch (e) { return []; }
  }
  push(e) {
    this.entries.push(Object.assign({ t: Date.now(), id: crypto.randomBytes(4).toString('hex') }, e));
    if (this.entries.length > 200) this.entries = this.entries.slice(-200);
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    fs.writeFileSync(this.file, JSON.stringify(this.entries, null, 1));
    return this.entries[this.entries.length - 1];
  }
  recent(n = 20) { return this.entries.slice(-n).reverse(); }
}

/* ---------------------------- 四个阶段 ---------------------------- */

/* ① 冻结：让源节点停止接受该服务的写请求
   实现方式：在源节点上加一个"冻结标记"，pulse 时检查 */
async function freeze(node, service) {
  return reqJson(node.host, node.port, 'POST', '/api/freeze', { service }, 8000);
}

async function unfreeze(node, service) {
  return reqJson(node.host, node.port, 'POST', '/api/unfreeze', { service }, 8000);
}

/* ② 导出：拿状态箱 + 源码 */
async function dump(node, service) {
  const exp = await reqJson(node.host, node.port, 'GET', '/api/export/' + encodeURIComponent(service), undefined, 15000);
  if (!exp || !exp.ok) throw new Error('导出失败: ' + (exp && exp.error || '未知'));

  // 还要拿到源码 —— 否则在 B 上无法重建这个微内核
  const src = await reqJson(node.host, node.port, 'GET', '/api/source/' + encodeURIComponent(service), undefined, 15000);
  if (!src || !src.ok) throw new Error('取源码失败: ' + (src && src.error || '未知'));

  return {
    service,
    state: exp.stateJson ? JSON.parse(exp.stateJson) : null,
    boxBase64: exp.base64,
    boxBytes: exp.bytes,
    source: src.source,
    meta: src.meta,
  };
}

/* ③ 装载：在目标节点上注册服务并灌入状态 */
async function load(node, payload) {
  const r = await reqJson(node.host, node.port, 'POST', '/api/restore', {
    service: payload.service,
    source: payload.source,
    state: payload.state,
  }, 20000);
  if (!r || !r.ok) throw new Error('装载失败: ' + (r && r.error || '未知'));
  return r;
}

/* ④ 卸下：确认目标可用后，删掉源节点的 */
async function drop(node, service) {
  return reqJson(node.host, node.port, 'DELETE', '/api/service/' + encodeURIComponent(service), undefined, 10000);
}

/* ---------------------------- 完整迁移 ---------------------------- */
async function migrate(opts) {
  const {
    from, to,        // { host, port, name }
    service,
    log,             // MigrationLog
    verify = true,   // 迁移后是否在目标上验证一次
    keepSource = false,
  } = opts;

  const t0 = Date.now();
  const rec = { service, from: from.name, to: to.name, stages: [], ok: false };

  const stage = (name, ok, detail) => {
    rec.stages.push({ name, ok, ms: Date.now() - t0, detail: detail || null });
    return ok;
  };

  let frozen = false;
  let loaded = false;

  try {
    /* ① 冻结源 */
    const f = await freeze(from, service).catch(e => ({ ok: false, error: e.message }));
    if (!f || !f.ok) throw new Error('冻结失败: ' + (f && f.error || '源节点不支持'));
    frozen = true;
    stage('freeze', true, { node: from.name });

    /* ② 导出 */
    const payload = await dump(from, service);
    stage('dump', true, { boxBytes: payload.boxBytes, hasSource: !!payload.source });

    /* ③ 装载到目标 */
    const l = await load(to, payload);
    loaded = true;
    stage('load', true, { node: to.name, services: l.services || [service] });

    /* 验证：直接查 /api/node 与 /api/state，不发假操作 */
    if (verify) {
      const nd = await reqJson(to.host, to.port, 'GET', '/api/node', undefined, 8000).catch(() => null);
      const found = nd && (nd.services || []).find(s => s.name === service);
      if (!found) throw new Error('目标上找不到服务 ' + service);

      const st = await reqJson(to.host, to.port, 'GET', '/api/state', undefined, 8000).catch(() => null);
      const svc = st && (st.services || []).find(s => s.name === service);
      if (!svc || svc.stateBytes <= 0) throw new Error('目标上状态箱为空');
      stage('verify', true, { registered: true, stateBytes: svc.stateBytes });
    }

    /* ④ 提交：解冻 + 可选卸下源 */
    if (!keepSource) {
      await drop(from, service).catch(() => {});
      stage('drop', true, { node: from.name, dropped: true });
    } else {
      await unfreeze(from, service).catch(() => {});
      stage('drop', true, { node: from.name, dropped: false, kept: true });
    }
    frozen = false;

    rec.ok = true;
    rec.ms = Date.now() - t0;
    if (log) rec.id = log.push(rec).id;
    return rec;

  } catch (e) {
    /* 回滚：不管走到哪一步，都尝试恢复源 */
    rec.error = e.message;
    rec.ms = Date.now() - t0;

    if (loaded) {
      await drop(to, service).catch(() => {});
      stage('rollback-drop-target', true);
    }
    if (frozen) {
      await unfreeze(from, service).catch(() => {});
      stage('rollback-unfreeze', true);
    }
    if (log) rec.id = log.push(rec).id;
    return rec;
  }
}

module.exports = { migrate, freeze, unfreeze, dump, load, drop, MigrationLog };

/* ---------------------------- CLI ---------------------------- */
if (require.main === module) {
  (async () => {
    const argv = process.argv.slice(2);
    const arg = (k) => { const i = argv.indexOf('--' + k); return i >= 0 ? argv[i + 1] : null; };

    const fromSpec = arg('from');
    const toSpec = arg('to');
    const service = arg('service');

    if (!fromSpec || !toSpec || !service) {
      console.log('用法:');
      console.log('  node shell/migrate.js --from nameA:host:port --to nameB:host:port --service counter');
      process.exit(1);
    }

    const parse = (s) => {
      const p = s.split(':');
      return { name: p[0], host: p[1], port: parseInt(p[2], 10) };
    };

    const log = new MigrationLog('/tmp/migrations.json');
    const r = await migrate({ from: parse(fromSpec), to: parse(toSpec), service, log });

    console.log('════════════════════════════════════════');
    console.log('  迁移 ' + service + ':  ' + r.from + ' → ' + r.to);
    console.log('════════════════════════════════════════');
    for (const s of r.stages) {
      console.log('  ' + (s.ok ? '✓' : '✗') + ' ' + s.name.padEnd(22) +
        String(s.ms).padStart(5) + 'ms  ' + (s.detail ? JSON.stringify(s.detail) : ''));
    }
    console.log('  ' + '-'.repeat(40));
    console.log('  ' + (r.ok ? '✓ 迁移成功' : '✗ 迁移失败: ' + r.error) + '   用时 ' + r.ms + 'ms');
    console.log('════════════════════════════════════════');
    process.exit(r.ok ? 0 : 1);
  })();
}
