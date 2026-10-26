'use strict';
/* PulseOS 控制台前端 —— 零依赖 */

const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const n = document.createElement(t); if (c) n.className = c; if (h !== undefined) n.innerHTML = h; return n; };

let STATE = null;

/* ---------------- 输出 ---------------- */
function out(msg, cls) {
  const p = $('#out');
  const line = el('span', cls || '', String(msg) + '\n');
  p.appendChild(line);
  p.scrollTop = p.scrollHeight;
}
const fmtB = (n) => (n >= 1024 ? (n / 1024).toFixed(1) + ' KB' : n + ' B');

/* ---------------- 拉状态 ---------------- */
async function refresh() {
  try {
    const r = await fetch('/api/state');
    STATE = await r.json();
    render();
  } catch (e) {
    out('拉取失败: ' + e.message, 'bad');
  }
}

function render() {
  if (!STATE) return;
  const s = STATE.system;

  /* KPI */
  $('#kpis').innerHTML = [
    ['服务', s.services, '个'],
    ['总脉冲', s.totalPulses, '次'],
    ['状态合计', s.totalStateBytes, 'B'],
    ['因果边', s.causalEdges, '条'],
    ['运行', Math.floor(s.uptimeMs / 1000), 's'],
  ].map(([k, v, u]) => `<div class="kpi"><b>${v}<small>${u}</small></b><span>${k}</span></div>`).join('');

  $('#sysline').textContent =
    `${s.services} 服务 · ${s.totalPulses} 脉冲 · ${s.totalStateBytes}B`;
  $('#svcCount').textContent = s.services;

  /* 服务卡片 */
  const box = $('#services');
  box.innerHTML = '';
  if (!STATE.services.length) {
    box.appendChild(el('div', 'cau empty', '还没有服务。点右上角「新建服务」，或用「编译并部署」。'));
  }
  for (const k of STATE.services) {
    const sizeBadge = k.stateBytes <= 256 ? 'good' : k.stateBytes <= 1024 ? 'mid' : 'bad';
    const card = el('div', 'svc');
    card.innerHTML = `
      <div class="svc-h">
        <span class="svc-n">${k.name}</span>
        <span class="svc-badge ${sizeBadge}">${fmtB(k.stateBytes)}</span>
      </div>
      <div class="svc-m">
        <span>脉冲 <i>${k.pulses}</i></span>
        <span>派生 <i>${k.emits}</i></span>
        <span>错误 <i>${k.errors}</i></span>
        <span>p95 <i>${k.lat.p95 == null ? '—' : k.lat.p95 + 'ms'}</i></span>
      </div>
      <div class="ops"></div>
      <div class="svc-act"></div>`;

    const opsBox = card.querySelector('.ops');
    for (const h of k.handlers) {
      const b = el('button', 'op', h.op + (h.params.length ? '(' + h.params.join(',') + ')' : ''));
      b.onclick = () => pulse(k.name, h.op, h.params.length);
      opsBox.appendChild(b);
    }
    if (!k.handlers.length) opsBox.appendChild(el('span', 'op', '（无处理器）'));

    const act = card.querySelector('.svc-act');
    const bd = el('button', 'btn small', '状态');
    bd.onclick = () => out(`${k.name} 状态 (${k.stateBytes}B): ${k.state}`, 'dim');
    act.appendChild(bd);
    const be = el('button', 'btn small', '导出状态箱');
    be.onclick = () => doExport(k.name);
    act.appendChild(be);
    const bx = el('button', 'btn small danger', '卸载');
    bx.onclick = () => unregister(k.name);
    act.appendChild(bx);

    box.appendChild(card);
  }

  /* 因果链 */
  const c = $('#causal');
  c.innerHTML = '';
  if (!STATE.causal.length) {
    c.appendChild(el('div', 'cau empty', '还没有调用。点上面某个服务的方法试试。'));
  } else {
    for (const x of STATE.causal.slice().reverse()) {
      const d = new Date(x.t);
      const hh = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') + ':' + String(d.getSeconds()).padStart(2, '0');
      const row = el('div', 'cau');
      const chain = x.chain.map((n, i) => (i === 0 ? '<b>' + n + '</b>' : n)).join('<span class="arr">→</span>');
      row.innerHTML = `<time>${hh}</time><span class="chain">${chain}</span><span class="ms">${x.ms}ms</span>`;
      c.appendChild(row);
    }
  }
}

/* ---------------- 调用 ---------------- */
async function pulse(service, op, needArgs) {
  let args = [];
  if (needArgs) {
    const v = prompt(`调用 ${service}.${op}()\n请输入参数（多个用英文逗号分隔，数字会自动转换）：`, '');
    if (v === null) return;
    args = v.split(',').map(s => {
      s = s.trim();
      if (s === '') return '';
      if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
      if (s === 'true') return true;
      if (s === 'false') return false;
      return s;
    });
  }
  try {
    const r = await fetch('/api/pulse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service, op, args }),
    });
    const d = await r.json();
    if (d.ok) {
      out(`▸ ${service}.${op}() → ${JSON.stringify(d.result)}`, 'ok');
      for (const t of d.trace) {
        out(`    ${t.service}.${t.op}  ${t.ms == null ? '—' : t.ms + 'ms'}  ${t.stateBytes != null ? t.stateBytes + 'B' : ''}`, 'dim');
      }
    } else {
      out(`✗ ${service}.${op}() → ${d.error || (d.trace && d.trace[0] && d.trace[0].error) || '失败'}`, 'bad');
    }
    await refresh();
  } catch (e) {
    out('调用失败: ' + e.message, 'bad');
  }
}

/* ---------------- 导出 ---------------- */
async function doExport(name) {
  try {
    const r = await fetch('/api/export/' + encodeURIComponent(name));
    const d = await r.json();
    if (!d.ok) return out('导出失败: ' + d.error, 'bad');
    out(`▸ ${name} 状态箱 ${d.bytes} 字节（base64 前 80 字符）`, 'acc');
    out('    ' + d.base64.slice(0, 80) + (d.base64.length > 80 ? '…' : ''), 'dim');
    out('    这个字符串就是全部需要持久化的东西。', 'dim');
  } catch (e) { out('导出失败: ' + e.message, 'bad'); }
}

/* ---------------- 卸载 ---------------- */
async function unregister(name) {
  if (!confirm(`确定卸载 ${name}？\n状态箱会被删除（不可恢复）。`)) return;
  const r = await fetch('/api/service/' + encodeURIComponent(name), { method: 'DELETE' });
  const d = await r.json();
  out('▸ 已卸载 ' + name, 'ok');
  await refresh();
}

/* ---------------- 编译 / 部署 ---------------- */
async function check() {
  const src = $('#src').value;
  const r = await fetch('/api/compile', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src }),
  });
  const d = await r.json();
  const box = $('#diag');
  const parts = [];
  if (d.errors && d.errors.length) for (const e of d.errors) parts.push('<div class="e">✗ ' + e + '</div>');
  if (d.warnings && d.warnings.length) for (const w of d.warnings) parts.push('<div class="w">⚠ ' + w + '</div>');
  if (d.services) {
    for (const s of d.services) {
      parts.push(`<div class="s">✓ ${s.name} · ${s.handlers.length} 个方法 [${s.handlers.join(', ')}] · 初始状态 ${s.initialBytes}B · ${s.verdict}</div>`);
    }
  }
  if (!parts.length) parts.push('<div class="s">✓ 无问题</div>');
  box.innerHTML = parts.join('');
  return d;
}

async function deploy() {
  const src = $('#src').value;
  const d = await check();
  if (!d.ok) return out('✗ 编译失败，未部署', 'bad');
  const r = await fetch('/api/deploy', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ src }),
  });
  const res = await r.json();
  if (res.ok) {
    out('▸ 已部署 ' + res.name, 'ok');
    await refresh();
  } else {
    out('✗ 部署失败: ' + res.error, 'bad');
  }
}

/* ---------------- 模板 ---------------- */
const TEMPLATE = `# 新建服务 —— 改完点「编译并部署」
#
# 三条铁律：
#   1. state 必须小（编译时右下角会显示预估大小）
#   2. 历史数据进日志，不进 state
#   3. emit 会在全局自动路由到声明了同名 on 的服务

service myservice {
  state {
    items: list = []
    n: int = 0
  }

  on "add"(text) {
    append(items, text)
    set n = n + 1
    if len(items) > 20 {
      set items = slice(items, len(items) - 20, len(items))
    }
    emit "changed" { n: n }
  }

  on "list" {
    return items
  }

  on "stats" {
    return { count: n, size: len(items) }
  }
}
`;

/* ---------------- 绑定 ---------------- */
$('#btnRefresh').onclick = refresh;
$('#btnCheck').onclick = check;
$('#btnDeploy').onclick = deploy;
$('#btnNew').onclick = () => {
  $('#src').value = TEMPLATE;
  $('#diag').innerHTML = '';
  $('#editorPanel').scrollIntoView({ behavior: 'smooth' });
  out('▸ 已载入模板，改完点「编译并部署」', 'dim');
};
$('#btnClearOut').onclick = () => { $('#out').textContent = ''; };

/* Ctrl+Enter 部署 */
$('#src').addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); deploy(); }
  if (e.key === 'Tab') {
    e.preventDefault();
    const t = e.target, p = t.selectionStart;
    t.value = t.value.slice(0, p) + '  ' + t.value.slice(t.selectionEnd);
    t.selectionStart = t.selectionEnd = p + 2;
  }
});

/* 启动 */
$('#src').value = TEMPLATE;
refresh();
setInterval(refresh, 4000);

out('◈ PulseOS 控制台已连接', 'acc');
out('  这是一个聚合外壳：下面每个服务都是一个独立的微内核，', 'dim');
out('  各自持有自己的状态箱，通过 emit 形成因果链。', 'dim');
out('', 'dim');
