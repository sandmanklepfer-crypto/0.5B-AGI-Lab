/* SAAS 货盘系统 · 统一页面外壳 */
(function(){
  var NAV = [
    {g:'工作台', items:[
      ['index.html','工作台','📊'],['dashboard.html','数据大屏','📈']
    ]},
    {g:'货盘', items:[
      ['goods.html','商品库','📦'],['select.html','选品采集','🔍'],
      ['publish.html','商品刊登','📤'],['dist.html','分销商品','🔗']
    ]},
    {g:'库存仓储', items:[
      ['stock.html','库存管理','🏷️'],['warehouse.html','仓库管理','🏭'],
      ['ship.html','国内发货','🚚']
    ]},
    {g:'订单', items:[
      ['orders.html','订单管理','📋'],['purchase.html','采购单','🧾'],
      ['cart.html','购物车','🛒']
    ]},
    {g:'供应商', items:[
      ['supplier.html','供应商列表','🏢'],['settle.html','供应商分账','💰']
    ]},
    {g:'会员财务', items:[
      ['members.html','会员管理','👥'],['wallet.html','钱包管理','💳'],
      ['withdraw.html','提现审核','💸']
    ]},
    {g:'系统', items:[
      ['roles.html','角色权限','🔐'],['logs.html','操作日志','📜'],
      ['settings.html','系统设置','⚙️']
    ]}
  ];

  window.SAAS_NAV = NAV;

  window.renderShell = function(opts){
    opts = opts || {};
    var cur = (location.pathname.split('/').pop() || 'index.html');
    var title = opts.title || '工作台';

    var menu = '';
    NAV.forEach(function(g){
      var on = g.items.some(function(i){ return i[0] === cur; });
      menu += '<div class="nv-g' + (on?' on':'') + '"><div class="nv-gt">' + g.g + '</div>';
      g.items.forEach(function(i){
        menu += '<a class="nv-i' + (i[0]===cur?' act':'') + '" href="' + i[0] + '"><span class="nv-ic">' + i[2] + '</span>' + i[1] + '</a>';
      });
      menu += '</div>';
    });

    document.body.insertAdjacentHTML('afterbegin',
      '<div class="shell">' +
        '<aside class="side">' +
          '<div class="brand"><span class="bl">G</span><div><b>GlobalSDS</b><i>跨境货盘 SaaS</i></div></div>' +
          '<nav class="nv">' + menu + '</nav>' +
          '<div class="side-ft"><a href="../index.html">← 返回主站</a></div>' +
        '</aside>' +
        '<main class="main">' +
          '<header class="topbar">' +
            '<button class="menu-btn" onclick="document.querySelector(\'.side\').classList.toggle(\'open\')">☰</button>' +
            '<h1>' + title + '</h1>' +
            '<div class="tb-r">' +
              '<span class="badge">DEMO</span>' +
              '<span class="u">演示账号</span>' +
            '</div>' +
          '</header>' +
          '<div class="content" id="content"></div>' +
        '</main>' +
      '</div>');
  };
})();
