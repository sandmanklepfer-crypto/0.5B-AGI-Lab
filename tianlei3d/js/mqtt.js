/*
 * 极简 MQTT over WebSocket 客户端（浏览器用，零依赖）
 *
 * 为什么用它：公共 MQTT broker 免注册、免 Token、支持双向实时推送。
 * 这样聊天就不需要任何账号/令牌，也不用来回轮询。
 *
 * 已验证：broker.emqx.io:8084 会回显子协议 'mqtt'，浏览器可正常连接。
 * 协议实现：MQTT 3.1.1，只用 QoS 0（聊天够用，最简单）
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.MiniMqtt = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ★★ 只用一个 broker（不要自动轮换！）
  //   原因：以前会在 hivemq / emqx 之间轮换，导致
  //         (a) 沙箱只能到 hivemq，手机上却可能落到 emqx → 命令行控制不了手机；
  //         (b) 两个玩家各连一个 broker → 彼此永远看不到对方（联机假故障）。
  //   统一个大家都能连的，坏了一起坏，至少不会"看起来在线其实失联"。
  const BROKERS = [
    'wss://broker.hivemq.com:8884/mqtt',
  ];

  function encStr(s) {
    const b = new TextEncoder().encode(s);
    const out = new Uint8Array(b.length + 2);
    out[0] = b.length >> 8; out[1] = b.length & 255;
    out.set(b, 2);
    return out;
  }
  function encLen(n) {
    const out = [];
    do { let d = n % 128; n = Math.floor(n / 128); if (n > 0) d |= 128; out.push(d); } while (n > 0);
    return new Uint8Array(out);
  }
  function packet(type, body) {
    const len = encLen(body.length);
    const out = new Uint8Array(1 + len.length + body.length);
    out[0] = type; out.set(len, 1); out.set(body, 1 + len.length);
    return out;
  }
  function join(parts) {
    let n = 0; for (const p of parts) n += p.length;
    const out = new Uint8Array(n); let o = 0;
    for (const p of parts) { out.set(p, o); o += p.length; }
    return out;
  }
  const rand = n => {
    const a = new Uint8Array(n);
    (self.crypto || self.msCrypto).getRandomValues(a);
    return a;
  };

  function createClient(opts) {
    opts = opts || {};
    const clientId = (opts.clientId || 'zhz') + Math.random().toString(36).slice(2, 8);
    const brokers = opts.brokers || BROKERS;
    let bi = 0;
    let ws = null;
    let ready = false;
    let closed = false;
    let keepTimer = null, retryTimer = null, attempts = 0;
    const subs = new Set();
    const handlers = { connect: [], message: [], close: [], error: [], raw: [] };
    const state = { broker: '' };

    const emit = (ev, a, b) => { (handlers[ev] || []).forEach(f => { try { f(a, b); } catch (e) {} }); };

    // 注意：浏览器的 WebSocket.send() 会自动加 WS 帧（含掩码），
    // 所以这里只传 MQTT 报文本身，绝不能再手工套一层 WS 帧（否则就是双层帧，服务器直接断开）。
    const send = bytes => {
      if (ws && ws.readyState === 1) { try { ws.send(bytes); } catch (e) {} }
    };

    function mqttSend(type, body) { send(packet(type, body)); }

    /* ---- 连接 ---- */
    // 连接代次：每条 socket 有自己的编号，旧 socket 的迟到事件一律丢弃。
    // 【稳定性修复】以前 connect() 建新 socket 前不关旧的，重试时旧连接还活着，
    // 它的 onclose 迟到又触发一次重试 —— 连接像雪球一样越滚越多，
    // 表现就是"时好时坏、偶尔卡住"。现在：先关旧、再建新、代次过滤。
    let gen = 0;
    function connect() {
      if (closed) return;
      const old = ws;
      if (old) {
        try { old.onopen = old.onmessage = old.onerror = old.onclose = null; old.close(); } catch (e) { /* ignore */ }
      }
      const myGen = ++gen;
      const url = brokers[bi % brokers.length];
      state.broker = url;
      let sock;
      try { sock = new WebSocket(url, 'mqtt'); }
      catch (e) { return scheduleRetry(e.message); }
      ws = sock;
      sock.binaryType = 'arraybuffer';

      sock.onopen = () => {
        if (myGen !== gen) return;          // 已被更新的连接取代，忽略
        attempts = 0;
        const vh = join([encStr('MQTT'), new Uint8Array([0x04, 0x02, 0x00, 0x3C])]);
        mqttSend(0x10, join([vh, encStr(clientId)]));
      };
      // 浏览器的 onmessage 给的已经是"剥好 WS 帧"的负载（就是 MQTT 报文本身），
      // 所以不能再剥一次帧；ping/pong 也由浏览器自动处理。
      sock.onmessage = e => { if (myGen === gen) onMqtt(new Uint8Array(e.data)); };
      sock.onerror = () => { if (myGen === gen) emit('error', new Error('WebSocket 出错')); };
      sock.onclose = () => {
        if (myGen !== gen) return;          // 旧连接的关闭事件：不触发重试
        ready = false;
        stopKeep();
        emit('close');
        if (!closed) scheduleRetry('连接关闭');
      };
    }

    function scheduleRetry(why) {
      if (closed) return;
      attempts++;
      // ★ 固定在同一个 broker 上重试（轮换会把玩家拆散，见上）
      const wait = Math.min(1000 * attempts, 8000);
      clearTimeout(retryTimer);
      retryTimer = setTimeout(connect, wait);
    }

    /* ---- 收包 ---- */
    // 处理一个 MQTT 报文（浏览器已剥掉 WS 帧）
    function onMqtt(buf) {
      if (!buf.length) return;
      const type = buf[0] >> 4;
      if (type === 2) {                       // CONNACK
        const rc = buf[3];
        if (rc !== 0) { emit('error', new Error('MQTT 拒绝连接 code=' + rc)); try { ws.close(); } catch (e) {} return; }
        ready = true; attempts = 0;
        startKeep();
        subs.forEach(t => doSub(t));
        emit('connect', state.broker);
        return;
      }
      if (type === 9) return;                 // SUBACK
      if (type === 3) {                       // PUBLISH
        let i = 2;
        // 跳过剩余长度（多字节）
        while (buf[i - 1] & 0x80) i++;
        const tlen = (buf[i] << 8) | buf[i + 1];
        const topic = new TextDecoder().decode(buf.slice(i + 2, i + 2 + tlen));
        const msg = new TextDecoder().decode(buf.slice(i + 2 + tlen));
        emit('message', topic, msg);
        return;
      }
      emit('raw', type, buf);
    }

    /* ---- 心跳 ---- */
    function startKeep() {
      stopKeep();
      keepTimer = setInterval(() => mqttSend(0xC0, new Uint8Array(0)), 30000);
    }
    function stopKeep() { clearInterval(keepTimer); keepTimer = null; }

    /* ---- 订阅 ---- */
    function doSub(topic) {
      const body = join([new Uint8Array([0x00, 0x01]), encStr(topic), new Uint8Array([0x00])]);
      mqttSend(0x82, body);
    }

    function subscribe(topic) {
      subs.add(topic);
      if (ready) doSub(topic);
    }
    function unsubscribe(topic) {
      subs.delete(topic);
      if (ready) mqttSend(0xA2, join([new Uint8Array([0x00, 0x02]), encStr(topic)]));
    }

    /* ---- 发布 ---- */
    function publish(topic, text, retain) {
      const body = join([encStr(topic), new TextEncoder().encode(String(text))]);
      const fixed = retain ? 0x31 : 0x30;      // retain 位
      send(packet(fixed, body));
      return ready;
    }

    function on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); return api; }
    function end() {
      closed = true;
      gen++;                                  // 让所有在途事件失效
      clearTimeout(retryTimer); stopKeep();
      try { mqttSend(0xE0, new Uint8Array(0)); } catch (e) {}
      try {
        if (ws) { ws.onopen = ws.onmessage = ws.onerror = ws.onclose = null; ws.close(); }
      } catch (e) {}
      ws = null;
    }

    const api = {
      on, subscribe, unsubscribe, publish, end,
      get connected() { return ready; },
      get broker() { return state.broker; },
      get pending() { return subs.size; },
    };
    connect();
    return api;
  }

  return { createClient, BROKERS };
});
