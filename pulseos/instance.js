/* ==========================================================================
 *  instance.js —— 链接即实例（零服务端多租户）
 *  --------------------------------------------------------------------------
 *  思路来自卤味商店的 join.js：把整个配置编进 URL，不需要数据库、不需要子域名。
 *
 *      pulseos/api.html#<base64({ label, gateway, services, ... })>
 *
 *  每个 URL 就是一个独立的"实例视图"：
 *    · 不同的 gateway 地址   → 连不同的后端
 *    · 不同的 services 列表  → 只看自己那几个微内核
 *    · 不同的 label          → 显示不同的名字
 *
 *  ★ 关键事实：这不是"给每个用户开一台服务器"。
 *     它只是"给每个用户一个不同的链接，指向不同的后端"。
 *     后端还是那几台，但链接可以无限生成。
 *
 *  ★ 这才是「无限扩充」的正确形态：
 *     不是扩充域名（做不到），是扩充【链接】+ 扩充【后端实例】。
 * ========================================================================== */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PulseInstance = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* ---------------- base64url 编解码（URL 安全）---------------- */
  function b64encode(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = '';
    for (const b of bytes) bin += String.fromCharCode(b);
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function b64decode(s) {
    const b = s.replace(/-/g, '+').replace(/_/g, '/');
    const pad = b.length % 4 ? '='.repeat(4 - (b.length % 4)) : '';
    const bin = atob(b + pad);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  /* ---------------- 实例配置 ---------------- */
  const DEFAULT_INSTANCE = {
    v: 1,
    label: 'PulseOS 默认实例',
    note: '',
    /* 后端网关。null = 没有在线网关，只能看不能调 */
    gateway: null,
    /* 只显示这些服务；null = 全部 */
    services: null,
    /* 允许调用的能力；null = 全部 */
    allow: null,
    /* 每个实例自己的限速（客户端侧提示，真正的限流在网关） */
    clientRateLimit: null,
    created: null,
  };

  function normalize(obj) {
    if (!obj || typeof obj !== 'object') return null;
    const out = Object.assign({}, DEFAULT_INSTANCE, obj);
    if (out.v !== 1) return null;
    return out;
  }

  /* 编码成 hash 片段（不含 #） */
  function encode(instance) {
    const obj = Object.assign({}, DEFAULT_INSTANCE, instance);
    obj.created = obj.created || new Date().toISOString().slice(0, 10);
    return b64encode(JSON.stringify(obj));
  }

  /* 从 hash 解码 */
  function decode(hash) {
    if (!hash) return null;
    const raw = String(hash).replace(/^#/, '');
    if (!raw) return null;

    /* 支持两种形式：
       #<base64>                      紧凑
       #instance=<base64>             显式
       #import=<base64>               兼容卤味商店的写法 */
    let payload = raw;
    const m = raw.match(/^(?:instance|import)=(.+)$/);
    if (m) payload = m[1];

    try {
      const json = b64decode(decodeURIComponent(payload));
      return normalize(JSON.parse(json));
    } catch (e) {
      return null;
    }
  }

  /* 生成一个新实例的完整 URL */
  function makeUrl(baseUrl, instance) {
    const base = String(baseUrl).split('#')[0];
    return base + '#' + encode(instance);
  }

  /* 从当前页面生成 */
  function currentBase() {
    if (typeof location === 'undefined') return '';
    return location.origin + location.pathname;
  }

  /* 生成一个随机 slug（用于 label 或短标识） */
  function randomSlug(len) {
    const chars = 'abcdefghijkmnpqrstuvwxyz23456789';
    const n = len || 6;
    let s = '';
    /* 浏览器用 crypto，Node 用 crypto.randomBytes —— 两边都要能跑（测试需要） */
    if (typeof self !== 'undefined' && (self.crypto || self.msCrypto)) {
      const arr = new Uint8Array(n);
      (self.crypto || self.msCrypto).getRandomValues(arr);
      for (const b of arr) s += chars[b % chars.length];
    } else {
      const nodeCrypto = require('crypto');
      const arr = nodeCrypto.randomBytes(n);
      for (const b of arr) s += chars[b % chars.length];
    }
    return s;
  }

  /* ---------------- 展示用 ---------------- */
  /* 把实例配置变成可读的描述 */
  function describe(inst) {
    if (!inst) return '（无实例配置，使用默认）';
    const lines = [];
    lines.push('实例名    ' + inst.label);
    if (inst.note) lines.push('说明      ' + inst.note);
    lines.push('网关      ' + (inst.gateway || '（未配置，只能看不能调）'));
    lines.push('可见服务  ' + (inst.services ? inst.services.join(', ') : '全部'));
    lines.push('允许能力  ' + (inst.allow ? inst.allow.join(', ') : '全部'));
    if (inst.clientRateLimit) lines.push('客户端限速 ' + inst.clientRateLimit + ' 次/小时');
    if (inst.created) lines.push('创建于    ' + inst.created);
    return lines.join('\n');
  }

  return {
    DEFAULT_INSTANCE,
    encode, decode, makeUrl, currentBase, describe, normalize,
    randomSlug, b64encode, b64decode,
  };
});
