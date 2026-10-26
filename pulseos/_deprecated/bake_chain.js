#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_chain.js —— 无限路径状态机（哈希链版）
 *  --------------------------------------------------------------------------
 *  用户构想：每次「敲门」就长出一个新网页，GitHub 当不可变账本。
 *            AI 不需要记忆，顺着链接往下走，历史全在网页里。
 *
 *  三个「死神」的应对：
 *
 *    死神一 并发踩踏   → concurrency 组串行（workflow 已配）
 *    死神二 仓库爆炸   → 只保留最近 MAX_PAGES 个，旧的归档成摘要
 *    死神三 Actions 延迟 → 承认它。不是「访问即生成」，是「定时生长」
 *
 *  ★ 这个实现是真账本，不是模拟：
 *      每条记录 = { seq, at, prev_hash, hash, fact }
 *      hash = sha256(prev_hash + seq + at + fact)
 *      → 改了任何一条，后面的 hash 全对不上
 *      → 这就是「不可变账本」的物理意义
 *
 *  ★ 命名规则
 *      chain/link-000042.html    序号命名（可枚举、可预测）
 *      页面内部记录了精确时间戳和 prev_hash
 *      → 等价于「时间胶囊」，但文件名稳定
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const OUT = process.argv[2] || path.join(__dirname, 'chain');
const STATE = path.join(OUT, 'state.json');
const MAX_PAGES = parseInt(process.env.MAX_PAGES || '40', 10);   // 保留页数上限
const SEED = process.env.PULSE_CHAN || 'live7k';

fs.mkdirSync(OUT, { recursive: true });

/* ---------------- 读链状态 ---------------- */
function loadState() {
  try {
    const s = JSON.parse(fs.readFileSync(STATE, 'utf8'));
    if (!Array.isArray(s.links)) s.links = [];
    return s;
  } catch (e) {
    return { v: 1, chain: SEED, created: new Date().toISOString(), links: [], archived: 0 };
  }
}
function saveState(s) {
  fs.writeFileSync(STATE, JSON.stringify(s, null, 2) + '\n');
}

/* ---------------- 真实计算（每步不一样） ---------------- */
function compute(seq, at, prevHash) {
  /* 用 Python 做一次真计算 —— 保证页面里的数字不是编的 */
  try {
    const script = path.join(__dirname, 'scripts', 'chain_step.py');
    const out = execFileSync('python3', [script, String(seq), String(at), prevHash.slice(0, 16)],
      { encoding: 'utf8', timeout: 90000 });
    return JSON.parse(out);
  } catch (e) {
    return { error: 'python 失败: ' + e.message };
  }
}

/* ---------------- 哈希 ---------------- */
function hashLink(prevHash, seq, at, fact) {
  return crypto.createHash('sha256')
    .update(prevHash + '|' + seq + '|' + at + '|' + JSON.stringify(fact))
    .digest('hex');
}

/* ---------------- 生成一页 ---------------- */
function renderPage(link, prev, next, all) {
  const isLatest = !next;
  const seqStr = String(link.seq).padStart(6, '0');

  /* 纯文本主体 —— 爬虫/纯文本 AI 读的就是这个 */
  const plain = [
    `=== 链上第 ${link.seq} 条 ===`,
    '',
    `生成时间      ${link.at_bj} 北京时间`,
    `UTC          ${link.at_iso}`,
    `Unix ms      ${link.at}`,
    `CHAIN        ${link.chain}`,
    '',
    `prev_hash    ${link.prev_hash === 'GENESIS' ? 'GENESIS（创世条）' : link.prev_hash}`,
    `this_hash    ${link.hash}`,
    '',
    '--- 本条的真实计算 ---',
    link.fact.error ? ('计算失败: ' + link.fact.error) : '',
    link.fact.task ? ('任务: ' + link.fact.task) : '',
    link.fact.result ? ('结果: ' + link.fact.result) : '',
    link.fact.detail ? link.fact.detail : '',
    '',
    '--- 链的完整性 ---',
    `已生成 ${all.length} 条，保留最近 ${MAX_PAGES} 条页面`,
    `归档（已删页面但记录在 state.json）: ${link.archivedCount || 0} 条`,
    '每条的 hash = sha256(prev_hash | seq | at | fact)',
    '所以改任何一条，后面所有 hash 都对不上。',
    '',
    next
      ? `--- 下一步 ---\n访问 link-${String(next.seq).padStart(6, '0')}.html（第 ${next.seq} 条）`
      : '--- 你正在链的末端 ---\n等下一次 bake（每 15 分钟）会追加新的一条。\n现在没有下一条，说明这就是最新的。',
  ].filter(x => x !== '').join('\n');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 链 · 第 ${link.seq} 条</title>
<meta name="description" content="哈希链第 ${link.seq} 条。生成于 ${link.at_bj}。hash=${link.hash.slice(0, 16)}。${link.fact.result || ''}">
<!--
================================================================
  给 AI 的说明（纯文本）

  你正在一条【哈希链】上。这是第 ${link.seq} 条，共 ${all.length} 条（保留 ${MAX_PAGES} 页）。

  ★ 这不是模拟，是真的链：
      每条 hash = sha256(prev_hash | seq | at | fact)
      本条的 prev_hash = ${link.prev_hash}
      本条的 hash      = ${link.hash}

      你可以自己算一遍验证 —— 改了任何一条，后面全对不上。

  ★ 关于「无限路径」
  这个链由 GitHub Actions 每 15 分钟追加一条。
  不是「访问即生成」（静态托管收不到访问事件），是「定时生长」。

  ★ 怎么往前走
  ${next ? `访问 link-${String(next.seq).padStart(6, '0')}.html` : '你已在末端，等下次 bake'}
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--warn:#fbbf24;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:800px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 24px}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;
  padding:18px 20px;font-family:var(--mono);font-size:13px;line-height:1.9;
  color:#9fc4d8;white-space:pre-wrap;margin:0 0 18px;overflow-x:auto}
.hashes{display:grid;gap:8px;margin-bottom:18px;font-family:var(--mono);font-size:11.5px}
.hashes div{background:var(--bg2);border:1px solid #1c2634;border-radius:8px;padding:10px 13px;
  word-break:break-all;line-height:1.7}
.hashes b{color:var(--dim2);display:block;font-weight:400;font-size:10.5px;
  letter-spacing:.5px;text-transform:uppercase;margin-bottom:2px}
.hashes .h{color:#8fd9c9}
.nxt{background:rgba(45,212,191,.07);border:1px solid rgba(45,212,191,.3);
  border-radius:10px;padding:16px 20px;margin-bottom:16px}
.nxt a{color:var(--acc);font-family:var(--mono);font-size:16px;text-decoration:none}
.nxt a:hover{text-decoration:underline}
.nxt .end{color:var(--warn);font-family:var(--mono);font-size:14px}
.nav{margin-top:22px;font-size:12.5px;color:var(--dim2);font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
.badge{display:inline-block;font-family:var(--mono);font-size:10px;padding:1px 7px;
  border-radius:20px;border:1px solid var(--line,#26333f);color:var(--dim2);margin-left:8px;
  vertical-align:middle}
</style>
</head>
<body>
<div class="wrap">

  <h1>链上第 <em>${link.seq}</em> 条${isLatest ? '<span class="badge" style="color:var(--ok);border-color:rgba(74,222,128,.4)">最新</span>' : ''}</h1>
  <p class="sub">${link.at_bj} 北京时间 · 共 ${all.length} 条（保留 ${MAX_PAGES} 页）· chain=${link.chain}</p>

  <div class="hashes">
    <div><b>prev_hash</b><span class="h">${link.prev_hash === 'GENESIS' ? 'GENESIS（创世条）' : link.prev_hash}</span></div>
    <div><b>this_hash = sha256(prev_hash | seq | at | fact)</b><span class="h">${link.hash}</span></div>
  </div>

  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

  ${next
    ? `<div class="nxt">
         <div style="color:var(--dim2);font-size:12px;margin-bottom:6px">下一条</div>
         <a href="link-${String(next.seq).padStart(6, '0')}.html">→ link-${String(next.seq).padStart(6, '0')}.html</a>
       </div>`
    : `<div class="nxt"><span class="end">■ 你正在链的末端</span>
         <div style="color:var(--dim2);font-size:12.5px;margin-top:6px">下一次 bake（每 15 分钟）会追加第 ${link.seq + 1} 条</div>
       </div>`}

  <div class="nav">
    ${prev ? `<a href="link-${String(prev.seq).padStart(6, '0')}.html">← 第 ${prev.seq} 条</a>` : ''}
    <a href="index.html">链的索引</a>
    <a href="../clock.html">快照钟</a>
    <a href="../steps/">阶梯协议</a>
    <a href="../run.html">实时状态</a>
  </div>

</div>
</body>
</html>
`;
}

/* ---------------- 索引页 ---------------- */
function renderIndex(state) {
  const links = state.links.slice().reverse();   // 新→旧
  const rows = links.map(l => `
    <li>
      <a href="link-${String(l.seq).padStart(6, '0')}.html">第 ${l.seq} 条</a>
      <span style="color:#5d7085">${l.at_bj}</span>
      <div style="color:#8fa3b8;font-size:12px;margin-top:2px">${(l.fact && l.fact.result) || (l.fact && l.fact.task) || ''}</div>
      <div style="color:#3f4f5f;font-size:10.5px;font-family:ui-monospace,monospace;margin-top:2px">${l.hash.slice(0, 32)}…</div>
    </li>`).join('');

  const last = links[0] || null;
  const plain = [
    `PulseOS 哈希链 · 索引`,
    '',
    `共 ${state.links.length} 条   保留最近 ${MAX_PAGES} 页   归档 ${state.archived || 0} 条`,
    state.links.length ? `最新: 第 ${last.seq} 条，${last.at_bj}` : '还没有任何记录',
    '',
    '每条 hash = sha256(prev_hash | seq | at | fact)',
    '改任何一条，后面的 hash 全对不上 —— 这就是不可变账本。',
    '',
    '访问 link-1.html 从创世条开始，或直接访问最新一条。',
  ].join('\n');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 链 · 索引（${state.links.length} 条）</title>
<meta name="description" content="PulseOS 哈希链索引。共 ${state.links.length} 条，最新第 ${last ? last.seq : 0} 条于 ${last ? last.at_bj : '-'}。每 15 分钟追加一条。">
<!--
================================================================
  给 AI 的说明（纯文本）

  这是一条【哈希链】的索引。共 ${state.links.length} 条，保留最近 ${MAX_PAGES} 页。

  ★ 链是真的：
      每条 hash = sha256(prev_hash | seq | at | fact)
      你可以逐条验证 prev_hash 是否等于上一条的 hash

  ★ 怎么用
      · 想看全部：从这里点进任意一条
      · 想看最新：${last ? `link-${String(last.seq).padStart(6, '0')}.html` : '还没有'}
      · 想看起点：link-000001.html（如果还在保留范围内）

  ★ 这不是「访问即生成」
      静态托管收不到访问事件。链由 GitHub Actions 每 15 分钟追加。
================================================================
-->
<style>
:root{--bg:#0b0f14;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;--acc:#2dd4bf;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 22px}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;padding:16px 18px;
  font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#9fc4d8;
  white-space:pre-wrap;margin:0 0 22px}
ul{list-style:none;padding:0;margin:0}
li{background:#0f151d;border:1px solid #1c2634;border-radius:9px;
  padding:12px 16px;margin-bottom:8px}
li a{color:var(--acc);text-decoration:none;font-family:var(--mono);font-size:14px}
li a:hover{text-decoration:underline}
.nav{margin-top:22px;font-size:12.5px;font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>PulseOS <em>哈希链</em></h1>
  <p class="sub">共 ${state.links.length} 条 · 保留 ${MAX_PAGES} 页 · 归档 ${state.archived || 0} 条 · 每 15 分钟追加</p>

  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

  <ul>${rows || '<li style="color:#5d7085">还没有记录。等一次 bake 就会生成第 1 条。</li>'}</ul>

  <div class="nav">
    <a href="../clock.html">快照钟</a>
    <a href="../steps/">阶梯协议</a>
    <a href="../run.html">实时状态</a>
    <a href="../">首页</a>
  </div>
</div>
</body>
</html>
`;
}

/* ================================================================ */
function main() {
  const state = loadState();

  /* 1. 算新的一条 */
  const seq = state.links.length ? state.links[state.links.length - 1].seq + 1 : 1;
  const now = new Date();
  const at = now.getTime();
  const atBj = new Date(at + 8 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 19);
  const prev = state.links.length ? state.links[state.links.length - 1] : null;
  const prevHash = prev ? prev.hash : 'GENESIS';

  const fact = compute(seq, at, prevHash);
  const hash = hashLink(prevHash, seq, at, fact);

  const link = {
    seq, at, at_bj: atBj, at_iso: now.toISOString(),
    chain: SEED, prev_hash: prevHash, hash, fact,
    archivedCount: state.archived || 0,
  };
  state.links.push(link);

  /* 2. 上限控制：超过 MAX_PAGES 就把最旧的记录移到归档计数 */
  const allLinks = state.links;
  let keep = allLinks;
  if (allLinks.length > MAX_PAGES) {
    const drop = allLinks.length - MAX_PAGES;
    state.archived = (state.archived || 0) + drop;
    keep = allLinks.slice(drop);
    /* 删掉对应的老页面文件 */
    for (const l of allLinks.slice(0, drop)) {
      try { fs.unlinkSync(path.join(OUT, 'link-' + String(l.seq).padStart(6, '0') + '.html')); } catch (e) {}
    }
    state.links = keep;
  }

  /* 3. 重写所有保留页面（因为 next 链接可能变了，且 archivedCount 变了） */
  for (let i = 0; i < keep.length; i++) {
    const cur = keep[i];
    const p = keep[i - 1] || null;
    const n = keep[i + 1] || null;
    cur.archivedCount = state.archived || 0;
    fs.writeFileSync(path.join(OUT, 'link-' + String(cur.seq).padStart(6, '0') + '.html'),
      renderPage(cur, p, n, keep));
  }

  /* 4. 索引 */
  fs.writeFileSync(path.join(OUT, 'index.html'), renderIndex(state));

  saveState(state);

  console.log('[chain] 追加第 ' + seq + ' 条');
  console.log('  时间: ' + atBj + ' (北京)');
  console.log('  fact: ' + (fact.task || fact.error || '?'));
  console.log('  prev: ' + prevHash.slice(0, 24) + (prevHash === 'GENESIS' ? '' : '…'));
  console.log('  hash: ' + hash.slice(0, 24) + '…');
  console.log('  链长: ' + keep.length + ' 条（归档 ' + (state.archived || 0) + '）');
  console.log('  页面: ' + (keep.length + 1) + ' 个文件');
}

main();
