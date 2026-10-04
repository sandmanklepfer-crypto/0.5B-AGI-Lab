/* 推广员 / 团长：生成带归因的专属报名链接 + 邀请话术 + 二维码 */
(function () {
  const $ = s => document.querySelector(s);
  const LSKEY = 'lh_tg_hist';

  function baseUrl() {
    // 报名页和本页在同一目录，直接用绝对地址，方便复制到微信
    return location.origin + location.pathname.replace(/[^/]*$/, '') + 'join.html';
  }

  function makeLink(name) {
    return baseUrl() + '?ref=' + encodeURIComponent(name);
  }

  function makeWords(name, link) {
    return '老板你好～我们这边可以免费给你的店做一个微信下单页面：\n' +
      '· 顾客手机点开就下单，钱直接进你自己的微信/支付宝\n' +
      '· 不用开发、不用服务器、不收开店费\n' +
      '· 有人教你怎么用，改价、上架、发优惠券都很简单\n\n' +
      '想开的话点这里填一下资料（30 秒）：\n' + link + '\n\n' +
      '（推荐人：' + name + '，有问题也可以直接问我）';
  }

  /* 依赖库都没有时，退化成"可点/可长按"的文本，不报错 */
  function renderQR(link) {
    const box = $('#qrBox');
    box.innerHTML = '<div class="qr-ph">把链接复制到微信里发给商家即可；' +
      '需要二维码的话，可长按下面的链接 → 在微信里"识别图中二维码"通常用不了，' +
      '建议直接用链接。<br><span style="font-size:12px;word-break:break-all">' + LH.esc(link) + '</span></div>';
  }

  function addHist(name, link) {
    let h = LH.LS.get(LSKEY, []);
    h = h.filter(x => x.name !== name);
    h.unshift({ name: name, link: link, at: new Date().toLocaleString('zh-CN') });
    h = h.slice(0, 20);
    LH.LS.set(LSKEY, h);
    renderHist();
  }

  function renderHist() {
    const h = LH.LS.get(LSKEY, []);
    const box = $('#hist');
    if (!h.length) { box.innerHTML = '<div style="color:var(--muted)">还没有生成过</div>'; return; }
    box.innerHTML = h.map(x =>
      '<div><b>' + LH.esc(x.name) + '</b> <span style="color:var(--muted)">· ' + LH.esc(x.at) + '</span><br>' +
      '<a href="' + LH.esc(x.link) + '" target="_blank" rel="noopener">' + LH.esc(x.link) + '</a></div>'
    ).join('');
  }

  function gen() {
    const name = $('#tgName').value.trim().replace(/\s+/g, '');
    if (!name) { LH.toast('先填个名字或编号'); return; }
    if (name.length > 20) { LH.toast('太长了，20 字以内'); return; }

    const link = makeLink(name);
    const words = makeWords(name, link);

    $('#outLink').textContent = link;
    $('#outWords').textContent = words;
    $('#btnOpen').href = link;
    $('#outWrap').classList.remove('hidden');
    renderQR(link);
    addHist(name, link);
    $('#outWrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function boot() {
    $('#btnGen').onclick = gen;
    $('#tgName').addEventListener('keydown', e => { if (e.key === 'Enter') gen(); });
    $('#btnCopyLink').onclick = async () => { await LH.copyText($('#outLink').textContent); LH.toast('链接已复制 ✅'); };
    $('#btnCopyWords').onclick = async () => { await LH.copyText($('#outWords').textContent); LH.toast('邀请话术已复制 ✅'); };
    $('#btnClear').onclick = () => { if (confirm('清空本机历史？')) { LH.LS.del(LSKEY); renderHist(); } };
    renderHist();

    // 支持 ?name=xxx 预填
    const n = new URLSearchParams(location.search).get('name');
    if (n) { $('#tgName').value = n; gen(); }
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
