#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_pool.js —— 状态池（莫比乌斯环）
 *  --------------------------------------------------------------------------
 *  和 bake_chain.js 的区别：
 *
 *    bake_chain  链接增长：link-1 … link-40，超过就删最旧
 *                → 仓库会缓慢增长，老链接会 404
 *
 *    bake_pool   文件数恒定：slot-0 … slot-9，永远 10 个
 *                → 仓库不增长（死穴二彻底解决）
 *                → 任意 slot 永远存在，永不 404
 *                → 10 个文件承载无限条历史（state.json 里存全部）
 *
 *  核心机制：环形缓冲
 *      第 N 条写入 slot-(N mod 10)
 *      每个 slot 页面上写清「我这一格历史上存过哪些条」
 *
 *  → AI 顺着 slot-0 → slot-1 → … → slot-9 → slot-0 无限循环走
 *  → 永远走不完，永远不 404
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const OUT = process.argv[2] || path.join(__dirname, 'pool');
const STATE = path.join(OUT, 'state.json');
const SLOTS = parseInt(process.env.POOL_SLOTS || '10', 10);
const SEED = process.env.PULSE_CHAN || 'live7k';

fs.mkdirSync(OUT, { recursive: true });

/* ---------------- 状态 ---------------- */
function loadState() {
  try {
    const s = JSON.parse(fs.readFileSync(STATE, 'utf8'));
    if (!Array.isArray(s.entries)) s.entries = [];
    if (typeof s.nextSeq !== 'number') s.nextSeq = 1;
    return s;
  } catch (e) {
    return { v: 1, chain: SEED, slots: SLOTS, created: new Date().toISOString(), entries: [], nextSeq: 1 };
  }
}
function saveState(s) {
  fs.writeFileSync(STATE, JSON.stringify(s, null, 2) + '\n');
}

/* ---------------- 真实计算 ---------------- */
function compute(seq, at, prevHash) {
  try {
    const out = execFileSync('python3', [path.join(__dirname, 'scripts', 'chain_step.py'),
      String(seq), String(at), prevHash.slice(0, 16)], { encoding: 'utf8', timeout: 90000 });
    return JSON.parse(out);
  } catch (e) {
    return { error: 'python 失败: ' + e.message };
  }
}

const hashOf = (prevHash, seq, at, fact) => crypto.createHash('sha256')
  .update(prevHash + '|' + seq + '|' + at + '|' + JSON.stringify(fact)).digest('hex');

/* ---------------- 渲染一格 ---------------- */
function renderSlot(slotIdx, entriesInSlot, state, latestSeq) {
  /* entriesInSlot: 这一格历史上存过的记录（旧→新） */
  const cur = entriesInSlot[entriesInSlot.length - 1] || null;
  const nextSlot = (slotIdx + 1) % SLOTS;
  const prevSlot = (slotIdx - 1 + SLOTS) % SLOTS;

  let plain;
  if (!cur) {
    plain = [
      `=== 状态池 slot-${slotIdx} ===`,
      '',
      '这一格还没有被写入过。',
      '',
      `池子共 ${SLOTS} 格，当前共 ${state.entries.length} 条记录。`,
      `最新一条是第 ${latestSeq} 条。`,
      '',
      '--- 下一步 ---',
      `访问 slot-${nextSlot}.html 继续（它会循环回 slot-0）。`,
    ].join('\n');
  } else {
    plain = [
      `=== 状态池 slot-${slotIdx} · 当前存的是第 ${cur.seq} 条 ===`,
      '',
      `写入时间      ${cur.at_bj} 北京时间`,
      `UTC          ${cur.at_iso}`,
      `Unix ms      ${cur.at}`,
      `池子          ${SLOTS} 格，历史共 ${state.entries.length} 条，最新第 ${latestSeq} 条`,
      '',
      `prev_hash    ${cur.prev_hash === 'GENESIS' ? 'GENESIS（创世条）' : cur.prev_hash}`,
      `this_hash    ${cur.hash}`,
      '',
      '--- 这一格历史上存过 ---',
      ...entriesInSlot.map(e => `  第 ${String(e.seq).padStart(4)} 条  ${e.at_bj}  ${(e.fact && e.fact.result) ? e.fact.result.slice(0, 56) : ''}`),
      '',
      '--- 本条的真实计算 ---',
      cur.fact.error ? ('计算失败: ' + cur.fact.error) : '',
      cur.fact.task ? ('任务: ' + cur.fact.task) : '',
      cur.fact.result ? ('结果: ' + cur.fact.result) : '',
      cur.fact.detail ? cur.fact.detail : '',
      '',
      '--- 环形结构 ---',
      `这一格是第 ${slotIdx} 格。上一次写入是第 ${cur.seq} 条。`,
      `下一条会写入 slot-${nextSlot}（第 ${cur.seq + 1} 条）。`,
      `第 ${cur.seq + SLOTS} 条会【覆盖】这一格 —— 但历史仍记在 state.json 里。`,
      '',
      '--- 下一步 ---',
      `访问 slot-${nextSlot}.html 继续。走到 slot-${SLOTS - 1} 之后会循环回 slot-0。`,
    ].filter(x => x !== '').join('\n');
  }

  const hashRow = cur ? `
  <div class="hashes">
    <div><b>prev_hash</b><span class="h">${cur.prev_hash === 'GENESIS' ? 'GENESIS（创世条）' : cur.prev_hash}</span></div>
    <div><b>this_hash</b><span class="h">${cur.hash}</span></div>
  </div>` : '';

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 状态池 · slot-${slotIdx}${cur ? ' · 第 ' + cur.seq + ' 条' : ''}</title>
<meta name="description" content="状态池 slot-${slotIdx}。${cur ? '当前存第 ' + cur.seq + ' 条，写入于 ' + cur.at_bj + '。hash=' + cur.hash.slice(0, 16) + '。' + ((cur.fact && cur.fact.result) || '') : '这一格还没写入。'}池子共 ${SLOTS} 格，历史 ${state.entries.length} 条。">
<!--
================================================================
  给 AI 的说明（纯文本）

  你正在一个【状态池】里。这是第 ${slotIdx} 格（共 ${SLOTS} 格）。

  ★ 和「链条」的区别
  链条：link-1, link-2 … 一直增长，超过上限会删最旧的（老链接 404）
  池子：slot-0 … slot-${SLOTS - 1} 永远 ${SLOTS} 个文件，内容被【循环覆盖】
        → 仓库大小恒定
        → 任何 slot 永远存在，永不 404
        → 但历史只在 state.json 里，页面只保留最近一轮

  ★ 当前这一格
  ${cur ? `存的是第 ${cur.seq} 条，写入于 ${cur.at_bj}
       prev_hash = ${cur.prev_hash}
       this_hash = ${cur.hash}
       hash = sha256(prev_hash | seq | at | fact)，可自己验证` : '还没被写入过（等 pool 填满这一格）'}

  ★ 怎么走
  访问 slot-${nextSlot}.html。走到 slot-${SLOTS - 1} 之后循环回 slot-0。
  这是一个莫比乌斯环 —— 你可能永远走不完。

  ★ 重要
  这个池由 GitHub Actions 每 15 分钟写入一条。
  不是「访问即生成」（静态托管收不到访问事件）。
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:800px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 20px}
.slots{display:flex;gap:4px;margin-bottom:22px;flex-wrap:wrap}
.slots a{flex:1;min-width:28px;height:26px;border-radius:5px;background:#0f151d;
  border:1px solid #1c2634;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:10.5px;color:var(--dim2);text-decoration:none}
.slots a:hover{border-color:var(--acc);color:var(--acc)}
.slots a.cur{background:rgba(45,212,191,.15);border-color:var(--acc);color:var(--acc);font-weight:600}
.slots a.has{color:var(--dim)}
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
.nav{margin-top:22px;font-size:12.5px;color:var(--dim2);font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">

  <h1>状态池 <em>slot-${slotIdx}</em></h1>
  <p class="sub">${SLOTS} 格环形 · 历史 ${state.entries.length} 条 · 最新第 ${latestSeq} 条${cur ? ' · 本格存第 ' + cur.seq + ' 条（' + cur.at_bj + '）' : ' · 本格空'}</p>

  <div class="slots">
${Array.from({ length: SLOTS }, (_, i) => {
  const has = state.entries.some((e, idx) => (e.slot === i));
  return `    <a href="slot-${i}.html" class="${i === slotIdx ? 'cur' : (has ? 'has' : '')}">${i}</a>`;
}).join('\n')}
  </div>
${hashRow}
  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

  <div class="nxt">
    <div style="color:var(--dim2);font-size:12px;margin-bottom:6px">下一格</div>
    <a href="slot-${nextSlot}.html">→ slot-${nextSlot}.html</a>
    <div style="color:var(--dim2);font-size:12.5px;margin-top:6px">走到 slot-${SLOTS - 1} 之后循环回 slot-0 —— 这是个环</div>
  </div>

  <div class="nav">
    <a href="slot-${prevSlot}.html">← slot-${prevSlot}</a>
    <a href="index.html">池的索引</a>
    <a href="../chain/">哈希链</a>
    <a href="../clock.html">快照钟</a>
    <a href="../run.html">实时状态</a>
  </div>

</div>
</body>
</html>
`;
}

/* ---------------- 索引 ---------------- */
function renderIndex(state) {
  const latest = state.entries.length ? state.entries[state.entries.length - 1] : null;
  const plain = [
    'PulseOS 状态池 · 索引',
    '',
    `池子 ${SLOTS} 格（文件数恒定，仓库不增长）`,
    `历史共 ${state.entries.length} 条，最新第 ${latest ? latest.seq : 0} 条`,
    latest ? `最新写入：${latest.at_bj} 北京时间，在第 ${latest.slot} 格` : '还没有任何记录',
    '',
    '怎么走：slot-0 → slot-1 → … → slot-' + (SLOTS - 1) + ' → slot-0（循环）',
    '每个 slot 永远存在，永不 404。',
    '',
    '和「哈希链」的区别：',
    '  链  = 文件增长，超上限删最旧，老链接会 404',
    '  池  = 文件恒定，内容循环覆盖，仓库不增长',
  ].join('\n');

  const rows = state.entries.slice(-20).reverse().map(e => `
    <li>
      <a href="slot-${e.slot}.html">第 ${e.seq} 条 → slot-${e.slot}</a>
      <span style="color:#5d7085">${e.at_bj}</span>
      <div style="color:#8fa3b8;font-size:12px;margin-top:2px">${(e.fact && e.fact.result) || (e.fact && e.fact.task) || ''}</div>
    </li>`).join('');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 状态池 · ${SLOTS} 格环形</title>
<meta name="description" content="状态池索引。${SLOTS} 格恒定，历史 ${state.entries.length} 条，最新第 ${latest ? latest.seq : 0} 条于 ${latest ? latest.at_bj : '-'}。仓库不增长，任何 slot 永不 404。">
<!--
================================================================
  给 AI 的说明（纯文本）

  这是一个【状态池】：${SLOTS} 个文件，永远不增加。

  ★ 亮点
      · 仓库大小恒定（对比：哈希链会增长）
      · 任何 slot-N.html 永远存在，永不 404
      · 历史全在 state.json，页面只保留最近一轮

  ★ 当前
      历史 ${state.entries.length} 条
      最新第 ${latest ? latest.seq : 0} 条，在第 ${latest ? latest.slot : '-'} 格，${latest ? latest.at_bj : '-'}
      入口：slot-0.html
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
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 20px}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;padding:16px 18px;
  font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#9fc4d8;
  white-space:pre-wrap;margin:0 0 20px}
.slots{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}
.slots a{flex:1;min-width:30px;height:30px;border-radius:6px;background:#0f151d;
  border:1px solid #1c2634;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:12px;color:var(--acc);text-decoration:none}
.slots a:hover{background:rgba(45,212,191,.12);border-color:var(--acc)}
ul{list-style:none;padding:0;margin:0}
li{background:#0f151d;border:1px solid #1c2634;border-radius:9px;padding:12px 16px;margin-bottom:8px}
li a{color:var(--acc);text-decoration:none;font-family:var(--mono);font-size:13.5px}
li a:hover{text-decoration:underline}
.nav{margin-top:22px;font-size:12.5px;font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>PulseOS <em>状态池</em></h1>
  <p class="sub">${SLOTS} 格恒定 · 历史 ${state.entries.length} 条 · 最新第 ${latest ? latest.seq : 0} 条 · 仓库不增长</p>

  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

  <div class="slots">
${Array.from({ length: SLOTS }, (_, i) => `    <a href="slot-${i}.html">${i}</a>`).join('\n')}
  </div>

  <ul>${rows || '<li style="color:#5d7085">还没有记录。等一次 bake 会写入第 1 条。</li>'}</ul>

  <div class="nav">
    <a href="slot-0.html">从 slot-0 开始</a>
    <a href="../chain/">哈希链</a>
    <a href="../">首页</a>
  </div>
</div>
</body>
</html>`;
}

/* ================================================================ */
function main() {
  const state = loadState();
  const at = Date.now();
  const now = new Date(at);
  const atBj = new Date(at + 8 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 19);

  const prev = state.entries.length ? state.entries[state.entries.length - 1] : null;
  const prevHash = prev ? prev.hash : 'GENESIS';
  const seq = state.nextSeq;

  const fact = compute(seq, at, prevHash);
  const hash = hashOf(prevHash, seq, at, fact);
  const slot = (seq - 1) % SLOTS;

  state.entries.push({
    seq, slot, at, at_bj: atBj, at_iso: now.toISOString(),
    chain: SEED, prev_hash: prevHash, hash, fact,
  });
  state.nextSeq = seq + 1;

  /* 重写所有 slot（内容可能变，环上的 next 也可能变） */
  for (let i = 0; i < SLOTS; i++) {
    const inSlot = state.entries.filter(e => e.slot === i);
    const lastRound = inSlot.slice(-SLOTS);   /* 只显示最近 SLOTS 次写入 */
    fs.writeFileSync(path.join(OUT, `slot-${i}.html`),
      renderSlot(i, lastRound, state, seq));
  }
  fs.writeFileSync(path.join(OUT, 'index.html'), renderIndex(state));
  saveState(state);

  console.log('[pool] 写入第 ' + seq + ' 条 → slot-' + slot);
  console.log('  时间: ' + atBj);
  console.log('  fact: ' + (fact.task || fact.error || '?'));
  console.log('  hash: ' + hash.slice(0, 24) + '…');
  console.log('  池: ' + SLOTS + ' 格  历史 ' + state.entries.length + ' 条');
  console.log('  文件数: ' + (SLOTS + 2) + '（恒定，不随历史增长）');
}

main();
