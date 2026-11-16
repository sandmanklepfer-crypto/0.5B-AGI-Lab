/* 页面渲染：从 SDS 数据层动态生成 */
(function(){
  function h(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }
  function money(n){ return '¥'+(Math.round((+n||0)*100)/100).toLocaleString('zh-CN'); }
  function tagOf(st){
    var m={pending:['t-warn','待处理'],delivering:['t-info','已发货'],
           done:['t-ok','已完成'],cancelled:['t-err','已取消'],paid:['t-ok','已付款']};
    var x=m[st]||['t-info',st];
    return '<span class="tag '+x[0]+'">'+x[1]+'</span>';
  }
  function gdCard(p){
    var stockBadge = p.stock<=0 ? '<span class="tag t-err" style="position:absolute;right:8px;top:8px">缺货</span>'
                  : (p.stock < p.moq*2 ? '<span class="tag t-warn" style="position:absolute;right:8px;top:8px">预警</span>' : '');
    return '<div class="gd">'
      +'<div class="im" style="position:relative">'
      +'<img src="img/'+h(p.img||'hub')+'.svg" style="width:72px;height:72px" alt="">'
      +'<span class="moq">MOQ '+h(p.moq)+'</span>'+stockBadge+'</div>'
      +'<div class="bd"><div class="nm">'+h(p.name)+'</div>'
      +'<div class="sn">'+h(p.sku)+'</div>'
      +'<div class="pr"><b>'+money(p.price)+'</b><span>供货价</span></div>'
      +'<div class="ft"><span class="ladder">'+h(p.t1)+'+ '+money(p.p1)+'</span>'
      +'<a class="btn sm g" href="goods-detail.html?sku='+encodeURIComponent(p.sku)+'">详情</a></div>'
      +'</div></div>';
  }
  window.SDSR = { h:h, money:money, tagOf:tagOf, gdCard:gdCard };
})();
