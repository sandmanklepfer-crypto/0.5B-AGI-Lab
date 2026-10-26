/* ==========================================================================
 *  Cloudflare Worker：URL 触发 → MQTT
 *  --------------------------------------------------------------------------
 *  这就是用户说的「访问即触发」的服务端。
 *
 *  部署后得到 https://xxx.workers.dev，然后：
 *    GET  /trigger?token=SECRET&cmd=ping
 *    GET  /trigger?token=SECRET&svc=echo&op=ping
 *    GET  /trigger?token=SECRET&ops=<base64 的批量 JSON>
 *
 *  它做的事：收到 GET → 连 MQTT over WebSocket → publish → 短等 reply → 返回 JSON
 *
 *  ★ 这样纯文本 AI 只要有「访问网页」的能力，访问一下就等于发指令，
 *    而且能在返回的 JSON 里看到结果。
 *
 *  部署步骤（2 分钟，免费，无需信用卡）：
 *    1. cloudflare.com 注册 → Workers & Pages → Create Worker
 *    2. 把本文件全部内容粘进去 → Deploy
 *    3. 在 Settings → Variables 加一个 TRIGGER_TOKEN=你自己的随机串
 *    4. 得到 https://xxx.workers.dev
 * ========================================================================== */

const BROKER = 'wss://broker.hivemq.com:8884/mqtt';

/* ---------- 极简 MQTT over WebSocket（Workers 里没有 npm，手写） ---------- */
function encStr(s) {
  const b = new TextEncoder().encode(s);
  const o = new Uint8Array(b.length + 2);
  o[0] = b.length >> 8; o[1] = b.length & 255; o.set(b, 2);
  return o;
}
function encLen(n) {
  const o = [];
  do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; o.push(d); } while (n > 0);
  return new Uint8Array(o);
}
function packet(t, body) {
  const l = encLen(body.length);
  const o = new Uint8Array(1 + l.length + body.length);
  o[0] = t; o.set(l, 1); o.set(body, 1 + l.length);
  return o;
}
function join(ps) {
  let n = 0; for (const p of ps) n += p.length;
  const o = new Uint8Array(n); let k = 0;
  for (const p of ps) { o.set(p, k); k += p.length; }
  return o;
}

async function mqttOnce(chan, payload, opts = {}) {
  const { timeoutMs = 12000, batch = false } = opts;
  const NS = 'zhz/pulse/' + chan + '/';
  const rid = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  const cid = 'cw' + Math.random().toString(36).slice(2, 8);

  const url = BROKER.replace('wss://', 'https://');
  const ws = new WebSocket(url, 'mqtt');
  ws.binaryType = 'arraybuffer';

  return new Promise((resolve) => {
    let ready = false, done = false;
    const t = setTimeout(() => { if (!done) { done = true; try { ws.close(); } catch (e) {} resolve({ ok: false, error: 'timeout' }); } }, timeoutMs);

    ws.onopen = () => {
      ws.send(packet(0x10, join([encStr('MQTT'), new Uint8Array([4, 2, 0, 60]), encStr(cid)])));
    };

    ws.onmessage = (ev) => {
      const buf = new Uint8Array(ev.data);
      let i = 0;
      while (i < buf.length) {
        const type = buf[i] >> 4;
        let len = 0, mult = 1, j = i + 1;
        while (true) { const b = buf[j++]; len += (b & 127) * mult; if (!(b & 128)) break; mult *= 128; }
        const body = buf.subarray(j, j + len);

        if (type === 2) {
          ready = true;
          /* 订阅 reply */
          ws.send(packet(0x82, join([new Uint8Array([0, 1]), encStr(NS + 'reply'), new Uint8Array([0])])));
          setTimeout(() => {
            const topic = NS + (batch ? 'batch' : 'invoke');
            ws.send(packet(0x30, join([encStr(topic), new TextEncoder().encode(JSON.stringify(payload))])));
          }, 400);
        } else if (type === 3) {
          const tl = (body[0] << 8) | body[1];
          const topic = new TextDecoder().decode(body.subarray(2, 2 + tl));
          if (topic === NS + 'reply') {
            try {
              const o = JSON.parse(new TextDecoder().decode(body.subarray(2 + tl)));
              if (o.request_id === rid && !done) {
                done = true; clearTimeout(t);
                try { ws.close(); } catch (e) {}
                resolve(o);
              }
            } catch (e) {}
          }
        }
        i = j + len;
      }
    };

    ws.onerror = () => { if (!done) { done = true; clearTimeout(t); resolve({ ok: false, error: 'ws error' }); } };
  }).then(async (r) => { await new Promise(x => setTimeout(x, 50)); return r; });
}

/* ---------- Worker 入口 ---------- */
export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    const cors = {
      'Access-Control-Allow-Origin': '*',
      'Content-Type': 'application/json; charset=utf-8',
    };

    if (u.pathname === '/' || u.pathname === '/health') {
      return new Response(JSON.stringify({
        ok: true,
        service: 'PulseOS Trigger Worker',
        usage: {
          single: '/trigger?token=SECRET&svc=echo&op=ping',
          batch: '/trigger?token=SECRET&ops=<base64 JSON array>',
        },
      }, null, 2), { headers: cors });
    }

    if (u.pathname !== '/trigger') {
      return new Response(JSON.stringify({ ok: false, error: 'not found' }), { status: 404, headers: cors });
    }

    /* 鉴权 —— ★ 必须有，否则任何人点一下就触发 */
    const token = u.searchParams.get('token') || '';
    const want = env.TRIGGER_TOKEN || '';
    if (!want) {
      return new Response(JSON.stringify({ ok: false, error: 'Worker 未配置 TRIGGER_TOKEN' }), { status: 500, headers: cors });
    }
    if (token !== want) {
      return new Response(JSON.stringify({ ok: false, error: 'token 不对' }), { status: 403, headers: cors });
    }

    const chan = env.PULSE_CHAN || 'p5k2m';
    const rid = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

    /* 批量 */
    const opsB64 = u.searchParams.get('ops');
    if (opsB64) {
      let ops;
      try { ops = JSON.parse(atob(opsB64)); } catch (e) {
        return new Response(JSON.stringify({ ok: false, error: 'ops 不是合法 base64 JSON' }), { status: 400, headers: cors });
      }
      if (!Array.isArray(ops) || ops.length > 500) {
        return new Response(JSON.stringify({ ok: false, error: 'ops 必须是数组且 ≤500 条' }), { status: 400, headers: cors });
      }
      const r = await mqttOnce(chan, { request_id: rid, ops }, { batch: true });
      return new Response(JSON.stringify(r, null, 2), { headers: cors });
    }

    /* 单次 */
    const svc = u.searchParams.get('svc') || 'echo';
    const op = u.searchParams.get('op') || 'ping';
    let args = [];
    const a = u.searchParams.get('args');
    if (a) { try { args = JSON.parse(a); } catch (e) { args = [a]; } }

    const r = await mqttOnce(chan, {
      request_id: rid, capability: 'invoke',
      params: { service: svc, op, args },
    });
    return new Response(JSON.stringify(r, null, 2), { headers: cors });
  },
};
