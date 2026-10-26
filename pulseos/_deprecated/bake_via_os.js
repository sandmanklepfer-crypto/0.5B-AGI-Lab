#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  bake_via_os.js —— 真正跑在 PulseOS 上的页面
 *  --------------------------------------------------------------------------
 *  ★ 修正的问题
 *    之前的 8 个 bake_*.js 全部直接 execFileSync('python3')，
 *    完全没有用到 PulseOS —— 页面是「自己算完写死」，跟 OS 割裂。
 *
 *  ★ 现在的分工（这才是你说的「基于那个 OS」）
 *
 *      Python        负责「算准」（SHA-256、素数、阶乘）
 *                     ↓ 事实以 {key, kind} 形式注入
 *      PulseOS       负责「记住 + 派生 + 持久化」
 *                     · facts 微内核登记每条事实
 *                     · emit fact_added → agg 微内核自动聚合
 *                     · 状态箱落盘（可用 WAL/批量/同步）
 *                     · 因果链自己跑，不是脚本手工拼
 *      bake          只负责把 PulseOS 的最终状态渲染成 HTML
 *
 *  ★ 页面上要能看出「哪些是 Python 算的」「哪些是 PulseOS 算的」
 *    所以每段数字都标注来源。
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const pulse = require('./index');

const OUT = process.argv[2] || path.join(__dirname, 'os.html');
const STATE_DIR = process.argv[3] || path.join(__dirname, '_state', 'bake');
const CHAN = process.env.PULSE_CHAN || 'live7k';

/* ---------------- ① Python 算事实 ---------------- */
const py = `
import hashlib, math, time, json
now = time.time()
ps = [i for i in range(2,2001) if all(i%d for d in range(2,int(i**0.5)+1))]
print(json.dumps({
  "unix_ms": int(now*1000),
  "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
  "bj": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now+8*3600)),
  "sha_hello": hashlib.sha256(b"hello").hexdigest(),
  "f50_len": len(str(math.factorial(50))),
  "f100_len": len(str(math.factorial(100))),
  "primes_2000": len(ps),
  "pi": f"{math.pi:.15f}",
}))
`;
const tPy0 = Date.now();
const F = JSON.parse(execFileSync('python3', ['-c', py], { encoding: 'utf8', timeout: 60000 }));
const pyMs = Date.now() - tPy0;

/* ---------------- ② 起 PulseOS，部署微内核 ---------------- */
const tOs0 = Date.now();

/* 用干净的状态目录（每次 bake 重建，保证可重复） */
try { fs.rmSync(STATE_DIR, { recursive: true, force: true }); } catch (e) {}
fs.mkdirSync(STATE_DIR, { recursive: true });

const rt = pulse.create({
  root: STATE_DIR,
  durability: 'batch',
  batchSize: 8,
  batchMs: 10,
});

const deployed = rt.deploy(fs.readFileSync(path.join(__dirname, 'services', 'facts.pulse'), 'utf8'));

/* ---------------- ③ 把事实注入 PulseOS（触发因果链） ---------------- */
const FACT_LIST = [
  ['unix_ms', 'time', String(F.unix_ms)],
  ['utc', 'time', F.utc],
  ['bj', 'time', F.bj],
  ['sha_hello', 'hash', F.sha_hello],
  ['f50_len', 'math', String(F.f50_len)],
  ['f100_len', 'math', String(F.f100_len)],
  ['primes_2000', 'math', String(F.primes_2000)],
  ['pi', 'math', F.pi],
];

const injectTraces = [];
let pulses = 0;
const lat = [];

for (const [k, kind, v] of FACT_LIST) {
  const r = rt.invoke('facts', 'add', [k, kind]);
  pulses++;
  if (r.ok) lat.push(r.ms);
  injectTraces.push({
    key: k, kind,
    ms: r.ms,
    causal: (r.causal || []).map(c => ({
      to: c.to, op: c.op, ok: c.ok, ms: c.ms, result: c.result,
    })),
  });
}

/* ---------------- ④ 从 PulseOS 读回状态 ---------------- */
const factsRep = rt.invoke('facts', 'report');
const aggRep = rt.invoke('agg', 'report');
pulses += 2;

const factsState = factsRep.result || { count: 0, items: [] };
const aggState = aggRep.result || { n: 0, kinds: [], keylen: 0 };

const sysInfo = rt.stat();

/* 状态箱大小（PulseOS 的核心指标） */
let stateBytes = 0;
try {
  for (const f of fs.readdirSync(STATE_DIR)) {
    if (f.endsWith('.box') || f.endsWith('.wal')) {
      stateBytes += fs.statSync(path.join(STATE_DIR, f)).size;
    }
  }
} catch (e) {}

rt.close();
const osMs = Date.now() - tOs0;

/* 状态箱指纹（证明这是真落盘的状态） */
let stateHash = '(无)';
try {
  const h = crypto.createHash('sha256');
  for (const f of fs.readdirSync(STATE_DIR).sort()) {
    if (f.endsWith('.box') || f.endsWith('.wal')) {
      h.update(fs.readFileSync(path.join(STATE_DIR, f)));
    }
  }
  stateHash = h.digest('hex');
} catch (e) {}

/* ---------------- ⑤ 纯文本主体 ---------------- */
const plain = [
  '=== PulseOS 实跑结果 ===',
  '',
  `生成时间      ${F.bj} 北京时间`,
  `UTC          ${F.utc}`,
  '',
  '────────────────────────────────────────',
  '① Python 算的（PulseOS 不负责算）',
  '────────────────────────────────────────',
  `unix_ms        ${F.unix_ms}`,
  `sha256("hello") ${F.sha_hello}`,
  `50! 位数        ${F.f50_len}`,
  `100! 位数       ${F.f100_len}`,
  `0~2000 素数个数  ${F.primes_2000}`,
  `π              ${F.pi}`,
  '',
  '────────────────────────────────────────',
  '② PulseOS 算的（这才是「基于 OS」）',
  '────────────────────────────────────────',
  `部署的微内核     ${deployed.map(d => d.name).join(', ')}`,
  `注入事实条数     ${factsState.count} 条`,
  '',
  '  因果链（facts.emit → agg.fact_added，OS 自动派发）：',
  ...injectTraces.map(t => {
    const c = t.causal.length
      ? t.causal.map(x => `${x.to}.${x.op} ${x.ms.toFixed(2)}ms`).join(', ')
      : '（无下游）';
    return `    ${t.key.padEnd(14)} ${t.kind.padEnd(6)} → ${c}`;
  }),
  '',
  '  ⤷ agg 微内核的最终状态（PulseOS 聚合出来的）：',
  `     n        ${aggState.n}   （收到了 ${aggState.n} 次 fact_added）`,
  `     kinds    ${JSON.stringify(aggState.kinds)}   （自动去重）`,
  `     keylen   ${aggState.keylen}   （各 key 字符数之和）`,
  '',
  '────────────────────────────────────────',
  '③ PulseOS 的运行时数据',
  '────────────────────────────────────────',
  `微内核数        ${sysInfo.services}`,
  `总脉冲次数       ${sysInfo.totalPulses}`,
  `状态字节        ${sysInfo.totalStateBytes} B`,
  `因果边          ${aggState.n} 条`,
  '',
  `持久化模式      ${rt.durability}`,
  `落盘文件大小     ${stateBytes} B`,
  `状态箱指纹       ${stateHash}`,
  '',
  '────────────────────────────────────────',
  '④ 耗时拆解',
  '────────────────────────────────────────',
  `Python 算事实    ${pyMs} ms`,
  `PulseOS 全流程   ${osMs} ms`,
  `  其中注入 ${FACT_LIST.length} 条   ${injectTraces.reduce((a, t) => a + (t.ms || 0), 0).toFixed(2)} ms`,
  '',
  '────────────────────────────────────────',
  '这一页和之前那些页面有什么不同',
  '────────────────────────────────────────',
  '之前：bake 脚本直接调 python，算完写死进 HTML，PulseOS 完全没参与。',
  '现在：python 只负责算，事实注入 PulseOS 的 facts 微内核，',
  '      emit 触发 agg 微内核自动聚合，状态落盘，然后才渲染。',
  '',
  '所以上面「②」和「③」的数字，是 PulseOS 运行时真算出来的，',
  '不是 bake 脚本拼出来的字符串。',
  '',
  `验证：状态箱指纹 ${stateHash.slice(0, 32)}…`,
  '      这个指纹来自磁盘上真实的 .box/.wal 文件。',
].join('\n');

const esc = (x) => String(x).replace(/&/g, '&amp;').replace(/</g, '&lt;');

/* ---------------- ⑥ HTML ---------------- */
const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PulseOS 实跑 · ${F.bj}</title>
<meta name="description" content="PulseOS 实跑结果。Python 算 ${FACT_LIST.length} 条事实，注入 PulseOS 的 facts 微内核，emit 触发 agg 自动聚合。agg.n=${aggState.n}，kinds=${aggState.kinds.join('/')}，状态 ${sysInfo.totalStateBytes}B。unix_ms=${F.unix_ms} sha256(hello)=${F.sha_hello}">
<!--
================================================================
  给 AI 的说明（纯文本）

  ★ 这一页不是「脚本算完写死」，是真的跑了 PulseOS。

  分工：
    Python   负责算准（SHA-256 / 素数 / 阶乘）
    PulseOS  负责记住、派生因果、聚合、持久化
    bake     只负责渲染

  ★ PulseOS 实际做了什么
    1. 部署两个微内核：${deployed.map(d => d.name).join(', ')}
    2. facts 微内核登记 ${factsState.count} 条事实
       每次 add 都 emit "fact_added"
    3. PulseOS 的因果派发器把 emit 路由到 agg 微内核
       agg 自动累加 n、去重 kinds、累加 keylen
    4. 状态落盘（${stateBytes} B），指纹 ${stateHash.slice(0, 32)}…

  ★ PulseOS 算出来的（不是脚本拼的）
    agg.n      = ${aggState.n}
    agg.kinds  = ${JSON.stringify(aggState.kinds)}
    agg.keylen = ${aggState.keylen}
    总脉冲     = ${sysInfo.totalPulses}
    状态字节   = ${sysInfo.totalStateBytes} B

  ★ 可以直接用的值
    unix_ms = ${F.unix_ms}
    sha256("hello") = ${F.sha_hello}
    0~2000 素数 = ${F.primes_2000}
    50! 位数 = ${F.f50_len}，100! 位数 = ${F.f100_len}
    π = ${F.pi}

  ★ 怎么验证
    状态箱在仓库的 pulseos/_state/bake/ 目录，
    指纹 ${stateHash.slice(0, 32)}… 是把所有 .box/.wal 拼接后算的 SHA-256。
================================================================
-->
<style>
:root{--bg:#0b0f14;--bg2:#0f151d;--fg:#dde7f0;--dim:#8fa3b8;--dim2:#5d7085;
  --acc:#2dd4bf;--ok:#4ade80;--warn:#fbbf24;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14.5px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:30px 22px 70px}
h1{font-size:21px;margin:0 0 4px}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--dim2);font-size:12px;font-family:var(--mono);margin:0 0 20px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1px;
  background:#1c2634;border:1px solid #1c2634;border-radius:10px;overflow:hidden;margin:0 0 18px}
.kpi div{background:var(--bg2);padding:13px 15px}
.kpi b{display:block;font-family:var(--mono);font-size:19px;color:var(--acc);line-height:1.25}
.kpi span{display:block;font-size:10.5px;color:var(--dim2);margin-top:3px}
pre{background:#05090d;border:1px solid #26333f;border-radius:9px;
  padding:17px 19px;font-family:var(--mono);font-size:12.4px;line-height:1.9;
  color:#9fc4d8;white-space:pre-wrap;margin:0 0 16px;overflow-x:auto}
.chain{display:flex;flex-direction:column;gap:6px;margin-bottom:16px}
.chain .row{display:flex;align-items:center;gap:9px;font-family:var(--mono);
  font-size:11.5px;background:var(--bg2);border:1px solid #1c2634;
  border-radius:7px;padding:9px 13px;flex-wrap:wrap}
.chain .k{color:#fbbf24}
.chain .arrow{color:var(--dim2)}
.chain .t{color:var(--acc)}
.chain .ms{color:var(--dim2);margin-left:auto}
.nav{margin-top:20px;font-size:12px;font-family:var(--mono)}
.nav a{color:var(--dim);text-decoration:none;margin-right:14px}
.nav a:hover{color:var(--acc)}
</style>
</head>
<body>
<div class="wrap">
  <h1>PulseOS <em>实跑</em></h1>
  <p class="sub">${F.bj} · 真跑 PulseOS（不是脚本算完写死）</p>

  <div class="kpi">
    <div><b>${sysInfo.totalPulses}</b><span>脉冲次数</span></div>
    <div><b>${aggState.n}</b><span>因果边</span></div>
    <div><b>${sysInfo.totalStateBytes}</b><span>状态字节</span></div>
    <div><b>${osMs}</b><span>OS 耗时 ms</span></div>
  </div>

  <pre>${esc(plain)}</pre>

  <div class="nav">
    <a href="./">官网</a>
    <a href="api.html">能力清单</a>
    <a href="toolapi.html">工具 API 版</a>
    <a href="answers.html">旧版答案表</a>
  </div>
</div>
</body>
</html>
`;

fs.writeFileSync(OUT, html);

console.log('[via-os] → ' + OUT);
console.log('  Python 算事实: ' + pyMs + 'ms');
console.log('  PulseOS 全流程: ' + osMs + 'ms');
console.log('  部署微内核: ' + deployed.map(d => d.name).join(', '));
console.log('  注入事实: ' + factsState.count + ' 条');
console.log('  因果触发: ' + aggState.n + ' 次');
console.log('  agg.kinds: ' + JSON.stringify(aggState.kinds));
console.log('  agg.keylen: ' + aggState.keylen);
console.log('  总脉冲: ' + sysInfo.totalPulses);
console.log('  状态字节: ' + sysInfo.totalStateBytes + ' B');
console.log('  状态箱指纹: ' + stateHash.slice(0, 32) + '…');
console.log('  大小: ' + html.length + ' B');
