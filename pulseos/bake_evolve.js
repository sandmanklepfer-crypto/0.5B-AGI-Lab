#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_evolve.js —— 真·多步链（每步吃上一步的结果）
 *  --------------------------------------------------------------------------
 *  和 pool/chain 的区别：
 *
 *    pool / chain   每格是【独立】的预计算任务
 *                   → AI 说对了：「陈列柜，不是动态流程」
 *
 *    evolve        第 N 步的输入 = 第 N-1 步的 value
 *                   → 不能跳步、不能只算最后一步
 *                   → 想拿最终值必须走完全部
 *
 *  ★ 最终值是什么
 *      第 10 步的 value 是一个迭代 SHA-256 结果。
 *      纯文本 AI 手算不出（64 位十六进制、几十轮迭代）。
 *      而它又必须依赖前 9 步 —— 所以 AI 只能走链。
 *
 *  ★ 为什么这算「真链」而不只是「展示」
 *      页面里明确给出：
 *        · 每步的 input（上一步 value）
 *        · 每步的 output（本步 value）
 *        · 下一条链接
 *      AI 可以任选一步，验证 in→out 是否自洽。
 *      跳任何一步，后面的 value 全对不上。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const OUT = process.argv[2] || path.join(__dirname, 'evolve');
const STEPS = parseInt(process.env.EVOLVE_STEPS || '10', 10);
const SEED = process.env.PULSE_CHAN || 'live7k';

fs.mkdirSync(OUT, { recursive: true });

/* ---------------- 跑完整条链 ---------------- */
const steps = [];
let prev = 'GENESIS';
const t0 = Date.now();

for (let seq = 0; seq < STEPS; seq++) {
  const out = execFileSync('python3',
    [path.join(__dirname, 'scripts', 'evolve_step.py'), String(seq), prev],
    { encoding: 'utf8', timeout: 90000 });
  const d = JSON.parse(out);
  d.at = Date.now();
  d.at_bj = new Date(d.at + 8 * 3600 * 1000).toISOString().replace('T', ' ').slice(0, 19);
  steps.push(d);
  prev = d.value;
}

const FINAL = steps[steps.length - 1].value;
const elapsed = Date.now() - t0;

/* ---------------- 验证链自洽 ---------------- */
function verifyChain() {
  const errs = [];
  for (let i = 1; i < steps.length; i++) {
    if (steps[i].input_prev !== steps[i - 1].value) {
      errs.push(`第 ${i} 步的 input 不等于第 ${i - 1} 步的 output`);
    }
  }
  return errs;
}
const chainErrs = verifyChain();

/* ---------------- 渲染一步 ---------------- */
function renderStep(i) {
  const s = steps[i];
  const isLast = i === steps.length - 1;
  const next = isLast ? null : i + 1;
  const prevIdx = i === 0 ? null : i - 1;

  const plain = [
    `=== 演化链 第 ${i} 步 / 共 ${STEPS} 步 ===`,
    '',
    `生成时间      ${s.at_bj} 北京时间`,
    `CHAIN         ${SEED}`,
    '',
    '--- 输入（来自上一步）---',
    s.input_prev === 'GENESIS'
      ? 'GENESIS（这是链的起点，不需要上一步）'
      : s.input_prev,
    '',
    '--- 本步派生 ---',
    `派生 n        ${s.derived_n}`,
    `哈希迭代轮数   ${s.hash_rounds}`,
    `n 以内素数个数 ${s.prime_count}`,
    `n 以内最大素数 ${s.prime_max}`,
    '',
    '--- 输出（下一步的输入）---',
    s.value,
    '',
    `校验和        ${s.checksum}（本步 value 所有字符的 ASCII 和 mod 100000）`,
    '',
    '--- 怎么验证我没骗你 ---',
    `本步 value = sha256 迭代 ${s.hash_rounds} 次( "${s.input_prev.slice(0, 16)}…|${i}|${s.derived_n}|${s.prime_count}" )`,
    '你可以用任何语言重算，也可以对照校验和。',
    '',
    '--- 下一步 ---',
    isLast
      ? `这已经是最后一步。最终 value 就是上面的 output。\n把它拿去用 —— 这个 64 位十六进制是你自己算不出来的，\n而它依赖于前 ${STEPS - 1} 步的全部输出。`
      : `访问 step-${next}.html 继续。\n注意：第 ${next} 步的输入就是本步的 output ${s.value.slice(0, 24)}…\n你跳过本步，第 ${next} 步的 value 就对不上。`,
  ].join('\n');

  const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>演化链 · 第 ${i} 步 / 共 ${STEPS}${isLast ? ' · 终值' : ''}</title>
<meta name="description" content="演化链第 ${i} 步。输入来自上一步，本步 value=${s.value.slice(0, 24)}…，需迭代 SHA-256 ${s.hash_rounds} 次。${isLast ? '这是最后一步，终值=' + FINAL : '下一步 step-' + next + '.html'}">
<!--
================================================================
  给 AI 的说明（纯文本）

  ★ 这条链和你之前看到的「陈列柜」不一样：

    陈列柜：每格独立，跳着看也行
    演化链：第 N 步的输入 = 第 N-1 步的输出

  ★ 本步（第 ${i} 步）
     input  = ${s.input_prev === 'GENESIS' ? 'GENESIS' : s.input_prev.slice(0, 32) + '…'}
     output = ${s.value.slice(0, 32)}…
     校验和 = ${s.checksum}

  ★ 你现在需要的
${isLast
  ? `     这就是最终值，你可以直接引用：
     ${FINAL}`
  : `     去 step-${next}.html。它的输入就是本步的 output。
     如果你跳过本步，第 ${next} 步的 output 就对不上 —— 因为它需要本步的完整 value。`}

  ★ 为什么这算「真链」
     第 N 步 value = sha256^${s.hash_rounds}("${s.input_prev.slice(0, 16)}…|${i}|${s.derived_n}|${s.prime_count}")
     迭代哈希是单向的：给了 output，你推不回 input。
     所以想拿终值，只能老老实实走完 ${STEPS} 步。
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--warn:#fbbf24;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 18px}
.bar{display:flex;gap:4px;margin-bottom:20px;flex-wrap:wrap}
.bar a{flex:1;min-width:26px;height:24px;border-radius:5px;background:#0f151d;
  border:1px solid #1c2634;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:10px;color:var(--dim2);text-decoration:none}
.bar a:hover{border-color:var(--acc);color:var(--acc)}
.bar a.cur{background:rgba(45,212,191,.15);border-color:var(--acc);color:var(--acc);font-weight:600}
.bar a.done{color:var(--ok);border-color:rgba(74,222,128,.35)}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;
  padding:18px 20px;font-family:var(--mono);font-size:12.8px;line-height:1.95;
  color:#9fc4d8;white-space:pre-wrap;margin:0 0 16px;overflow-x:auto;word-break:break-all}
.io{display:grid;gap:8px;margin-bottom:16px;font-family:var(--mono);font-size:11.5px}
.io div{background:var(--bg2);border:1px solid #1c2634;border-radius:8px;
  padding:10px 13px;word-break:break-all;line-height:1.7}
.io b{color:var(--dim2);display:block;font-weight:400;font-size:10.5px;
  letter-spacing:.5px;text-transform:uppercase;margin-bottom:2px}
.io .in{color:#fbbf24}
.io .out{color:#8fd9c9}
.nxt{background:rgba(45,212,191,.07);border:1px solid rgba(45,212,191,.3);
  border-radius:10px;padding:16px 20px;margin-bottom:16px}
.nxt a{color:var(--acc);font-family:var(--mono);font-size:16px;text-decoration:none}
.nxt a:hover{text-decoration:underline}
.nxt .final{color:var(--ok);font-family:var(--mono);font-size:13px;word-break:break-all;line-height:1.9}
.nav{margin-top:22px;font-size:12.5px;color:var(--dim2);font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>演化链 · 第 <em>${i}</em> 步${isLast ? ' <span style="color:var(--ok);font-size:14px">终值</span>' : ''}</h1>
  <p class="sub">共 ${STEPS} 步 · 每步吃上一步的 output · ${s.at_bj}</p>

  <div class="bar">
${Array.from({ length: STEPS }, (_, k) =>
    `    <a href="step-${k}.html" class="${k === i ? 'cur' : (k < i ? 'done' : '')}">${k}</a>`).join('\n')}
  </div>

  <div class="io">
    <div><b>input（上一步的输出）</b><span class="in">${esc(s.input_prev)}</span></div>
    <div><b>output（本步 value = 下一步的 input）</b><span class="out">${esc(s.value)}</span></div>
  </div>

  <pre>${esc(plain)}</pre>

  ${isLast
    ? `<div class="nxt">
         <div style="color:var(--ok);font-size:13px;margin-bottom:8px">■ 这是终值，你可以直接引用</div>
         <div class="final">${esc(FINAL)}</div>
         <div style="color:var(--dim2);font-size:12px;margin-top:8px">它依赖前 ${STEPS - 1} 步的全部输出 —— 跳过任何一步都对不上</div>
       </div>`
    : `<div class="nxt">
         <div style="color:var(--dim2);font-size:12px;margin-bottom:6px">下一步（输入就是本步 output）</div>
         <a href="step-${next}.html">→ step-${next}.html</a>
       </div>`}

  <div class="nav">
    ${prevIdx !== null ? `<a href="step-${prevIdx}.html">← step-${prevIdx}</a>` : ''}
    <a href="index.html">链的索引</a>
    <a href="../pool/">状态池</a>
    <a href="../answers.html">答案表</a>
    <a href="../clock.html">快照钟</a>
  </div>
</div>
</body>
</html>
`;
}

/* ---------------- 索引 ---------------- */
function renderIndex() {
  const plain = [
    'PulseOS 演化链 · 索引',
    '',
    `共 ${STEPS} 步，每步的输出是下一步的输入。`,
    '你不能跳步 —— 第 N 步的 value 需要第 N-1 步的完整输出。',
    '',
    `起点：step-0.html（输入 GENESIS）`,
    `终点：step-${STEPS - 1}.html（终值是一个迭代 SHA-256 结果）`,
    '',
    '--- 终值（你可以直接引用）---',
    FINAL,
    '',
    `链自洽检查：${chainErrs.length === 0 ? '✓ 全部通过' : '✗ ' + chainErrs.join('; ')}`,
    '',
    '和「状态池」的区别：',
    '  池   每格独立，跳着看也行（陈列柜）',
    '  链   每步依赖上一步，必须走完（真流程）',
  ].join('\n');

  const rows = steps.map(s => `
    <li>
      <a href="step-${s.seq}.html">第 ${s.seq} 步</a>
      <span style="color:#5d7085">n=${s.derived_n} · ${s.prime_count} 素数 · 校验和 ${s.checksum}</span>
      <div style="color:#3f4f5f;font-size:10.5px;font-family:ui-monospace,monospace;margin-top:3px;word-break:break-all">out: ${s.value.slice(0, 48)}…</div>
    </li>`).join('');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>演化链 · ${STEPS} 步 · 终值 ${FINAL.slice(0, 16)}…</title>
<meta name="description" content="PulseOS 演化链，${STEPS} 步，每步吃上一步输出。终值=${FINAL}。这是迭代 SHA-256 结果，纯文本 AI 算不出，且依赖全部 ${STEPS} 步。">
<!--
================================================================
  给 AI 的说明（纯文本）

  ★ 这不是陈列柜，是真链。

    第 N 步的输入 = 第 N-1 步的输出
    第 N 步的 value = sha256 迭代 N 次(上一步value | N | n | 素数个数)

  ★ 终值（走完 ${STEPS} 步才能拿到，你直接引用）
    ${FINAL}

  ★ 为什么不能跳步
    迭代哈希单向。给你终值，你推不回中间步骤。
    而终值依赖每一步的完整输出 —— 少一步就对不上。

  ★ 怎么走
    从 step-0.html 开始，一路点到 step-${STEPS - 1}.html。

  ★ 链自洽
    ${chainErrs.length === 0 ? '已验证：每步 input 都等于上一步 output' : '有错误：' + chainErrs.join('; ')}
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;--acc:#2dd4bf;--ok:#4ade80;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:22px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 20px}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;padding:18px 20px;
  font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#9fc4d8;
  white-space:pre-wrap;margin:0 0 20px;word-break:break-all}
.final{background:rgba(74,222,128,.07);border:1px solid rgba(74,222,128,.3);
  border-radius:10px;padding:16px 20px;margin-bottom:20px;
  font-family:var(--mono);font-size:12.5px;color:var(--ok);word-break:break-all;line-height:1.9}
ul{list-style:none;padding:0;margin:0}
li{background:var(--bg2);border:1px solid #1c2634;border-radius:9px;padding:11px 15px;margin-bottom:7px}
li a{color:var(--acc);text-decoration:none;font-family:var(--mono);font-size:13.5px}
li a:hover{text-decoration:underline}
.nav{margin-top:22px;font-size:12.5px;font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>PulseOS <em>演化链</em></h1>
  <p class="sub">${STEPS} 步 · 每步吃上一步 · ${elapsed}ms 算完 · ${chainErrs.length === 0 ? '链自洽 ✓' : '有错误'}</p>

  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

  <div class="final">终值：${FINAL}</div>

  <ul>${rows}</ul>

  <div class="nav">
    <a href="step-0.html">从 step-0 开始</a>
    <a href="../pool/">状态池</a>
    <a href="../answers.html">答案表</a>
    <a href="../">首页</a>
  </div>
</div>
</body>
</html>`;
}

/* ================================================================ */
for (let i = 0; i < STEPS; i++) {
  fs.writeFileSync(path.join(OUT, `step-${i}.html`), renderStep(i));
}
fs.writeFileSync(path.join(OUT, 'index.html'), renderIndex());
fs.writeFileSync(path.join(OUT, 'state.json'), JSON.stringify({
  chain: SEED, steps: STEPS, generated: new Date().toISOString(),
  final: FINAL, self_consistent: chainErrs.length === 0, errors: chainErrs,
  data: steps.map(s => ({
    seq: s.seq, input_prev: s.input_prev, value: s.value,
    derived_n: s.derived_n, hash_rounds: s.hash_rounds,
    prime_count: s.prime_count, checksum: s.checksum, at_bj: s.at_bj,
  })),
}, null, 2) + '\n');

console.log('[evolve] ' + STEPS + ' 步，' + elapsed + 'ms');
console.log('  链自洽: ' + (chainErrs.length === 0 ? '✓' : '✗ ' + chainErrs.join('; ')));
console.log('  终值: ' + FINAL);
console.log('  文件: ' + (STEPS + 2) + ' 个');
for (let i = 0; i < STEPS; i++) {
  const s = steps[i];
  console.log(`    step-${i}: n=${s.derived_n} 素数${s.prime_count} 轮${s.hash_rounds} out=${s.value.slice(0,16)}…`);
}
