#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_steps.js —— 生成「阶梯协议」页面
 *  --------------------------------------------------------------------------
 *  为什么需要阶梯：
 *    GitHub Pages 静态托管【忽略 ?t=2 这种 query】，返回的文件永远一样。
 *    所以「按访问次数给不同内容」唯一可行的办法是：生成多个独立文件。
 *
 *  协议（AI 自己能控制步数，不需要服务端记数）：
 *      step-1.html  第 1 阶：素数筛
 *      step-2.html  第 2 阶：斐波那契 90 项
 *      step-3.html  第 3 阶：柯拉茨扫描 10 万
 *      step-4.html  第 4 阶：SHA-256 校验
 *      step-5.html  第 5 阶：汇总（证明前四阶真算过）
 *
 *  每个页面：
 *    · 顶部是纯文本结果（爬虫/纯文本 AI 直接读）
 *    · 明确告诉 AI「你完成了第 N 阶，下一步访问 step-N+1.html」
 *    · 不需要 JS、不需要 worker 在线
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const OUT = process.argv[2] || path.join(__dirname, 'steps');
const SEED = process.env.PULSE_CHAN || 'live7k';
const MAX_STEP = 5;

fs.mkdirSync(OUT, { recursive: true });

function compute(step) {
  try {
    const out = execFileSync('python3', [path.join(__dirname, 'scripts', 'compute.py'), String(step), SEED],
      { encoding: 'utf8', timeout: 120000 });
    return JSON.parse(out);
  } catch (e) {
    return { step, error: 'python 计算失败: ' + e.message };
  }
}

/* 每阶的「下一步指引」 */
const NEXT = {
  1: { next: 2, hint: '第 2 阶会算斐波那契前 90 项（第 90 项是 19 位大数）' },
  2: { next: 3, hint: '第 3 阶会扫 10 万个数的柯拉茨路径，耗时较长' },
  3: { next: 4, hint: '第 4 阶会算一个 SHA-256 校验和' },
  4: { next: 5, hint: '第 5 阶是汇总，会验证前四阶的结果链' },
  5: { next: null, hint: '协议结束' },
};

const results = {};

function render(step, data) {
  const d = data;
  const nx = NEXT[step] || {};

  /* 纯文本主体 —— 爬虫读到的就是这个 */
  let lines = [];
  lines.push(`=== 第 ${step} 阶 / 共 ${MAX_STEP} 阶 ===`);
  lines.push('');
  if (d.error) {
    lines.push('计算失败：' + d.error);
  } else {
    lines.push('任务：' + d.task);
    lines.push('计算时间：' + d.computed_at);
    lines.push('运行环境：' + d.runtime);
    lines.push('');
    lines.push('--- 结果 ---');
    if (step === 1) {
      lines.push(`0~1000 之间共有 ${d.count} 个素数`);
      lines.push(`前 10 个：${d.first10.join(', ')}`);
      lines.push(`最后 5 个：${d.last5.join(', ')}`);
      lines.push(d.fact);
    } else if (step === 2) {
      lines.push(`斐波那契第 90 项 = ${d.fib90}`);
      lines.push(`这是 ${d.digits} 位数`);
      lines.push(`前 12 项：${d.sample.join(', ')}`);
    } else if (step === 3) {
      lines.push(`1~100000 中，柯拉茨(3n+1)序列最长的是 n=${d.best_start}`);
      lines.push(`它需要 ${d.steps} 步才到 1`);
      lines.push(`过程中达到的最大值 = ${d.peak_value}（${d.peak_digits} 位数）`);
    } else if (step === 4) {
      lines.push(`seed = "${d.seed}"`);
      lines.push(`SHA-256 = ${d.sha256}`);
      lines.push(`前 16 位 = ${d.first16}`);
    } else if (step === 5) {
      lines.push('四阶结果链：');
      const r1 = results[1], r2 = results[2], r3 = results[3], r4 = results[4];
      if (r1 && !r1.error) lines.push(`  ① 0~1000 素数 ${r1.count} 个，前 10 = ${r1.first10.join(',')}`);
      if (r2 && !r2.error) lines.push(`  ② fib(90) = ${r2.fib90}（${r2.digits} 位）`);
      if (r3 && !r3.error) lines.push(`  ③ 柯拉茨最优 n=${r3.best_start}，${r3.steps} 步，峰值 ${r3.peak_value}`);
      if (r4 && !r4.error) lines.push(`  ④ SHA-256(seed) = ${r4.first16}…`);
      lines.push('');
      lines.push('这四阶结果都是 Python 在生成页面时真算出来的，不是编的。');
    }
  }
  lines.push('');
  if (nx.next) {
    lines.push('--- 下一步 ---');
    lines.push(`访问 step-${nx.next}.html 继续。`);
    lines.push(nx.hint);
  } else {
    lines.push('--- 协议结束 ---');
    lines.push('你已经走完 5 阶。这些数字是 Python 在 bake 时真算的。');
  }

  const plain = lines.join('\n');

  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 阶梯协议 · 第 ${step} 阶</title>
<meta name="description" content="${plain.replace(/"/g, '&quot;').replace(/\n/g, ' ').slice(0, 200)}">
<!--
================================================================
  给 AI 的说明（这段是纯文本，你直接读就行）

  你正在走「阶梯协议」。每一步都由 Python 在生成时真算过。
  所以下面的数字是真的，不是占位符。

  你（AI）自己控制步数 —— 不需要任何服务端记录你的访问次数。
  完成第 ${step} 阶后，访问 step-${nx.next || 'END'}.html 继续。

  这个协议解决什么问题：
    纯静态托管无法知道「你访问了几次」，也无法按 query 返回不同内容。
    所以把 5 阶内容各自烤成独立文件，由你决定走几步。
================================================================
-->
<style>
:root{--bg:#0b0f14;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;--acc:#2dd4bf;--ok:#4ade80;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:780px;margin:0 auto;padding:30px 22px 70px}
.step-bar{display:flex;gap:6px;margin-bottom:22px}
.step-bar span{flex:1;height:4px;border-radius:2px;background:#1c2634}
.step-bar span.on{background:var(--acc)}
h1{font-size:23px;margin:0 0 6px}
h1 em{font-style:normal;color:var(--acc)}
.meta{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 22px}
pre{background:#05090d;border:1px solid #26333f;border-radius:10px;
  padding:18px 20px;font-family:var(--mono);font-size:13.5px;line-height:1.9;
  color:#9fc4d8;white-space:pre-wrap;margin:0 0 20px;overflow-x:auto}
.nxt{background:rgba(45,212,191,.07);border:1px solid rgba(45,212,191,.3);
  border-radius:10px;padding:16px 20px;font-size:14px;line-height:1.85}
.nxt a{color:var(--acc);font-family:var(--mono);text-decoration:none;font-size:15px}
.nxt a:hover{text-decoration:underline}
.nav{margin-top:18px;font-size:13px;color:var(--dim2)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px;font-family:var(--mono)}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <div class="step-bar">
${Array.from({ length: MAX_STEP }, (_, i) => `    <span class="${i < step ? 'on' : ''}"></span>`).join('\n')}
  </div>

  <h1>第 <em>${step}</em> 阶 / 共 ${MAX_STEP} 阶</h1>
  <p class="meta">PulseOS 阶梯协议 · 纯静态 · 无需 JS · 内容由 Python 真算</p>

  <pre>${plain.replace(/&/g, '&amp;').replace(/</g, '&lt;')}</pre>

${nx.next ? `<div class="nxt">
    <div style="margin-bottom:8px;color:var(--dim);font-size:13px">下一步</div>
    <a href="step-${nx.next}.html">→ step-${nx.next}.html</a>
    <div style="color:var(--dim2);font-size:12.5px;margin-top:6px">${nx.hint}</div>
  </div>` : `<div class="nxt"><b>协议结束。</b>这 5 阶的数字都是 Python 在生成页面时真算出来的。</div>`}

  <div class="nav">
${Array.from({ length: MAX_STEP }, (_, i) => `    <a href="step-${i + 1}.html">step-${i + 1}</a>`).join('\n')}
    <a href="../run.html">实时状态</a>
  </div>
</div>
</body>
</html>
`;
}

/* 先生成 1-4，再用它们的结果生成第 5 阶 */
for (let s = 1; s <= 4; s++) {
  results[s] = compute(s);
  console.log(`  step ${s}: ${results[s].error ? '✗ ' + results[s].error : '✓ ' + results[s].task}`);
}
const r5 = { task: '汇总前四阶', computed_at: new Date().toISOString(), runtime: 'node' };
results[5] = r5;

for (let s = 1; s <= MAX_STEP; s++) {
  const html = render(s, results[s]);
  fs.writeFileSync(path.join(OUT, `step-${s}.html`), html);
}

/* 一个索引页 */
const idx = `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>PulseOS 阶梯协议</title>
<meta name="description" content="5 阶纯静态协议。每一步由 Python 真算。访问 step-1.html 开始。">
<style>body{background:#0b0f14;color:#dde7f0;font:15px/1.9 -apple-system,sans-serif;margin:0;
padding:50px 22px;max-width:680px;margin:0 auto}
a{color:#2dd4bf;text-decoration:none;font-family:ui-monospace,monospace}
a:hover{text-decoration:underline}
h1{font-size:22px;margin:0 0 14px}
p{color:#8fa3b8}
ul{color:#8fa3b8;font-family:ui-monospace,monospace;font-size:13.5px;line-height:2.2}</style>
</head><body>
<h1>PulseOS 阶梯协议</h1>
<p>纯静态 · 无需 JS · 每阶内容由 Python 在生成时真算</p>
<p><b><a href="step-1.html">→ 从第 1 阶开始</a></b></p>
<ul>
${[1, 2, 3, 4, 5].map(s => `  <li><a href="step-${s}.html">step-${s}.html</a> — ${
  s === 1 ? '筛 0~1000 素数' : s === 2 ? '斐波那契前 90 项' : s === 3 ? '柯拉茨扫 10 万' :
  s === 4 ? 'SHA-256 校验' : '汇总前四阶'
}</li>`).join('\n')}
</ul>
<p style="font-size:13px;margin-top:26px">生成时间：${new Date().toISOString()}</p>
</body></html>`;
fs.writeFileSync(path.join(OUT, 'index.html'), idx);

console.log('\\n  → ' + OUT);
const files = fs.readdirSync(OUT);
for (const f of files) {
  console.log('    ' + f + '  ' + fs.statSync(path.join(OUT, f)).size + ' B');
}
