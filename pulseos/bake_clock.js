#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_clock.js —— 生成「静态钟表页」clock.html
 *  --------------------------------------------------------------------------
 *  三个组成部分，各解决一个问题：
 *
 *    ① SVG 静态钟表      →  视觉模型截图后能「看」出快照时间
 *                            （纯静态，零 JS，指针角度在 bake 时算好）
 *
 *    ② 纯文本时间戳      →  纯文本 AI 直接读，不需要渲染
 *
 *    ③ 1px 信标 + ?t=    →  有浏览器的 AI 渲染页面时会发一次 GET
 *                            ?t=<毫秒> 绕过 GitHub 的 max-age=600 缓存
 *
 *  ★ 必须说清的：③ 只有「真的会渲染页面的 AI」才会发。
 *     纯文本 AI 只读源码，<img> 不会被请求。
 *     而且 GitHub Pages 收到 GET 后不做任何事 —— 需要另配接收端。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { buildClock } = require('./scripts/clock_svg');

const OUT = process.argv[2] || path.join(__dirname, 'clock.html');
const CHAN = process.env.PULSE_CHAN || 'live7k';

/* 信标地址：默认指向 GitHub Pages 自己（只发请求，不记录）
   想真记录就换成你自己的 Worker / 第三方统计 */
const BEACON = process.env.PULSE_BEACON || '';

const now = new Date();
const stamp = now.toISOString();
const bjTime = new Date(now.getTime() + 8 * 3600 * 1000);
const bjStr = bjTime.toISOString().replace('T', ' ').slice(0, 19);

/* 读一下 run.html 里的实时数据（如果存在） */
let liveInfo = null;
try {
  const rj = path.join(__dirname, 'result.json');
  if (fs.existsSync(rj)) liveInfo = JSON.parse(fs.readFileSync(rj, 'utf8'));
} catch (e) {}

const svg = buildClock(bjTime, { size: 200 });
const beaconUrl = BEACON
  ? `${BEACON}?ch=${CHAN}&t=${now.getTime()}&page=clock`
  : `https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/pulseos/clock.html?ping=${now.getTime()}`;

const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 快照钟 · ${bjStr} 北京时间</title>
<meta name="description" content="PulseOS 静态快照钟。快照时间 ${bjStr} 北京时间（UTC ${stamp}）。指针停在 ${bjStr.slice(11)}，读图即可知道数据时刻。无需 JS。">
<!--
================================================================
  给 AI 的说明（纯文本，直接读）

  这是一个「静态钟表页」。它不是实时时钟，是一个【快照】。

  快照时间：${bjStr} 北京时间
  对应 UTC：${stamp}
  Unix 毫秒：${now.getTime()}
  数据年龄：页面生成时刻距你读取时刻的差，自己算一下就知道新鲜度

  页面上的 SVG 钟表，指针角度是【生成时算好的】。
  所以：
    · 如果你能渲染页面 → 看指针位置就知道快照时间
    · 如果你只读文本   → 上面这行 UTC 时间就是答案

  ★ 关于「1px 信标」
  页面里有一个 <img> 指向带随机参数的信标地址。
  如果你（AI）用真实的浏览器渲染这个页面，它会被请求一次 ——
  这是「访问即触发」的物理机制。
  但如果你只读 HTML 源码，这个 <img> 不会被请求，什么都不会发生。

  这是物理事实，不是页面做得不够。
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:40px 22px 70px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.3px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 30px}

.clockbox{display:flex;gap:28px;align-items:center;flex-wrap:wrap;
  background:var(--bg2);border:1px solid #1c2634;border-radius:14px;
  padding:26px 28px;margin-bottom:22px}
.tl-clock{filter:drop-shadow(0 0 18px rgba(45,212,191,.18));flex:0 0 auto}
.info{flex:1;min-width:200px;font-family:var(--mono);font-size:13px;line-height:2.1;color:var(--dim)}
.info b{color:var(--fg);font-weight:500}
.info .big{font-size:19px;color:var(--acc);font-family:var(--mono);letter-spacing:.5px}
.info .k{color:var(--dim2);display:inline-block;width:96px}

.card{background:var(--bg2);border:1px solid #1c2634;border-radius:11px;
  padding:18px 20px;margin-bottom:14px}
.card h2{font-size:12px;margin:0 0 12px;color:var(--dim2);letter-spacing:.6px;
  text-transform:uppercase;font-weight:600}
.card p{margin:0 0 10px;color:var(--dim);font-size:13.5px}
.card p:last-child{margin-bottom:0}
.card code{background:#05090d;padding:1px 6px;border-radius:4px;
  font-family:var(--mono);font-size:12px;color:#8fd9c9}
pre{background:#05090d;border:1px solid #26333f;border-radius:9px;padding:15px 17px;
  font-family:var(--mono);font-size:12.5px;line-height:1.9;color:#9fc4d8;
  white-space:pre-wrap;margin:0;overflow-x:auto}

.warn{background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.28);
  border-radius:10px;padding:15px 18px;font-size:13.5px;line-height:1.9}
.warn b{color:#fbbf24}

.nav{margin-top:24px;font-size:13px;color:var(--dim2)}
.nav a{color:var(--dim);text-decoration:none;margin-right:16px;font-family:var(--mono)}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">

  <h1>PulseOS <em>快照钟</em></h1>
  <p class="sub">纯静态 · 零 JS · 指针停在生成时刻</p>

  <div class="clockbox">
    ${svg}
    <div class="info">
      <div class="big">${bjStr.slice(11)}</div>
      <div style="color:var(--dim2);font-size:11px;margin-bottom:8px">北京时间</div>
      <div><span class="k">快照 UTC</span><b>${stamp}</b></div>
      <div><span class="k">Unix ms</span><b>${now.getTime()}</b></div>
      <div><span class="k">频道</span><b>${CHAN}</b></div>
    </div>
  </div>

  <div class="card">
    <h2>这一页是什么</h2>
    <p>钟表的指针角度是在<strong>生成页面时算好并写死</strong>的。所以它不是实时时钟，
       是一个<strong>快照</strong>——指针停在哪，数据就是那一刻的。</p>
    <p>这样做的好处：<strong>不需要 JS</strong>。视觉模型截图后能从指针位置直接读出时间，
       纯文本 AI 读上面的 UTC 时间戳就行。</p>
  </div>

  <div class="card">
    <h2>为什么 CSS 做不到，SVG 可以</h2>
    <pre>CSS 动画  →  只能「转」，不能显示【真实当前时间】
SVG      →  指针角度 = f(时, 分, 秒)，在 bake 时算出来
            静态写进 &lt;line x2= y2= /&gt;，零 JS 也能被看见</pre>
  </div>

  <div class="card">
    <h2>1px 信标（访问即触发的物理机制）</h2>
    <pre>${beaconUrl}</pre>
    <p style="margin-top:10px">页面里有一个隐藏的 &lt;img&gt; 指向上面这个地址，
       带 <code>?t=${now.getTime()}</code> 是为了绕过 GitHub 的
       <code>Cache-Control: max-age=600</code>（实测缓存 10 分钟）。</p>
  </div>

  <div class="warn">
    <b>必须说清的边界</b><br><br>
    ① <b>只有「真的渲染页面」的 AI</b>（headless Chrome / Playwright / 带浏览的 ChatGPT、Perplexity）
       才会去请求那个 &lt;img&gt;。纯文本 AI 只读源码，图片不会被加载。<br><br>
    ② <b>GitHub Pages 收到这个 GET 后什么都不做</b> —— 它不记日志、不执行代码。
       想真的记录或触发，信标得指向你自己的 Cloudflare Worker。<br><br>
    ③ 现在信标指向 GitHub Pages 自己，所以它<strong>只会发一次请求，然后什么都没有</strong>。
       这不是 bug，是静态托管的物理限制。
  </div>

  ${liveInfo ? `<div class="card">
    <h2>最近一次实时快照（来自 result.json）</h2>
    <pre>${JSON.stringify({
      generated_at: liveInfo.generated_at,
      online: liveInfo.online,
      workers: (liveInfo.workers || []).map(w => w.name + '(' + (w.alive ? '活' : '假死') + ')'),
    }, null, 2).replace(/</g, '&lt;')}</pre>
  </div>` : ''}

  <div class="nav">
    <a href="steps/">阶梯协议</a>
    <a href="run.html">实时状态</a>
    <a href="demo.html">控制台</a>
    <a href="./">首页</a>
  </div>

  <!-- ★ 1px 信标：只有渲染页面的浏览器才会请求它 -->
  <img src="${beaconUrl}" width="1" height="1" alt=""
       style="position:absolute;left:-9999px;opacity:0" referrerpolicy="no-referrer">

</div>
</body>
</html>
`;

fs.writeFileSync(OUT, html);
console.log('[clock] → ' + OUT);
console.log('  快照时间: ' + bjStr + ' (北京时间)');
console.log('  UTC: ' + stamp);
console.log('  SVG 钟表: ' + svg.length + ' 字符');
console.log('  信标: ' + beaconUrl.slice(0, 90));
console.log('  大小: ' + html.length + ' B');
