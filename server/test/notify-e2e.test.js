'use strict';
/*
 * 微信回调整链路端到端测试（不联网）
 *
 * 模拟微信服务器的真实行为：
 *   1) 用「微信支付私钥」对回调报文签名
 *   2) 用 APIv3 密钥对订单数据做 AES-256-GCM 加密
 *   3) POST 到 /api/pay/notify
 * 验证我们的服务器能：验签 → 解密 → 核对金额 → 落库 → 标记已付
 *
 * 运行：node test/notify-e2e.test.js
 */
const crypto = require('crypto');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

let pass = 0, fail = 0;
const ok = (name, cond, extra) => {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra !== undefined ? '  → ' + JSON.stringify(extra) : '')); }
};

/* ---------- 造一对「微信支付」钥匙 ---------- */
const wxKey = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});
/* ---------- 造一对「商户」钥匙 ---------- */
const mchKey = crypto.generateKeyPairSync('rsa', {
  modulusLength: 2048,
  publicKeyEncoding: { type: 'spki', format: 'pem' },
  privateKeyEncoding: { type: 'pkcs8', format: 'pem' },
});

const APIV3_KEY = 'abcdefghijklmnopqrstuvwxyz123456';   // 32 位
const PORT = 8901;
const BASE = 'http://127.0.0.1:' + PORT;
const TOKEN = 'test-token-123';

/* ---------- 构造微信回调报文 ---------- */
function buildNotify({ outTradeNo, totalFen, txId }) {
  const plain = JSON.stringify({
    mchid: '1900000001',
    appid: 'wx1234567890',
    out_trade_no: outTradeNo,
    transaction_id: txId,
    trade_type: 'NATIVE',
    trade_state: 'SUCCESS',
    success_time: new Date().toISOString(),
    payer: { openid: 'oUpF8uMuAJO_M2pxb1Q9zNjWeS6o' },
    amount: { total: totalFen, payer_total: totalFen, currency: 'CNY' },
  });

  const nonce = crypto.randomBytes(6).toString('hex').slice(0, 12);
  const aad = 'transaction';
  const cipher = crypto.createCipheriv('aes-256-gcm', Buffer.from(APIV3_KEY), Buffer.from(nonce));
  cipher.setAAD(Buffer.from(aad));
  const enc = Buffer.concat([cipher.update(plain, 'utf8'), cipher.final()]);
  const ciphertext = Buffer.concat([enc, cipher.getAuthTag()]).toString('base64');

  const body = JSON.stringify({
    id: 'EV-' + Date.now(),
    create_time: new Date().toISOString(),
    event_type: 'TRANSACTION.SUCCESS',
    resource_type: 'encrypt-resource',
    resource: { algorithm: 'AEAD_AES_256_GCM', original_type: 'transaction', ciphertext, associated_data: aad, nonce },
  });

  const ts = String(Math.floor(Date.now() / 1000));
  const nonceStr = crypto.randomBytes(8).toString('hex');
  const message = `${ts}\n${nonceStr}\n${body}\n`;
  const signature = crypto.createSign('RSA-SHA256').update(message).sign(wxKey.privateKey, 'base64');

  return { body, headers: {
    'Content-Type': 'application/json',
    'Wechatpay-Timestamp': ts,
    'Wechatpay-Nonce': nonceStr,
    'Wechatpay-Signature': signature,
    'Wechatpay-Serial': 'PUB_KEY_ID_TEST',
  } };
}

/* ---------- 启动服务器 ---------- */
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'luhuo-test-'));
const env = Object.assign({}, process.env, {
  PORT: String(PORT),
  MOCK: '0',
  ADMIN_TOKEN: TOKEN,
  WXPAY_MCHID: '1900000001',
  WXPAY_APPID: 'wx1234567890',
  WXPAY_SERIAL_NO: 'MCHSERIAL123',
  WXPAY_APIV3_KEY: APIV3_KEY,
  WXPAY_PRIVATE_KEY_PEM: mchKey.privateKey,
  WXPAY_PUBLIC_KEY_PEM: wxKey.publicKey,
  WXPAY_PRIVATE_KEY_PATH: '/nonexistent/x.pem',
  WXPAY_PUBLIC_KEY_PATH: '/nonexistent/y.pem',
  ORDERS_FILE: path.join(dataDir, 'orders.json'),
  STORAGE: 'local',
  PUBLIC_BASE_URL: 'https://pay.test.local',
});

const srv = spawn(process.execPath, [path.join(__dirname, '..', 'index.js')], { env, cwd: path.join(__dirname, '..') });
let serverLog = '';
srv.stdout.on('data', d => serverLog += d);
srv.stderr.on('data', d => serverLog += d);

const sleep = ms => new Promise(r => setTimeout(r, ms));
const j = (p, o) => fetch(BASE + p, o).then(async r => ({ status: r.status, body: await r.json().catch(() => null) }));

(async () => {
  // 等服务起来
  for (let i = 0; i < 40; i++) {
    try { await fetch(BASE + '/api/health'); break; } catch (e) { await sleep(200); }
  }

  console.log('\n== 0. 生产模式启动检查 ==');
  const h = await j('/api/health');
  ok('运行在 LIVE 真实模式（不是 mock）', /LIVE/.test(h.body.mode), h.body.mode);
  ok('商户私钥已从环境变量加载', h.body.hasPrivateKey === true, h.body);

  console.log('\n== 1. 下单 ==');
  const created = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '王小明', phone: '13611112222', address: '阳光小区 8 栋 1801', items: [{ id: 'p_zhuti', qty: 2 }] }),
  });
  ok('下单成功', created.status === 200 && created.body.ok, created.body);
  const no = created.body.outTradeNo;
  const totalFen = Math.round(created.body.total * 100);
  console.log('     订单号 ' + no + '  应付 ' + totalFen + ' 分');

  console.log('\n== 2. 真实签名回调（金额正确）==');
  const n = buildNotify({ outTradeNo: no, totalFen, txId: '4200001234202609301234567890' });
  const res = await fetch(BASE + '/api/pay/notify', { method: 'POST', headers: n.headers, body: n.body });
  const resBody = await res.json();
  ok('回调被接受（微信会收到 SUCCESS）', res.status === 200 && resBody.code === 'SUCCESS', resBody);

  await sleep(300);
  const o1 = await j('/api/orders/' + no);
  ok('订单已标记为已付款', o1.body.order.status === 'PAID', o1.body.order.status);
  ok('公开接口不泄露微信交易号', o1.body.order.transactionId === undefined, o1.body.order.transactionId);

  // 交易号要能在后台（带 token）查到
  const admin = await j('/api/admin/orders', { headers: { Authorization: 'Bearer ' + TOKEN } });
  const rec = admin.body.orders.find(x => x.outTradeNo === no);
  ok('后台能查到微信交易号', rec && rec.transactionId === '4200001234202609301234567890', rec && rec.transactionId);
  ok('后台记录了付款时间', rec && !!rec.paidAt, rec && rec.paidAt);

  console.log('\n== 3. 幂等性（微信会重复回调）==');
  const res2 = await fetch(BASE + '/api/pay/notify', { method: 'POST', headers: n.headers, body: n.body });
  ok('重复回调仍返回 SUCCESS', res2.status === 200, res2.status);

  console.log('\n== 4. 伪造签名必须被拒 ==');
  const fakeBody = JSON.stringify({ event_type: 'TRANSACTION.SUCCESS', resource: { algorithm: 'AEAD_AES_256_GCM', ciphertext: 'x', nonce: '123456789012', associated_data: 'transaction' } });
  const fakeRes = await fetch(BASE + '/api/pay/notify', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Wechatpay-Timestamp': String(Math.floor(Date.now() / 1000)),
      'Wechatpay-Nonce': 'aaa', 'Wechatpay-Signature': 'Tk9UX1ZBTElE', 'Wechatpay-Serial': 'x',
    },
    body: fakeBody,
  });
  ok('伪造签名被拒（401）', fakeRes.status === 401, fakeRes.status);

  console.log('\n== 5. 重放攻击（时间戳过期）==');
  const old = buildNotify({ outTradeNo: no, totalFen, txId: 'X' });
  old.headers['Wechatpay-Timestamp'] = String(Math.floor(Date.now() / 1000) - 600);   // 10 分钟前，签名已失效
  const replay = await fetch(BASE + '/api/pay/notify', { method: 'POST', headers: old.headers, body: old.body });
  ok('过期时间戳被拒（401）', replay.status === 401, replay.status);

  console.log('\n== 6. 金额篡改：实付 1 分钱买 56 元卤味 ==');
  const c2 = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '小偷', phone: '13611113333', address: '阳光小区 8 栋 1801', items: [{ id: 'p_zhuti', qty: 2 }] }),
  });
  const no2 = c2.body.outTradeNo;
  const stolen = buildNotify({ outTradeNo: no2, totalFen: 1, txId: 'STEAL' });
  const stealRes = await fetch(BASE + '/api/pay/notify', { method: 'POST', headers: stolen.headers, body: stolen.body });
  await sleep(300);
  const o2 = await j('/api/orders/' + no2);
  ok('金额不符不会标记为已付款', o2.body.order.status !== 'PAID', o2.body.order.status);
  ok('标记为 AMOUNT_MISMATCH 告警', o2.body.order.status === 'AMOUNT_MISMATCH', o2.body.order.status);

  console.log('\n== 7. 订单数据持久化 ==');
  const saved = JSON.parse(fs.readFileSync(path.join(dataDir, 'orders.json'), 'utf8'));
  ok('订单已落盘', !!saved.orders[no], Object.keys(saved.orders));

  console.log('\n== 8. 回调错误细节不外泄 ==');
  const bodyStr = JSON.stringify(resBody);
  ok('SSUCCESS 响应不含敏感字段', !/private|BEGIN|apiv3|key/i.test(bodyStr), bodyStr);

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  if (fail) console.log('--- 服务器日志 ---\n' + serverLog);
  srv.kill('SIGTERM');
  fs.rmSync(dataDir, { recursive: true, force: true });
  process.exit(fail ? 1 : 0);
})().catch(e => {
  console.error('测试异常', e);
  console.log('--- 服务器日志 ---\n' + serverLog);
  srv.kill('SIGTERM');
  process.exit(1);
});
