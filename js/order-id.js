/*
 * 订单指纹（浏览器 + Node 通用）
 *
 * 解决的问题：静态收款码 + 四方平台，付款不回调我们。
 * 答案是：让「钱」本身带上订单身份 —— 用唯一金额尾数 + 短指针码，
 *         这样任何平台的收款记录都能反查回订单，不依赖回调。
 *
 * 三件套：
 *   1) 订单号   LH + 时间 + 随机 + 校验位   —— 防伪造、防抄错
 *   2) 唯一金额 本金 + 尾数(1~99分)          —— 付款记录里直接带订单身份
 *   3) 指针码   6 位短码                     —— 可口述、可手输、跨平台
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.OrderID = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /* Crockford Base32：去掉 I L O U，避免 1/l/I、0/O 看错 */
  const AB = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

  /* ---------- 哈希：FNV-1a + murmur3 收尾（保证雪崩效应，低位也均匀） ---------- */
  function mix32(h) {
    h ^= h >>> 16; h = Math.imul(h, 0x85ebca6b);
    h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35);
    h ^= h >>> 16;
    return h >>> 0;
  }
  function hash32(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193);      // FNV prime
    }
    return mix32(h >>> 0);
  }

  /* ---------- 校验位：让瞎编/抄错的订单号一眼识破 ---------- */
  function checkChar(body) {
    let sum = 0;
    for (let i = 0; i < body.length; i++) {
      const v = AB.indexOf(body[i]);
      sum += (v < 0 ? 0 : v) * (i % 7 + 1);   // 位置加权
    }
    return AB[sum % 32];
  }

  function pad(n, len) { return String(n).padStart(len, '0'); }

  /* ---------- 订单号 ---------- */
  function makeOrderNo(date) {
    const d = date || new Date();
    // 日期段：YYMMDD（6 位，人眼可读）
    const t = String(d.getFullYear()).slice(2) +
      pad(d.getMonth() + 1, 2) + pad(d.getDate(), 2);
    // 随机段 5 位 → 32^5 = 3355 万种/天，小店铺撞号概率趋近于 0
    let r = '';
    for (let i = 0; i < 5; i++) r += AB[Math.floor(Math.random() * 32)];
    const body = 'LH' + t + r;
    return body + checkChar(body);   // 共 2+6+5+1 = 14 位
  }

  /* 生成不与已有订单冲突的订单号 */
  function makeUniqueOrderNo(exists, date) {
    for (let i = 0; i < 12; i++) {
      const no = makeOrderNo(date);
      if (typeof exists !== 'function' || !exists(no)) return no;
    }
    // 极端情况兜底：加时间戳扰动
    return makeOrderNo(new Date(Date.now() + Math.floor(Math.random() * 86400000)));
  }

  function checkOrderNo(no) {
    if (typeof no !== 'string' || no.length < 6) return false;
    if (no.slice(0, 2) !== 'LH') return false;
    const body = no.slice(0, -1);
    // 前缀 LH 不在 Crockford 字母表内，只校验时间/随机段
    for (const c of body.slice(2)) if (AB.indexOf(c) < 0) return false;
    return checkChar(body) === no.slice(-1);
  }

  /* ---------- 指针码：6 位，可口述 ---------- */
  // 由订单号确定性地派生，所以不占存储、可随时复算核对
  function pointerOf(orderNo) {
    // 用哈希链：每次取 5 位，再重新混淆，避免低位分布不均
    let out = '';
    let h = hash32(orderNo + '|ptr');
    for (let i = 0; i < 6; i++) {
      out += AB[h & 31];
      h = hash32(out + '|' + i + '|' + orderNo);
    }
    return out;
  }

  /* ---------- 唯一金额 ---------- */
  // 尾数 1~99 分，由订单号确定性派生 → 同一订单永远是同一金额，可复算
  function tailFen(orderNo) {
    return (hash32(orderNo + '|tail') % 99) + 1;   // 1..99 分
  }

  /**
   * 把订单总价变成"唯一金额"
   * @param totalYuan 基础总价（元），如 56
   * @param orderNo   订单号
   * @returns { baseFen, payFen, payYuan, tailFen, tailText }
   */
  function uniqueAmount(totalYuan, orderNo) {
    const baseFen = Math.round(Number(totalYuan) * 100);
    const tail = tailFen(orderNo);
    const payFen = baseFen + tail;
    return {
      baseFen,
      payFen,
      payYuan: payFen / 100,
      tailFen: tail,
      tailText: pad(tail, 2),          // "07" / "37"
      display: (payFen / 100).toFixed(2),
    };
  }

  /**
   * 反查：拿"收到的金额（分）"找订单线索
   * 返回该金额对应的尾数，用来和订单的 tailFen 比对
   */
  function tailFromPaidFen(paidFen) {
    const f = Math.round(Number(paidFen));
    if (!(f > 0)) return null;
    const t = f % 100;
    return t === 0 ? 100 : t;   // 尾数 0 视为 100（即整元，无尾数）
  }

  /* ---------- 打印/展示用 ---------- */
  function fmtFen(fen) {
    return (Math.round(Number(fen)) / 100).toFixed(2);
  }

  /* ---------- 对账：把"收到的金额"归一化 ---------- */
  // 支持 "56.89" / "¥56.89" / "5689"（分）/ "89"（只给尾数）
  function parsePaidAmount(s) {
    s = String(s == null ? '' : s).replace(/[¥￥\s,]/g, '');
    if (!s) return null;
    if (/^\d+\.\d{1,2}$/.test(s)) return Math.round(parseFloat(s) * 100);
    if (/^\d+$/.test(s)) {
      if (s.length <= 2) return null;        // 纯尾数，交给 tailOf
      return parseInt(s, 10);                // "5689" → 5689 分
    }
    return null;
  }
  // 取尾数（1~100，其中 100 表示整元）
  function tailOf(s) {
    s = String(s == null ? '' : s).replace(/[^\d]/g, '');
    if (!s) return null;
    const t = parseInt(s.slice(-2), 10);
    return t === 0 ? 100 : t;
  }

  /* ---------- 从"顾客发来的订单文本"里解析 ---------- */
  function parseOrderText(text) {
    const t = String(text == null ? '' : text);
    const pick = re => { const m = t.match(re); return m ? String(m[1]).trim() : ''; };
    let code = pick(/订单号[：:]\s*([A-Za-z0-9]{6,})/);
    if (!code) { const m = t.match(/\bLH[0-9A-Z]{6,}\b/); if (m) code = m[0]; }
    if (!code) return null;
    code = code.toUpperCase();
    if (!checkOrderNo(code)) return null;

    const pay = pick(/请支付[：:]\s*¥?\s*([\d.]+)/);
    const total = pick(/合计应付[：:]\s*¥?\s*([\d.]+)/);
    const ptr = pick(/(?:订单指针|指针)[：:]\s*([A-Za-z0-9]{4,8})/);

    let fen = 0;
    if (pay) fen = Math.round(parseFloat(pay) * 100);
    else if (total) fen = Math.round(parseFloat(total) * 100) + tailFen(code);

    return {
      code,
      pointer: (ptr || pointerOf(code)).toUpperCase(),
      payFen: fen,
      payText: fmtFen(fen),
      tailFen: fen % 100 === 0 ? 100 : fen % 100,
      name: pick(/收货人[：:]\s*([^\n]+)/),
      phone: pick(/电话[：:]\s*([\d\-+ ]{5,20})/),
      address: pick(/地址[：:]\s*([^\n]+)/),
      raw: t.slice(0, 600),
    };
  }

  /* ---------- 收款确认回执 ----------
   * 只有商家的对账台能生成，顾客伪造不了（因为要商家核对完才能拿到）。
   * 顾客说"我付过了"时，商家回这一条，就代表"我确实在账上看到了这笔钱"。
   */
  function receiptText(o) {
    return [
      '✅ 收款确认',
      '订单号：' + o.code,
      '金额：¥' + (o.payText || fmtFen(o.payFen || 0)),
      '已收到款，马上为你安排～',
    ].join('\n');
  }

  /* ---------- 订单是否已过期 ---------- */
  function isExpired(o, now) {
    if (!o || o.status === 'PAID') return false;
    if (!o.expireAt) return false;
    return (now || Date.now()) > o.expireAt;
  }
  function leftMinutes(o, now) {
    if (!o || !o.expireAt) return null;
    const ms = o.expireAt - (now || Date.now());
    return ms <= 0 ? 0 : Math.ceil(ms / 60000);
  }

  /* ---------- 对账匹配：给一个"收到的金额/指针"找出订单 ----------
   * 返回 { hits: [...], how: '指针码'|'金额'|'尾数'|'' }
   * 优先级：指针码（最准）→ 完整金额 → 尾数（模糊，只找待收款）
   */
  function looksLikePointer(s) {
    const t = String(s == null ? '' : s).trim().toUpperCase();
    if (!/^[0-9A-HJKMNP-TV-Z]{6}$/.test(t)) return false;
    if (/^\d{6}$/.test(t)) return false;    // 纯数字更像金额
    return true;
  }

  function matchOrder(list, input) {
    const arr = Array.isArray(list) ? list : [];
    const raw = String(input == null ? '' : input).trim();
    if (!raw) return { hits: [], how: '' };
    const up = raw.toUpperCase();

    if (looksLikePointer(up)) {
      const h = arr.filter(o => String(o.pointer || '').toUpperCase() === up);
      if (h.length) return { hits: h, how: '指针码' };
    }
    const fen = parsePaidAmount(raw);
    if (fen) {
      const h = arr.filter(o => Number(o.payFen) === fen);
      if (h.length) return { hits: h, how: '金额' };
    }
    const digits = raw.replace(/\D/g, '');
    if (digits.length <= 2) {
      const t = tailOf(raw);
      if (t) {
        const h = arr.filter(o => Number(o.tailFen) === t && o.status === 'WAIT');
        if (h.length) return { hits: h, how: '尾数' };
      }
    }
    return { hits: [], how: '' };
  }

  /* ---------- 识别方式说明（给顾客看的） ---------- */
  function payInstruction(recognizeBy, o) {
    const ptr = o.pointer || '';
    switch (recognizeBy) {
      case 'amount':
        return {
          amount: o.payText,
          title: '请支付 ¥' + o.payText,
          sub: '尾数 ' + o.tailText + ' 是这单的识别码，请务必一分不差',
          copyHint: '复制金额',
          copyValue: o.payText,
        };
      case 'both':
        return {
          amount: o.payText,
          title: '请支付 ¥' + o.payText,
          sub: '付款备注填 ' + ptr + '（尾数也要对）',
          copyHint: '复制备注',
          copyValue: ptr,
        };
      default: // note
        return {
          amount: o.baseText || o.payText,
          title: '请支付 ¥' + (o.baseText || o.payText),
          sub: '在「添加备注」里填 ' + ptr + '，方便商家认出是你这一单',
          copyHint: '复制备注 ' + ptr,
          copyValue: ptr,
        };
    }
  }

  /* 尾数显示：1 → "01"，100 → "00"（整元） */
  function tailText(fen) {
    const t = Math.round(Number(fen));
    if (!(t > 0)) return '--';
    const v = t % 100;
    return v === 0 ? '00' : pad(v, 2);
  }

  // 把订单号分组，方便看：LH2609301234ABC7 → LH26 0930 1234 ABC7
  function group(no) {
    if (typeof no !== 'string' || no.length < 14) return no;
    return no.slice(0, 2) + ' ' + no.slice(2, 6) + ' ' + no.slice(6, 10) + ' ' + no.slice(10);
  }

  return {
    AB, hash32, makeOrderNo, makeUniqueOrderNo, checkOrderNo, pointerOf,
    tailFen, uniqueAmount, tailFromPaidFen, fmtFen, tailText, group,
    parsePaidAmount, tailOf, parseOrderText,
    receiptText, isExpired, leftMinutes, payInstruction,
    looksLikePointer, matchOrder,
  };
});
