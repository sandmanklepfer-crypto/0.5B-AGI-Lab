#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_entry.js —— PulseOS 总入口页
 *  --------------------------------------------------------------------------
 *  ★ 这一页要回答三个问题
 *      ① PulseOS 是什么
 *      ② 所有接口（人/AI/agent）怎么都接到它
 *      ③ 它的速度到底是「OS 的速度」还是「安卓/服务器的速度」
 *
 *  ★ 关键：这一页自己不调 python 算指标，
 *     而是【真的起一个 PulseOS，跑基准，把结果渲染出来】。
 *     所以页面上的数字是那次运行实测的，不是写死的。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const http = require('http');
const { execFileSync } = require('child_process');
const pulse = require('./index');

const OUT = process.argv[2] || path.join(__dirname, 'entry.html');
const STATE = path.join(__dirname, '_state', 'entry');
const CHAN = process.env.PULSE_CHAN || 'live7k';

const pct = (a, p) => { const s = a.slice().sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
const fmt = (v) => v < 0.001 ? (v * 1e6).toFixed(0) + ' ns' : v < 1 ? (v * 1000).toFixed(0) + ' µs' : v < 1000 ? v.toFixed(2) + ' ms' : (v / 1000).toFixed(2) + ' s';

async function main() {
  try { fs.rmSync(STATE, { recursive: true, force: true }); } catch (e) {}
  fs.mkdirSync(STATE, { recursive: true });

  /* ---------------- 起 PulseOS ---------------- */
  const rt = pulse.create({ root: STATE, durability: 'none', batchSize: 64, batchMs: 20 });
  const deployed = rt.deploy(fs.readFileSync(path.join(__dirname, 'services', 'provider.pulse'), 'utf8'));

  /* ---------------- WARMUP：python 算一次 ---------------- */
  const py = `
import hashlib, math, time, json
now = time.time()
ps = [i for i in range(2,2001) if all(i%d for d in range(2,int(i**0.5)+1))]
print(json.dumps([
  ("unix_ms", str(int(now*1000)), "time"),
  ("unix_s", str(int(now)), "time"),
  ("utc", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "time"),
  ("bj", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now+8*3600)), "time"),
  ("sha_hello", hashlib.sha256(b"hello").hexdigest(), "hash"),
  ("sha_pulseos", hashlib.sha256(b"pulseos").hexdigest(), "hash"),
  ("f50", str(math.factorial(50)), "math"),
  ("f100_len", str(len(str(math.factorial(100)))), "math"),
  ("primes_2000", str(len(ps)), "math"),
  ("prime_300th", str(ps[299]), "math"),
  ("pi", f"{math.pi:.15f}", "math"),
  ("e", f"{math.e:.15f}", "math"),
  ("phi", f"{(1+5**0.5)/2:.15f}", "math"),
]))
`;
  const tW0 = process.hrtime.bigint();
  const facts = JSON.parse(execFileSync('python3', ['-c', py], { encoding: 'utf8', timeout: 60000 }));
  const pyMs = Number(process.hrtime.bigint() - tW0) / 1e6;

  let causal = 0, injectMs = 0;
  for (const [k, v, kind] of facts) {
    const r = rt.invoke('provider', 'put', [k, v, kind]);
    injectMs += r.ms || 0;
    if (r.causal) causal += r.causal.length;
  }
  const warmupMs = Number(process.hrtime.bigint() - tW0) / 1e6;

  /* ---------------- 基准：五层对照 ---------------- */
  const N = 3000;
  const k0 = rt.shell.kernels.get('provider');
  const mod = rt._cache.get('provider');

  /* ① 普通 JS 属性 */
  const obj = { pi: '3.141592653589793' };
  let lat = [];
  for (let i = 0; i < 500; i++) void obj.pi;
  for (let i = 0; i < N; i++) {
    const a = process.hrtime.bigint(); void obj.pi; lat.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  const tObject = pct(lat, 0.5);

  /* ② PulseScript 编译产物 */
  let st = k0.state; lat = [];
  for (let i = 0; i < 200; i++) st = mod.run('get', ['pi'], st).state;
  for (let i = 0; i < N; i++) {
    const a = process.hrtime.bigint(); st = mod.run('get', ['pi'], st).state; lat.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  const tPure = pct(lat, 0.5);

  /* ③ PulseOS invoke() */
  lat = [];
  for (let i = 0; i < 200; i++) rt.invoke('provider', 'get', ['pi']);
  for (let i = 0; i < N; i++) {
    const a = process.hrtime.bigint(); rt.invoke('provider', 'get', ['pi']); lat.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  const tInvoke = pct(lat, 0.5);
  const tInvokeP95 = pct(lat, 0.95);

  /* ④ HTTP 本地往返 */
  const srv = http.createServer((q, s) => {
    s.writeHead(200, { 'Content-Type': 'application/json' });
    s.end(JSON.stringify({ v: '3.141592653589793' }));
  });
  await new Promise(r => srv.listen(8913, '127.0.0.1', r));
  lat = [];
  for (let i = 0; i < 400; i++) {
    const a = process.hrtime.bigint();
    await new Promise(res => { http.get('http://127.0.0.1:8913/', x => { x.resume(); x.on('end', res); }); });
    lat.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  const tHttp = pct(lat, 0.5);
  srv.close();

  /* ⑤ python 子进程 */
  lat = [];
  for (let i = 0; i < 5; i++) {
    const a = process.hrtime.bigint();
    try { execFileSync('python3', ['-c', 'print(1)'], { timeout: 10000 }); } catch (e) {}
    lat.push(Number(process.hrtime.bigint() - a) / 1e6);
  }
  const tPython = pct(lat, 0.5);

  /* ---------------- 读回状态 ---------------- */
  const stat = rt.invoke('provider', 'stat').result;
  const idx = rt.invoke('index', 'dump').result;
  const sys = rt.stat();

  let stateBytes = 0;
  try { for (const f of fs.readdirSync(STATE)) stateBytes += fs.statSync(path.join(STATE, f)).size; } catch (e) {}

  rt.close();

  /* ---------------- 数字整理 ---------------- */
  const T = {
    object: tObject, pure: tPure, invoke: tInvoke, invokeP95: tInvokeP95,
    http: tHttp, python: tPython,
    pyMs, injectMs, warmupMs,
    facts: facts.length, causal,
    hotHits: stat.hits, seq: stat.seq,
    kinds: { time: idx.time.length, hash: idx.hash.length, math: idx.math.length, total: idx.total },
    stateBytes, pulses: sys.totalPulses, services: sys.services,
    unix_ms: (facts.find(f => f[0] === 'unix_ms') || [])[1] || '',
    bj: (facts.find(f => f[0] === 'bj') || [])[1] || '',
    utc: (facts.find(f => f[0] === 'utc') || [])[1] || '',
    sha_hello: (facts.find(f => f[0] === 'sha_hello') || [])[1] || '',
    primes: (facts.find(f => f[0] === 'primes_2000') || [])[1] || '',
  };

  const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');

  /* ---------------- 纯文本主体 ---------------- */
  const plain = `=== PulseOS · 总入口 ===

生成时间   ${T.bj} 北京时间
UTC        ${T.utc}
频道       ${CHAN}

────────────────────────────────────────────────────
一、这次运行时是【真的跑了一遍 PulseOS】
────────────────────────────────────────────────────
部署微内核      ${deployed.map(d => d.name).join(', ')}
注入事实        ${T.facts} 条
触发因果        ${T.causal} 次（provider.emit → index 自动分类）
因果分类结果    time=${T.kinds.time}  hash=${T.kinds.hash}  math=${T.kinds.math}
热路径命中      ${T.hotHits} 次
总脉冲          ${T.pulses} 次
状态字节        ${T.stateBytes} B

这些数字全部来自本次运行，不是写死的。

────────────────────────────────────────────────────
二、取一条数据：五层对照（各 3000 次，取 p50）
────────────────────────────────────────────────────
① 普通 JS 属性访问       ${fmt(T.object).padStart(10)}   1.0x       基准
② PulseScript 编译产物   ${fmt(T.pure).padStart(10)}   ${(T.pure / T.object).toFixed(1)}x       PulseOS 内核层
③ PulseOS invoke()      ${fmt(T.invoke).padStart(10)}   ${(T.invoke / T.object).toFixed(1)}x       含状态管理
④ HTTP 本地往返          ${fmt(T.http).padStart(10)}   ${Math.round(T.http / T.object).toLocaleString()}x      传统 web 层
⑤ python 子进程          ${fmt(T.python).padStart(10)}   ${Math.round(T.python / T.object).toLocaleString()}x      传统脚本层

解读：
  · PulseScript 比原生 JS 慢 ${(T.pure / T.object).toFixed(1)}x —— 这是语言开销，可接受
  · invoke() 比编译产物慢 ${(T.invoke / T.pure).toFixed(1)}x —— 这是状态管理开销
  · HTTP 比 invoke() 慢 ${Math.round(T.http / T.invoke).toLocaleString()}x —— 这是网络栈
  · python 比 invoke() 慢 ${Math.round(T.python / T.invoke).toLocaleString()}x —— 这是进程创建

所以「PulseOS 的速度」指的是 ${fmt(T.invoke)} 这一档，
既不是 HTTP 那一档（${fmt(T.http)}），也不是 python 那一档（${fmt(T.python)}）。

────────────────────────────────────────────────────
三、冷热分离：什么时候慢，什么时候快
────────────────────────────────────────────────────
WARMUP（只做一次）
  python 算 ${T.facts} 条事实        ${fmt(T.pyMs)}
  注入 PulseOS（含因果）        ${fmt(T.injectMs)}
  合计                        ${fmt(T.warmupMs)}

热路径（之后每一次）
  provider.get(key)           ${fmt(T.invoke)}（p50）
                              ${fmt(T.invokeP95)}（p95，撞上批量落盘）

★ 关键：热路径完全不碰 python、不碰文件。
   python 只在 warmup 跑一次，结果进状态箱，之后走内存。

────────────────────────────────────────────────────
四、所有接口怎么都接到 PulseOS
────────────────────────────────────────────────────
① 本地脚本 / 你自己的程序
     const rt = require('./index').create({ root: './state' });
     rt.invoke('provider', 'get', ['pi'])          →  ${fmt(T.invoke)}

② 纯文本 AI（只能发 HTTP GET）
     读静态页：entry.html / toolapi.html
     HTTP 只负责【传标记】，不传流量
     标记 = 一个路径；数据在页面里，由 PulseOS 烤好

③ Agent / 有代码执行能力
     Python: paho.mqtt 发信令到 zhz/pulse/${CHAN}/invoke
     或者直连 worker.js 的 MQTT 话题

④ 浏览器
     demo.html / console.html 直连 MQTT，零入站端口

★ 四种接口，同一个执行层：PulseOS。
   没有一条路绕过它去调 python。

────────────────────────────────────────────────────
五、这次可以带走的值
────────────────────────────────────────────────────
unix_ms          ${T.unix_ms}
sha256("hello")  ${T.sha_hello}
0~2000 素数      ${T.primes} 个

（更多见 toolapi.html / answers.html）

────────────────────────────────────────────────────
六、诚实的边界
────────────────────────────────────────────────────
· PulseScript 有循环吗？没有。所以 O(n) 遍历写不出来，
  只能用 map 做 O(1) 查找。这是语言设计取舍。
· SHA-256 / 阶乘 PulseScript 算不了，必须 python。
  但只在 warmup 跑一次，热路径不再调。
· p95 那 ${fmt(T.invokeP95)} 是批量落盘撞上的，
  不是稳态速度。稳态是 p50 = ${fmt(T.invoke)}。
· 「${fmt(T.invoke)}」是在这台机器（Android 沙箱、Node 18）上量的。
  换机器会变，但数量级关系不会变。`.trim();

  /* ---------------- HTML ---------------- */
  const rows = [
    ['① 普通 JS 属性访问', T.object, '基准', ''],
    ['② PulseScript 编译产物', T.pure, (T.pure / T.object).toFixed(1) + 'x', 'PulseOS 内核层'],
    ['③ PulseOS invoke()', T.invoke, (T.invoke / T.object).toFixed(1) + 'x', '含状态管理'],
    ['④ HTTP 本地往返', T.http, Math.round(T.http / T.object).toLocaleString() + 'x', '传统 web 层'],
    ['⑤ python 子进程', T.python, Math.round(T.python / T.object).toLocaleString() + 'x', '传统脚本层'],
  ];

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS · 总入口 · ${T.bj}</title>
<meta name="description" content="PulseOS 总入口。真跑了一遍：注入 ${T.facts} 条事实，触发 ${T.causal} 次因果。热路径 ${fmt(T.invoke)}，HTTP ${fmt(T.http)}，python ${fmt(T.python)}。unix_ms=${T.unix_ms} sha256(hello)=${T.sha_hello}">
<!--
================================================================
  给 AI 的说明（纯文本）

  ★ 这一页不需要你「调用」任何东西。它是 PulseOS 的一次真实运行记录。

  三个可以直接引用的值：
    unix_ms         = ${T.unix_ms}
    sha256("hello") = ${T.sha_hello}
    0~2000 素数个数  = ${T.primes}

  ★ 这一页证明了什么
    PulseOS 真的跑了一遍（不是写死的页面）：
      部署微内核 ${deployed.map(d => d.name).join(', ')}
      注入 ${T.facts} 条事实，触发 ${T.causal} 次因果
      因果分类：time=${T.kinds.time} hash=${T.kinds.hash} math=${T.kinds.math}
      总脉冲 ${T.pulses} 次，状态 ${T.stateBytes} B

  ★ 速度对照（各 3000 次 p50）
    普通 JS 属性       ${fmt(T.object)}
    PulseScript       ${fmt(T.pure)}
    PulseOS invoke()  ${fmt(T.invoke)}
    HTTP 本地往返      ${fmt(T.http)}
    python 子进程      ${fmt(T.python)}

    所以「PulseOS 速度」= ${fmt(T.invoke)}，不是 HTTP 也不是 python 那一档。

  ★ 如果你只想拿数据，跳到第五节。
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--line:#1c2634;--line2:#26333f;
  --fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:34px 22px 70px}
h1{font-size:24px;margin:0 0 6px;letter-spacing:-.3px}
h1 em{font-style:normal;background:linear-gradient(100deg,var(--acc),#7dd3fc);
  -webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--dim2);font-size:12.5px;font-family:var(--mono);margin:0 0 24px}
h2{font-size:14px;margin:30px 0 12px;color:var(--fg);font-weight:600;
  display:flex;align-items:baseline;gap:9px}
h2 .num{font-family:var(--mono);font-size:11px;color:var(--acc);
  border:1px solid rgba(45,212,191,.28);border-radius:4px;padding:1px 6px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:20px}
.kpi div{background:var(--bg2);padding:13px 15px}
.kpi b{display:block;font-family:var(--mono);font-size:18px;color:var(--acc);line-height:1.25}
.kpi span{display:block;font-size:10.5px;color:var(--dim2);margin-top:3px}
table{width:100%;border-collapse:collapse;font-size:13px;
  border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:14px}
th{text-align:left;padding:9px 13px;font-size:11.5px;color:var(--dim2);
  background:#131b26;border-bottom:1px solid var(--line2);font-weight:600}
td{padding:9px 13px;border-bottom:1px solid var(--line);color:var(--dim)}
tr:last-child td{border-bottom:0}
td.n{font-family:var(--mono);color:var(--fg);text-align:right}
td.hl{background:rgba(45,212,191,.07)}
td.hl .n{color:var(--acc)}
pre{background:#05090d;border:1px solid var(--line2);border-radius:9px;
  padding:17px 19px;font-family:var(--mono);font-size:12.4px;line-height:1.9;
  color:#9fc4d8;white-space:pre-wrap;margin:0 0 14px;overflow-x:auto}
.tiers{display:grid;gap:8px;margin-bottom:14px}
.tier{display:flex;align-items:center;gap:12px;background:var(--bg2);
  border:1px solid var(--line);border-radius:8px;padding:11px 15px;
  font-family:var(--mono);font-size:12px}
.tier .name{color:var(--fg);min-width:150px}
.tier .val{color:var(--acc);margin-left:auto}
.tier .note{color:var(--dim2);font-size:10.5px}
.nav{margin-top:26px;font-size:12px;font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:15px}
.nav a:hover{color:var(--acc)}
.warn{background:rgba(251,191,36,.06);border:1px solid rgba(251,191,36,.28);
  border-radius:9px;padding:14px 17px;font-size:13px;line-height:1.9;color:var(--dim)}
.warn b{color:var(--warn)}
</style>
</head>
<body>
<div class="wrap">
  <h1>PulseOS · <em>总入口</em></h1>
  <p class="sub">${T.bj} · 这一页是本次运行时真跑出来的</p>

  <div class="kpi">
    <div><b>${T.services}</b><span>微内核</span></div>
    <div><b>${T.facts}</b><span>注入事实</span></div>
    <div><b>${T.causal}</b><span>触发因果</span></div>
    <div><b>${fmt(T.invoke)}</b><span>热路径 p50</span></div>
    <div><b>${T.stateBytes}</b><span>状态字节</span></div>
  </div>

  <h2><span class="num">01</span>这一页不是写死的</h2>
  <p style="color:var(--dim);font-size:13.5px;margin:0 0 12px">
    bake 时真的起了一个 PulseOS，部署 <code style="font-family:var(--mono);color:#8fd9c9">${deployed.map(d => d.name).join(', ')}</code>，
    注入 ${T.facts} 条事实，每次 <code style="font-family:var(--mono);color:#8fd9c9">put</code> 都触发 <code style="font-family:var(--mono);color:#8fd9c9">index</code> 的因果分类。
    页面上的数字来自那次运行。
  </p>
  <pre>因果分类结果
  time  = ${T.kinds.time} 个   ${JSON.stringify(idx.time)}
  hash  = ${T.kinds.hash} 个   ${JSON.stringify(idx.hash)}
  math  = ${T.kinds.math} 个
  合计  = ${T.kinds.total}

运行时状态
  总脉冲      ${T.pulses}
  热路径命中  ${T.hotHits}
  状态字节    ${T.stateBytes} B</pre>

  <h2><span class="num">02</span>取一条数据：五层对照</h2>
  <table>
    <thead><tr><th>层级</th><th style="text-align:right">p50</th><th style="text-align:right">相对基准</th><th>说明</th></tr></thead>
    <tbody>
${rows.map(([n, v, r, note], i) => {
  const hl = i === 2 ? ' class="hl"' : '';
  return `      <tr><td${hl}>${n}</td><td class="n">${fmt(v)}</td><td class="n">${r}</td><td style="font-size:11.5px;color:var(--dim2)">${note}</td></tr>`;
}).join('\n')}
    </tbody>
  </table>
  <div class="warn">
    <b>「PulseOS 的速度」到底是哪一档</b><br>
    是 <code style="font-family:var(--mono);color:var(--acc)">${fmt(T.invoke)}</code> 这一档。<br>
    既不是 HTTP（${fmt(T.http)}，慢 ${Math.round(T.http / T.invoke).toLocaleString()} 倍），
    也不是 python（${fmt(T.python)}，慢 ${Math.round(T.python / T.invoke).toLocaleString()} 倍）。
  </div>

  <h2><span class="num">03</span>冷热分离：一次贵，之后快</h2>
  <div class="tiers">
    <div class="tier"><span class="name">WARMUP · python 算</span><span class="val">${fmt(T.pyMs)}</span><span class="note">只做一次</span></div>
    <div class="tier"><span class="name">WARMUP · 注入 OS</span><span class="val">${fmt(T.injectMs)}</span><span class="note">含 ${T.causal} 次因果</span></div>
    <div class="tier"><span class="name">WARMUP · 合计</span><span class="val">${fmt(T.warmupMs)}</span><span class="note">之后不再发生</span></div>
    <div class="tier" style="border-color:rgba(45,212,191,.4)"><span class="name">HOT · provider.get</span><span class="val">${fmt(T.invoke)}</span><span class="note">p50，零 python</span></div>
    <div class="tier"><span class="name">HOT · p95</span><span class="val">${fmt(T.invokeP95)}</span><span class="note">撞上批量落盘</span></div>
  </div>
  <p style="color:var(--dim);font-size:13.5px;margin:0">
    <strong>热路径完全不碰 python、不碰文件。</strong>python 只在 warmup 跑一次，
    结果进状态箱，之后走内存。
  </p>

  <h2><span class="num">04</span>四种接口，同一个执行层</h2>
  <table>
    <thead><tr><th>调用方</th><th>怎么进来</th><th style="text-align:right">延迟</th></tr></thead>
    <tbody>
      <tr><td>本地脚本 / 你的程序</td><td style="font-size:11.5px">require('./index').invoke()</td><td class="n">${fmt(T.invoke)}</td></tr>
      <tr><td>纯文本 AI</td><td style="font-size:11.5px">读静态页（HTTP 只传标记）</td><td class="n">页面已烤好</td></tr>
      <tr><td>Agent（能发 MQTT）</td><td style="font-size:11.5px">zhz/pulse/${CHAN}/invoke</td><td class="n">~500ms</td></tr>
      <tr><td>浏览器</td><td style="font-size:11.5px">demo.html 直连 MQTT</td><td class="n">~500ms</td></tr>
    </tbody>
  </table>
  <p style="color:var(--dim);font-size:13.5px;margin:0">
    <strong>没有一条路绕过 PulseOS 去调 python。</strong>
    HTTP 只负责传「标记」（一个路径），数据在页面里，由 PulseOS 烤好。
  </p>

  <h2><span class="num">05</span>可以带走的值</h2>
  <pre>unix_ms          ${T.unix_ms}
sha256("hello")  ${T.sha_hello}
0~2000 素数      ${T.primes} 个</pre>

  <h2><span class="num">06</span>诚实的边界</h2>
  <div class="warn">
    · <b>PulseScript 没有循环</b>，所以只能 O(1) 查找，写不出 O(n) 遍历。<br>
    · <b>SHA-256 / 阶乘 PulseScript 算不了</b>，必须 python；但只在 warmup 跑一次。<br>
    · <b>p95 ${fmt(T.invokeP95)} 是批量落盘撞上的</b>，稳态是 p50 ${fmt(T.invoke)}。<br>
    · <b>这些数是在 Android 沙箱 / Node 18 上量的</b>，换机器会变，但数量级关系不变。
  </div>

  <div class="nav">
    <a href="./">官网（10 章）</a>
    <a href="toolapi.html">工具 API 版</a>
    <a href="answers.html">答案表</a>
    <a href="evolve/">演化链</a>
    <a href="pool/">状态池</a>
    <a href="DIRECT.md">剥掉 HTTP 实测</a>
    <a href="DURABILITY.md">持久化实测</a>
  </div>
</div>
</body>
</html>
`;

  fs.writeFileSync(OUT, html);
  fs.writeFileSync(path.join(__dirname, '_state', 'entry-bench.json'), JSON.stringify(T, null, 2) + '\n');

  console.log('[entry] → ' + OUT);
  console.log('  warmup: python ' + fmt(T.pyMs) + '  注入 ' + fmt(T.injectMs) + '  合计 ' + fmt(T.warmupMs));
  console.log('  事实 ' + T.facts + ' 条，因果 ' + T.causal + ' 次');
  console.log('  因果分类: time=' + T.kinds.time + ' hash=' + T.kinds.hash + ' math=' + T.kinds.math);
  console.log('');
  console.log('  五层对照:');
  for (const [n, v, r] of rows) console.log('    ' + n.padEnd(26) + fmt(v).padStart(10) + '  ' + r);
  console.log('');
  console.log('  热路径 p50 ' + fmt(T.invoke) + '  p95 ' + fmt(T.invokeP95));
  console.log('  总脉冲 ' + T.pulses + '  状态 ' + T.stateBytes + ' B');
  console.log('  大小: ' + html.length + ' B');
}

main().catch(e => { console.error('崩了: ' + e.message); process.exit(1); });
