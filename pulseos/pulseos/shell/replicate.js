'use strict';
/* ==========================================================================
 *  replicate.js —— 状态复制（主从同步）
 *  --------------------------------------------------------------------------
 *  迁移解决「搬到别处」，复制解决「两边都有」。
 *
 *      迁移：A → B，A 没了           （一次性，所有权转移）
 *      复制：A 和 B 都有，A 主 B 从   （持续，读可分散）
 *
 *  ★ 复制比迁移难在哪
 *
 *    1. 顺序：状态是有因果的，n=5 必须排在 n=4 之后
 *       → 需要一个单调递增的版本号（这里用 uint32 seq）
 *
 *    2. 冲突：万一两边都写了（脑裂），谁赢？
 *       → 这里选择「主节点赢」：只允许主写，从只读。
 *         这不是通用方案，但它是【唯一能在不引入共识算法的前提下保证正确】的方案。
 *
 *    3. 落后：从节点掉线一段时间，回来时要补齐
 *       → 这里做「全量重传」（简单可靠）。
 *         真正的做法是增量日志，但那需要 WAL，工程量是 5 倍。
 *
 *  所以本模块的定位很明确：
 *      「单向主从 + 全量重传 + 主节点仲裁」
 *      能撑住「读分散、写集中」，不承诺多主。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { reqJson } = require('./remote');

/* ---------------------------- 版本向量 ---------------------------- */
/* 每个服务一个 seq（单调递增）+ 一个 leaderId。
   seq 只在主节点写成功时 +1。 */
class ReplicaSet {
  constructor(opts = {}) {
    this.service = opts.service;
    this.leader = opts.leader;            // { name, host, port }
    this.followers = opts.followers || [];// [{ name, host, port }]
    this.seq = 0;
    this.stats = { syncs: 0, failures: 0, lastSync: 0, lag: 0 };
    this.stateFile = opts.stateFile || '/tmp/replica-' + this.service + '.json';
    this._load();
  }

  _load() {
    try {
      const d = JSON.parse(fs.readFileSync(this.stateFile, 'utf8'));
      this.seq = d.seq || 0;
      this.stats = Object.assign(this.stats, d.stats || {});
    } catch (e) {}
  }
  _save() {
    try {
      fs.writeFileSync(this.stateFile, JSON.stringify({ seq: this.seq, stats: this.stats }));
    } catch (e) {}
  }

  /* 主节点写：成功后 seq+1，然后异步推给从节点 */
  async write(op, args = []) {
    const r = await reqJson(this.leader.host, this.leader.port, 'POST', '/api/pulse', {
      service: this.service, op, args,
    }, 10000);

    if (!r.ok) return { ok: false, error: r.error, seq: this.seq };

    this.seq++;
    this._save();
    return {
      ok: true,
      result: r.result === undefined ? null : r.result,
      seq: this.seq,
      leader: this.leader.name,
    };
  }

  /* 读：可指定从某节点读（从节点只读） */
  async read(op, args = [], opts = {}) {
    const node = opts.from
      ? (this.followers.find(f => f.name === opts.from) || this.leader)
      : this.leader;
    const r = await reqJson(node.host, node.port, 'POST', '/api/pulse', {
      service: this.service, op, args,
    }, 10000);
    return {
      ok: r.ok,
      result: r.result === undefined ? null : r.result,
      from: node.name,
      isLeader: node.name === this.leader.name,
    };
  }

  /* 同步：把主节点的完整状态推给所有从节点（全量重传） */
  async sync() {
    const t0 = Date.now();
    const report = { seq: this.seq, followers: [], ms: 0 };

    /* ① 从主节点取出完整状态 + 源码 */
    let dump;
    try {
      const exp = await reqJson(this.leader.host, this.leader.port,
        'GET', '/api/export/' + encodeURIComponent(this.service), undefined, 15000);
      if (!exp || !exp.ok) throw new Error('导出失败: ' + (exp && exp.error));
      const src = await reqJson(this.leader.host, this.leader.port,
        'GET', '/api/source/' + encodeURIComponent(this.service), undefined, 15000);
      if (!src || !src.ok) throw new Error('取源码失败: ' + (src && src.error));
      dump = { state: JSON.parse(exp.stateJson), source: src.source, boxBytes: exp.bytes };
    } catch (e) {
      this.stats.failures++;
      this._save();
      return { ok: false, error: '主节点不可读: ' + e.message, followers: [], ms: Date.now() - t0 };
    }

    /* ② 逐个推给从节点 */
    for (const f of this.followers) {
      try {
        const r = await reqJson(f.host, f.port, 'POST', '/api/restore', {
          service: this.service, source: dump.source, state: dump.state,
        }, 20000);
        if (!r || !r.ok) throw new Error(r && r.error || '未知');

        /* ③ 验证：从节点上的状态字节数对得上吗 */
        const st = await reqJson(f.host, f.port, 'GET', '/api/state', undefined, 8000);
        const svc = st && (st.services || []).find(s => s.name === this.service);
        const ok = svc && svc.stateBytes > 0;

        report.followers.push({
          node: f.name, ok,
          stateBytes: svc ? svc.stateBytes : 0,
          drift: svc && svc.stateBytes !== dump.boxBytes ? 'state-bytes-differ' : null,
        });
        if (ok) this.stats.syncs++;
      } catch (e) {
        report.followers.push({ node: f.name, ok: false, error: e.message });
        this.stats.failures++;
      }
    }

    report.ms = Date.now() - t0;
    report.ok = report.followers.every(f => f.ok);
    this.stats.lastSync = Date.now();
    this._save();
    return report;
  }

  /* 一致性检查：主从状态是否完全相同 */
  async verify() {
    const get = async (n) => {
      const st = await reqJson(n.host, n.port, 'GET', '/api/state', undefined, 8000).catch(() => null);
      const svc = st && (st.services || []).find(s => s.name === this.service);
      return svc ? svc.state : null;
    };
    const leaderState = await get(this.leader);
    const out = { leader: this.leader.name, leaderHasState: leaderState !== null, followers: [] };

    for (const f of this.followers) {
      const s = await get(f);
      out.followers.push({
        node: f.name,
        hasState: s !== null,
        identical: s !== null && leaderState !== null && s === leaderState,
      });
    }
    out.allConsistent = out.followers.every(f => f.identical);
    return out;
  }

  info() {
    return {
      service: this.service,
      leader: this.leader.name,
      followers: this.followers.map(f => f.name),
      seq: this.seq,
      ...this.stats,
    };
  }
}

module.exports = { ReplicaSet };
