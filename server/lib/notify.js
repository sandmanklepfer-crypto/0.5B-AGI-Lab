'use strict';
/* 付款成功后，把订单推给老板：优先自建 webhook，否则复用网页里的邮箱设置 */
const fs = require('fs');
const path = require('path');
const https = require('https');
const { cfg } = require('./config');

function post(url, payload) {
  return new Promise((resolve) => {
    try {
      const u = new URL(url);
      const body = JSON.stringify(payload);
      const req = https.request({
        host: u.hostname,
        port: u.port || 443,
        path: u.pathname + u.search,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': Buffer.byteLength(body),
          'Accept': 'application/json',
        },
      }, res => { res.resume(); resolve(res.statusCode < 300); });
      req.on('error', () => resolve(false));
      req.write(body); req.end();
    } catch (e) { resolve(false); }
  });
}

function orderLines(o) {
  return (o.items || []).map(i => `${i.name} ×${i.qty}  ¥${Number(i.sum).toFixed(2)}`).join('\n');
}

function summaryText(o) {
  return [
    `【已付款】${o.shop || '卤味小店'}`,
    `订单号：${o.outTradeNo}`,
    `微信交易号：${o.transactionId || '-'}`,
    '————————',
    orderLines(o),
    '————————',
    `实付：¥${Number(o.total).toFixed(2)}`,
    `收货人：${o.name}`,
    `电话：${o.phone}`,
    `地址：${o.address}`,
    `送达时间：${o.want || '-'}`,
    o.note ? `备注：${o.note}` : '',
    `付款时间：${o.paidAt ? new Date(o.paidAt).toLocaleString('zh-CN') : '-'}`,
  ].filter(Boolean).join('\n');
}

async function pushToMerchant(o) {
  const text = summaryText(o);

  if (cfg.merchantWebhook) {
    const ok = await post(cfg.merchantWebhook, { type: 'PAID', text, order: o });
    console.log('[notify] webhook', ok ? 'OK' : 'FAIL');
  }

  // 复用网页后台里配的邮箱通道
  let form = {};
  try {
    const s = JSON.parse(fs.readFileSync(path.join(cfg.SHOP_ROOT, 'data', 'settings.json'), 'utf8'));
    form = s.orderForm || {};
  } catch (e) { /* ignore */ }

  try {
    if (form.provider === 'web3forms' && form.accessKey) {
      await post('https://api.web3forms.com/submit', {
        access_key: form.accessKey,
        subject: `【已付款】${o.outTradeNo} ¥${Number(o.total).toFixed(2)}`,
        from_name: (o.shop || '卤味小店') + ' 在线支付',
        '订单号': o.outTradeNo, '金额': '¥' + Number(o.total).toFixed(2),
        '收货人': o.name, '电话': o.phone, '地址': o.address,
        '明细': (o.items || []).map(i => i.name + '×' + i.qty).join('、'),
        '完整订单': text,
      });
    } else if (form.provider === 'formsubmit' && form.email) {
      await post('https://formsubmit.co/ajax/' + encodeURIComponent(form.email), {
        _subject: `【已付款】${o.outTradeNo} ¥${Number(o.total).toFixed(2)}`,
        '订单号': o.outTradeNo, '金额': '¥' + Number(o.total).toFixed(2),
        '收货人': o.name, '电话': o.phone, '地址': o.address,
        '完整订单': text,
      });
    }
  } catch (e) { console.warn('[notify] 邮件推送失败', e.message); }

  console.log('\n===== 收到付款 =====\n' + text + '\n====================\n');
  return text;
}

/* ---------- 新消息通知商家 ---------- */
async function pushChatToMerchant(thread, msg) {
  const name = thread.name || thread.phone;
  const text = [
    '【新消息】' + name,
    '手机号：' + thread.phone,
    '——',
    msg.text,
    '——',
    new Date(msg.at).toLocaleString('zh-CN'),
    '（回复请打开订单后台 → 消息）',
  ].join('\n');

  if (cfg.merchantWebhook) {
    await post(cfg.merchantWebhook, { type: 'CHAT', text, phone: thread.phone });
  }

  let form = {};
  try {
    const s = JSON.parse(fs.readFileSync(path.join(cfg.SHOP_ROOT, 'data', 'settings.json'), 'utf8'));
    form = s.orderForm || {};
  } catch (e) { /* ignore */ }

  try {
    const subject = `【新消息】${name} 在卤味小店留言`;
    if (form.provider === 'web3forms' && form.accessKey) {
      await post('https://api.web3forms.com/submit', {
        access_key: form.accessKey, subject, from_name: '店铺消息',
        '来自': name, '手机号': thread.phone, '内容': msg.text, '时间': text.split('\n').pop(),
      });
    } else if (form.provider === 'formsubmit' && form.email) {
      await post('https://formsubmit.co/ajax/' + encodeURIComponent(form.email), {
        _subject: subject, '来自': name, '手机号': thread.phone, '内容': msg.text,
      });
    }
  } catch (e) { console.warn('[chat] 邮件通知失败', e.message); }

  console.log('\n===== 顾客留言 =====\n' + text + '\n====================\n');
}

module.exports = { pushToMerchant, summaryText, pushChatToMerchant };
