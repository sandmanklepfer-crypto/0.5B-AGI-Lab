/* ============================================================
   顾客端实时数据通道（公共 MQTT · 免 Token · 不改界面）
   ------------------------------------------------------------
   作用：
     · 收到商家工作台改的商品/店铺资料 → 即时覆盖并通知页面重渲染
     · 顾客下单时，把订单 publish 到 MQTT，商家工作台立刻可见
   说明：没连上（或没网）时，页面照旧用仓库里的 data/*.json，不影响下单。
   ============================================================ */
window.OVR = (function () {
  function key() {
    var g = (window.LH && LH.guessRepo) ? LH.guessRepo() : { owner: '', repo: '' };
    var o = g.owner || 'anon', r = g.repo || 'luhuo';
    return (o + '__' + r).toLowerCase().replace(/[^a-z0-9_]/g, '');
  }
  var K = key();
  var BASE = 'zhz/luhuo/wb/' + K + '/';       // 商品 / 店铺资料
  var ORD = 'zhz/luhuo/orders/' + K + '/';    // 订单（每单一条，retain）
  var O = { products: null, settings: null, ready: false, publishOrder: function () {} };

  if (typeof MiniMqtt === 'undefined') return O;   // 没加载 MQTT 库就静默降级

  function fire() { try { window.dispatchEvent(new Event('lh:data')); } catch (e) {} }

  try {
    var cli = MiniMqtt.createClient({ clientId: 'lhcust' });
    cli.on('connect', function () {
      O.ready = true;
      cli.subscribe(BASE + 'products');
      cli.subscribe(BASE + 'settings');
    });
    cli.on('message', function (t, m) {
      var o; try { o = JSON.parse(m); } catch (e) { return; }
      if (!o) return;
      if (t === BASE + 'products' && o.items) {
        O.products = { categories: o.categories || [], items: o.items };
        fire();
      } else if (t === BASE + 'settings') {
        O.settings = o; fire();
      }
    });
    O.publishOrder = function (o) {
      try {
        cli.publish(ORD + (o.code || ('o' + Date.now())), JSON.stringify({
          name: o.name, phone: o.phone, address: o.address, want: o.want, pay: o.pay,
          note: o.note, items: (o.items || []).map(function (i) {
            return { id: i.id, name: i.name, qty: i.qty, price: i.price };
          }),
          total: o.total, status: 'PENDING', at: Date.now(), time: o.time
        }), true);
      } catch (e) {}
    };
  } catch (e) { /* 静默降级 */ }

  return O;
})();
