'use strict';
/* 冒烟测试：node server/test/smoke.js （需先启动演示模式服务） */
const BASE = process.env.BASE || 'http://localhost:8787';
const TOKEN = process.env.ADMIN_TOKEN || 'please-change-this-token';

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log('  ✅ ' + name); }
  else { fail++; console.log('  ❌ ' + name + (extra ? '  → ' + JSON.stringify(extra) : '')); }
}
const j = (p, o) => fetch(BASE + p, o).then(async r => ({ status: r.status, body: await r.json().catch(() => null) }));

(async () => {
  console.log('\n== 1. 健康检查 ==');
  const h = await j('/api/health');
  ok('服务在线', h.status === 200 && h.body.ok, h.body);
  ok('回调地址正确', /\/api\/pay\/notify$/.test(h.body.notifyUrl || ''), h.body.notifyUrl);

  console.log('\n== 2. 下单 & 金额由服务端说了算 ==');
  const bad = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '李四', phone: '13900139000', address: '测试路 1 号 101', items: [{ id: 'p_zhuti', qty: 2 }], total: 0.01 }),
  });
  ok('创建成功', bad.status === 200 && bad.body.ok, bad.body);
  ok('忽略前端传的 total（服务端算价）', bad.body.total === 56, bad.body.total);
  const no = bad.body.outTradeNo;

  // 卤鸡爪 18 元 < 起送 20 元
  const cheap = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '李四', phone: '13900139000', address: '测试路 1 号 101', items: [{ id: 'p_jizhua', qty: 1 }] }),
  });
  ok('低于起送金额被拒', cheap.status === 400, cheap.body);

  const badPhone = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '李四', phone: '123', address: '测试路 1 号 101', items: [{ id: 'p_zhuti', qty: 2 }] }),
  });
  ok('手机号非法被拒', badPhone.status === 400, badPhone.body);

  const noStock = await j('/api/orders/create', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: '李四', phone: '13900139000', address: '测试路 1 号 101', items: [{ id: 'p_zhuti', qty: 9999 }] }),
  });
  ok('超库存被拒', noStock.status === 400, noStock.body);

  console.log('\n== 3. 支付码 & 状态轮询 ==');
  const pre = await j('/api/pay/prepay', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ outTradeNo: no }),
  });
  ok('生成支付码', pre.status === 200 && !!pre.body.codeUrl, pre.body);
  let st = await j('/api/pay/status?outTradeNo=' + no);
  ok('初始状态 PENDING', st.body.status === 'PENDING', st.body);

  console.log('\n== 4. 回调安全 ==');
  const forged = await fetch(BASE + '/api/pay/notify', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Wechatpay-Timestamp': String(Math.floor(Date.now() / 1000)), 'Wechatpay-Nonce': 'abc', 'Wechatpay-Signature': 'fake', 'Wechatpay-Serial': 'x' },
    body: JSON.stringify({ event_type: 'TRANSACTION.SUCCESS', resource: {} }),
  });
  ok('伪造签名被拒（401）', forged.status === 401, forged.status);

  console.log('\n== 5. 模拟付款 → 回调链路 ==');
  const mock = await j('/api/pay/mock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outTradeNo: no }) });
  ok('标记已付', mock.status === 200 && mock.body.status === 'PAID', mock.body);
  const mock2 = await j('/api/pay/mock', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ outTradeNo: no }) });
  ok('重复付款幂等', mock2.status === 200, mock2.body);
  st = await j('/api/pay/status?outTradeNo=' + no);
  ok('状态变为 PAID', st.body.status === 'PAID', st.body);
  const o = await j('/api/orders/' + no);
  ok('订单详情可查', o.body.ok && o.body.order.status === 'PAID', o.body);

  console.log('\n== 6. 权限 ==');
  const noAuth = await j('/api/admin/orders');
  ok('无 token 查订单被拒（403）', noAuth.status === 403, noAuth.status);
  const withAuth = await j('/api/admin/orders', { headers: { Authorization: 'Bearer ' + TOKEN } });
  ok('带 token 可查订单', withAuth.status === 200 && Array.isArray(withAuth.body.orders), withAuth.body);

  console.log('\n== 7. 静态资源 & 目录保护 ==');
  const idx = await fetch(BASE + '/');
  ok('首页可访问', idx.status === 200);
  const pay = await fetch(BASE + '/pay.html?no=' + no);
  ok('支付页可访问', pay.status === 200);
  const env = await fetch(BASE + '/server/.env');
  ok('server/.env 被拒（403）', env.status === 403, env.status);
  const git = await fetch(BASE + '/.git/config');
  ok('.git 被拒', git.status === 403, git.status);
  const qr = await fetch(BASE + '/api/qr.svg?text=hello');
  ok('二维码 SVG 正常', qr.status === 200 && (qr.headers.get('content-type') || '').includes('svg'));

  console.log(`\n===== 结果：${pass} 通过 / ${fail} 失败 =====\n`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('测试异常', e); process.exit(1); });
