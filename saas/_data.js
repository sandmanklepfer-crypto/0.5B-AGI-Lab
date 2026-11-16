/* SDS 数据层 —— 走 MQTT 公共 broker，无需后端服务器 */
(function(){
  var P = 'zhz/sds/v1/';
  var TID = 't1';                       // 演示租户
  var CASHE = { products:null, orders:null, suppliers:null, stats:null };
  var cli = null, ready = false, cbs = [];

  function fire(){ cbs.forEach(function(f){ try{ f(); }catch(e){} }); }
  function onReady(f){ if(ready) f(); else cbs.push(f); }

  function connect(){
    if (typeof MiniMqtt === 'undefined') { console.warn('MQTT 未加载，使用本地演示数据'); loadFallback(); return; }
    try {
      cli = MiniMqtt.createClient({ clientId: 'sds' + Math.random().toString(36).slice(2,9) });
      cli.on('connect', function(){
        ready = true;
        cli.subscribe(P + TID + '/products');
        cli.subscribe(P + TID + '/orders');
        cli.subscribe(P + TID + '/suppliers');
        // 请求一次权威数据
        cli.publish(P + TID + '/req', JSON.stringify({ t: Date.now(), c: 'sync' }));
        fire();
      });
      cli.on('message', function(t, m){
        var d; try{ d = JSON.parse(m); }catch(e){ return; }
        if (t.indexOf('/products') > 0 && d.items){ CASHE.products = d.items; fire(); }
        else if (t.indexOf('/orders') > 0 && d.items){ CASHE.orders = d.items; fire(); }
        else if (t.indexOf('/suppliers') > 0 && d.items){ CASHE.suppliers = d.items; fire(); }
      });
      setTimeout(function(){ if(!ready) loadFallback(); }, 3000);
    } catch(e) { loadFallback(); }
  }

  /* 本地兜底数据（MQTT 不通时用） */
  var FB_P = [
    {sku:'SKU-TWS-001',name:'蓝牙耳机 TWS-Pro 降噪版',img:'earphone',cat:'数码配件',supplier:'深圳华强北电子',cost:128,price:299,retail:299,stock:2480,moq:10,t1:50,t2:200,p1:118,p2:108,status:'on'},
    {sku:'SKU-PWB-002',name:'充电宝 20000mAh 双向快充',img:'powerbank',cat:'数码配件',supplier:'东莞制造',cost:99,price:189,retail:219,stock:1860,moq:20,t1:50,t2:200,p1:89,p2:82,status:'on'},
    {sku:'SKU-STD-003',name:'手机支架 磁吸折叠款',img:'stand',cat:'数码配件',supplier:'深圳华强北电子',cost:18.5,price:39.9,retail:49.9,stock:48,moq:50,t1:100,t2:500,p1:15,p2:13,status:'on'},
    {sku:'SKU-CBL-004',name:'数据线 三合一 快充编织',img:'cable',cat:'数码配件',supplier:'义乌小商品',cost:12,price:25.9,retail:35.9,stock:0,moq:100,t1:500,t2:2000,p1:9.5,p2:8.5,status:'on'},
    {sku:'SKU-CAR-005',name:'车载充电器 66W 双口',img:'car',cat:'数码配件',supplier:'东莞制造',cost:45,price:89,retail:109,stock:920,moq:30,t1:100,t2:500,p1:39,p2:35,status:'on'},
    {sku:'SKU-MSE-006',name:'无线鼠标 静音办公',img:'mouse',cat:'数码配件',supplier:'深圳华强北电子',cost:38,price:79,retail:99,stock:640,moq:20,t1:50,t2:200,p1:33,p2:29,status:'on'},
    {sku:'SKU-SPK-007',name:'蓝牙音箱 便携防水',img:'speaker',cat:'数码配件',supplier:'义乌小商品',cost:76,price:159,retail:199,stock:380,moq:15,t1:50,t2:200,p1:68,p2:62,status:'on'},
    {sku:'SKU-HUB-008',name:'USB集线器 4口 3.0',img:'hub',cat:'数码配件',supplier:'广州天河数码',cost:22,price:49,retail:69,stock:1240,moq:50,t1:100,t2:500,p1:18,p2:16,status:'on'}
  ];
  var FB_O = [
    {no:'GS241116001',buyer:'深圳华强北',items:'蓝牙耳机 TWS-Pro ×10',amount:2990,profit:1710,status:'delivering',at:'11-16 14:22'},
    {no:'GS241116002',buyer:'广州天河',items:'手机支架 磁吸款 ×20',amount:798,profit:428,status:'pending',at:'11-16 14:08'},
    {no:'GS241116003',buyer:'义乌小商品',items:'数据线 三合一 ×50',amount:1295,profit:695,status:'pending',at:'11-16 13:51'},
    {no:'GS241116004',buyer:'东莞制造',items:'充电宝 20000mAh ×20',amount:3780,profit:1800,status:'done',at:'11-16 13:20'},
    {no:'GS241115098',buyer:'广州天河',items:'车载充电器 ×30',amount:2670,profit:1320,status:'done',at:'11-15 18:40'}
  ];
  var FB_S = [
    {sid:'s1',name:'深圳华强北电子',region:'广东 深圳',settle:'月结30天',status:'ok'},
    {sid:'s2',name:'东莞制造',region:'广东 东莞',settle:'月结30天',status:'ok'},
    {sid:'s3',name:'义乌小商品',region:'浙江 义乌',settle:'半月结',status:'ok'},
    {sid:'s4',name:'广州天河数码',region:'广东 广州',settle:'周结',status:'review'}
  ];

  function loadFallback(){
    CASHE.products = FB_P;
    CASHE.orders = FB_O;
    CASHE.suppliers = FB_S;
    ready = true;
    fire();
  }

  window.SDS = {
    onReady: onReady,
    get products(){ return CASHE.products || []; },
    get orders(){ return CASHE.orders || []; },
    get suppliers(){ return CASHE.suppliers || []; },
    stats: function(){
      var p = this.products, o = this.orders;
      var gmv = 0, prof = 0;
      o.forEach(function(x){ gmv += (+x.amount||0); prof += (+x.profit||0); });
      return {
        products: p.length,
        onSale: p.filter(function(x){return x.stock>0}).length,
        outOfStock: p.filter(function(x){return x.stock<=0}).length,
        stock: p.reduce(function(a,x){return a+(+x.stock||0)},0),
        orders: o.length,
        gmv: Math.round(gmv),
        profit: Math.round(prof),
        suppliers: this.suppliers.length,
        pending: o.filter(function(x){return x.status==='pending'}).length,
        delivering: o.filter(function(x){return x.status==='delivering'}).length,
        done: o.filter(function(x){return x.status==='done'}).length
      };
    },
    money: function(n){ return '¥' + (Math.round(n*100)/100).toLocaleString('zh-CN'); }
  };

  connect();
})();
