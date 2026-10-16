/**
 * worker.js —— Cloudflare Worker：渡口的"安全大脑"（key 放在服务端）
 *
 * 为什么需要它：
 *   浏览器里的 API Key = 公开的 Key。想在网页上用自己（要钱）的模型，
 *   必须让 key 待在服务器，浏览器只调你自己的接口。
 *
 * 部署（免费额度够用，5 分钟）：
 *   1) 注册 cloudflare.com → Workers & Pages → 创建 Worker
 *   2) 把本文件内容粘进去，Deploy
 *   3) Worker 设置里加环境变量：DEEPSEEK_KEY = sk-xxxx   （Secret，加密存储）
 *   4) 把 Worker 地址填回 index.html 的 MY_PROXY
 *
 * 内置保护（你说的"审计/隐私/防滥用"）：
 *   - Origin 白名单：只允许你的站点调用
 *   - 每 IP 限流：防止有人拿你的接口当免费 API 刷
 *   - 只走白名单目的地（服务端二次校验，防篡改）
 *   - 不记录用户原文（隐私）；只记计数（审计）
 */

const ALLOW_ORIGIN = [
  'https://sandmanklepfer-crypto.github.io',
  'http://127.0.0.1:8200',
  'http://localhost:8200',
];

const DESTS = ['yikoucha','fruit3','game','join','orders','chat'];
const RATE = new Map();          // IP -> {n, t}
const LIMIT_PER_MIN = 20;

function cors(origin){
  const allow = ALLOW_ORIGIN.includes(origin) ? origin : ALLOW_ORIGIN[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };
}

export default {
  async fetch(req, env) {
    const origin = req.headers.get('Origin') || '';
    const h = cors(origin);

    if (req.method === 'OPTIONS') return new Response(null, { headers: h });
    if (req.method !== 'POST') return json({ error: 'POST only' }, 405, h);

    // ① Origin 白名单
    if (!ALLOW_ORIGIN.includes(origin)) return json({ error: 'forbidden origin' }, 403, h);

    // ② 限流（每 IP 每分钟）
    const ip = req.headers.get('CF-Connecting-IP') || 'unknown';
    const now = Date.now();
    const r = RATE.get(ip) || { n: 0, t: now };
    if (now - r.t > 60000) { r.n = 0; r.t = now; }
    r.n++; RATE.set(ip, r);
    if (r.n > LIMIT_PER_MIN) return json({ error: 'rate limited' }, 429, h);

    // ③ 解析请求
    let body;
    try { body = await req.json(); } catch (e) { return json({ error: 'bad json' }, 400, h); }
    const text = String(body.text || '').slice(0, 300);

    // ④ 调模型（key 只在服务端）
    const menu = DESTS.join(', ');
    const sys = `你是"渡口"，把用户一句话送到该去的地方。只能从这menu里选slug: ${menu}。
最多3个，按相关度排序。说不清就route空数组并反问。只输出JSON: {"reply":"≤30字","route":["slug"]}`;

    const r2 = await fetch('https://api.deepseek.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + env.DEEPSEEK_KEY },
      body: JSON.stringify({ model: 'deepseek-chat', temperature: 0.3,
        messages: [{ role: 'system', content: sys }, { role: 'user', content: text }] })
    });
    if (!r2.ok) return json({ error: 'upstream ' + r2.status }, 502, h);
    const raw = (await r2.json()).choices[0].message.content;

    // ⑤ 服务端二次校验：route 必须是白名单内的 slug
    let out = { reply: '', destinations: [] };
    const m = raw.match(/\{[\s\S]*\}/);
    if (m) {
      try {
        const j = JSON.parse(m[0]);
        out.reply = String(j.reply || '').slice(0, 60);
        out.destinations = (j.route || []).filter(s => DESTS.includes(s)).slice(0, 3);
      } catch (e) {}
    }
    // 审计：只记时间/结果，不记用户原文（隐私）
    console.log(JSON.stringify({ t: now, ip_h: await hash(ip), n: out.destinations.length }));
    return json(out, 200, h);
  }
};

function json(o, code, h) {
  return new Response(JSON.stringify(o), { status: code,
    headers: { ...h, 'Content-Type': 'application/json; charset=utf-8' } });
}
async function hash(s) {   // 只存哈希，不存原始 IP（隐私）
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].slice(0, 6).map(x => x.toString(16).padStart(2, '0')).join('');
}
