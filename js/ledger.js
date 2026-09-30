/* 对账台：输入收到的金额 → 用「唯一金额尾数」反查订单 → 一键标记已收款 */
(function () {
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const esc = LH.esc, money = LH.money;
  const KEY = 'lh_ledger';
  let orders = LH.LS.get(KEY, []);
  let filter = 'all';

  const save = () => LH.LS.set(KEY, orders);

  /* 金额归一化 / 尾数 / 订单文本解析 —— 全部复用共享模块，保证与顾客端一致 */
  const parseAmount = s => OrderID.parsePaidAmount(s);
  const tailOf = s => OrderID.tailOf(s);
  function parseOrder(text) {
    const o = OrderID.parseOrderText(text);
    if (!o) return null;
    o.at = Date.now();
    o.status = 'WAIT';
    return o;
  }

  /* ---------- 渲染 ---------- */
  function render() {
    const wait = orders.filter(o => o.status === 'WAIT');
    const paid = orders.filter(o => o.status === 'PAID');
    const sum = paid.reduce((a, o) => a + o.payFen, 0);
    $('#stat').textContent = '待收 ' + wait.length + ' 单　已收 ¥' + OrderID.fmtFen(sum);

    let list = orders;
    if (filter === 'wait') list = wait;
    if (filter === 'paid') list = paid;

    if (!list.length) {
      $('#list').innerHTML = '<div class="box" style="text-align:center;color:var(--muted);padding:26px">' +
        (orders.length ? '这个分类下没有订单' : '还没有登记订单<br><span style="font-size:12.5px">把顾客发来的订单粘贴到上面②，就会出现在这里</span>') +
        '</div>';
      return;
    }

    $('#list').innerHTML = list.map((o, i) => {
      const idx = orders.indexOf(o);
      const st = o.status === 'PAID'
        ? '<span class="tag p">已收款</span>'
        : '<span class="tag w">待收款</span>';
      return '<div class="ord-card ' + (o.status === 'PAID' ? 'paid' : '') + '">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">' +
          '<span class="no mono" style="font-weight:700">' + esc(o.code) + '</span>' + st +
        '</div>' +
        '<div class="money" style="font-size:18px;font-weight:800;color:var(--brand);margin-top:3px">¥' + esc(o.payText) + '</div>' +
        '<div class="meta">' +
          '指针 <b class="mono">' + esc(o.pointer) + '</b>' +
          '　尾数 <b>' + esc(OrderID.tailText(o.tailFen)) + '</b><br>' +
          (o.name ? '👤 ' + esc(o.name) + '　' : '') +
          (o.phone ? '📞 ' + esc(o.phone) + '<br>' : '') +
          (o.address ? '📍 ' + esc(o.address) + '<br>' : '') +
          '🕐 ' + new Date(o.at).toLocaleString('zh-CN', { hour12: false }) +
        '</div>' +
        '<div class="row-actions" style="margin-top:9px">' +
          (o.status === 'WAIT'
            ? '<button class="mini go" data-paid="' + idx + '">✓ 已收到这笔钱</button>'
            : '<button class="mini" data-undone="' + idx + '">撤销</button>') +
          '<button class="mini" data-copy="' + idx + '">复制单号</button>' +
          '<button class="mini danger" data-del="' + idx + '">删除</button>' +
        '</div>' +
      '</div>';
    }).join('');

    $$('#list [data-paid]').forEach(b => b.onclick = () => {
      orders[Number(b.dataset.paid)].status = 'PAID';
      orders[Number(b.dataset.paid)].paidAt = Date.now();
      save(); render(); LH.toast('已标记收款 ✅');
    });
    $$('#list [data-undone]').forEach(b => b.onclick = () => {
      orders[Number(b.dataset.undone)].status = 'WAIT';
      save(); render();
    });
    $$('#list [data-del]').forEach(b => b.onclick = () => {
      const i = Number(b.dataset.del);
      if (confirm('删除 ' + orders[i].code + '？')) { orders.splice(i, 1); save(); render(); }
    });
    $$('#list [data-copy]').forEach(b => b.onclick = async () => {
      await LH.copyText(orders[Number(b.dataset.copy)].code); LH.toast('已复制');
    });
  }

  /* ---------- 金额匹配 ---------- */
  function match() {
    const raw = $('#amtIn').value.trim();
    const box = $('#matchBox');
    if (!raw) { box.innerHTML = ''; return; }

    const fen = parseAmount(raw);
    const t = tailOf(raw);
    let hits = [];

    if (fen) hits = orders.filter(o => o.payFen === fen);
    // 没精确命中：按尾数兜底
    if (!hits.length && t) {
      hits = orders.filter(o => (o.tailFen === t) && o.status === 'WAIT');
      if (!hits.length) hits = orders.filter(o => o.tailFen === t);
    }

    if (!hits.length) {
      box.innerHTML = '<div class="match miss">' +
        '<b>没找到匹配的订单</b>' +
        '<div style="font-size:12.5px;color:var(--muted);margin-top:5px;line-height:1.8">' +
        '可能原因：<br>· 这单还没登记（去上面②粘贴顾客的订单）<br>· 金额输错了<br>· 顾客付的金额不是约定金额' +
        '</div></div>';
      return;
    }

    box.innerHTML = hits.map(o => {
      const idx = orders.indexOf(o);
      return '<div class="match hit">' +
        '<div class="hd"><span class="no">' + esc(o.code) + '</span>' +
        '<span class="money">¥' + esc(o.payText) + '</span></div>' +
        '<div class="meta">' +
          '指针 <b class="mono">' + esc(o.pointer) + '</b>　尾数 <b>' + esc(OrderID.tailText(o.tailFen)) + '</b><br>' +
          (o.name ? '👤 ' + esc(o.name) + '　' : '') + (o.phone ? '📞 ' + esc(o.phone) : '') +
        '</div>' +
        (o.status === 'PAID'
          ? '<div style="margin-top:8px;color:var(--ok);font-weight:700">这笔已经收过了</div>'
          : '<button class="btn-primary btn-block" style="margin-top:9px" data-ok="' + idx + '">✓ 确认收到，标记这一单</button>') +
      '</div>';
    }).join('');

    $$('#matchBox [data-ok]').forEach(b => b.onclick = () => {
      const i = Number(b.dataset.ok);
      orders[i].status = 'PAID'; orders[i].paidAt = Date.now();
      save(); render(); match(); LH.toast('对账完成 ✅');
    });

    if (hits.length > 1) {
      box.insertAdjacentHTML('beforeend',
        '<div style="font-size:12px;color:var(--warn);margin-top:8px">⚠️ 有 ' + hits.length +
        ' 单金额相同，请核对顾客给的「指针码」再确认</div>');
    }
  }

  /* ---------- 绑定 ---------- */
  function bind() {
    $('#amtIn').oninput = match;
    $('#btnClear').onclick = () => { $('#amtIn').value = ''; match(); };
    $$('.quick [data-add]').forEach(b => b.onclick = () => {
      const fen = parseAmount($('#amtIn').value);
      if (!fen) return;
      $('#amtIn').value = OrderID.fmtFen(fen + Math.round(parseFloat(b.dataset.add) * 100));
      match();
    });
    $('#btnAdd').onclick = () => {
      const o = parseOrder($('#pasteIn').value);
      if (!o) { $('#addMsg').innerHTML = '<div class="status err">没读出订单号，检查一下粘贴的内容</div>'; return; }
      if (orders.some(x => x.code === o.code)) {
        $('#addMsg').innerHTML = '<div class="status warn">这单已经登记过了</div>'; return;
      }
      orders.unshift(o); save(); render();
      $('#pasteIn').value = '';
      $('#addMsg').innerHTML = '<div class="status ok">✅ 已登记 ' + esc(o.code) + '（¥' + esc(o.payText) + '）</div>';
    };
    $('#btnSample').onclick = () => {
      const no = OrderID.makeOrderNo();
      const a = OrderID.uniqueAmount(56, no);
      $('#pasteIn').value = '【订单】阿香卤味\n订单号：' + no +
        '\n合计应付：¥56\n★ 请支付：¥' + a.display + '（尾数 ' + a.tailText + ' 是识别码，必须一分不差）' +
        '\n★ 订单指针：' + OrderID.pointerOf(no) +
        '\n收货人：张三\n电话：13800138000\n地址：幸福小区 3 栋 601';
    };
    $('#btnExport').onclick = () => {
      const blob = new Blob([JSON.stringify(orders, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '对账台账-' + new Date().toISOString().slice(0, 10) + '.json';
      a.click();
    };
    $$('.tab').forEach(t => t.onclick = () => {
      $$('.tab').forEach(x => x.classList.remove('on'));
      t.classList.add('on'); filter = t.dataset.f; render();
    });
  }

  document.addEventListener('DOMContentLoaded', () => { bind(); render(); });
})();
