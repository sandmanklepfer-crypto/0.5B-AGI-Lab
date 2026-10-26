'use strict';
/* ==========================================================================
 *  clock_svg.js —— 生成「静态 SVG 钟表」
 *  --------------------------------------------------------------------------
 *  为什么用 SVG 而不是 CSS 动画：
 *    CSS 动画只能「转」，不能显示【真实当前时间】。
 *    SVG 可以在 bake 时把指针角度算好写死 —— 指针停在哪就是几点几分，
 *    视觉模型截图后能直接读出来。
 *
 *  这就是「视觉状态传递」：
 *    不需要 URL 传参、不需要 JS、不需要服务端
 *    时间被「画」在表盘上，看图就知道快照是什么时候的
 * ========================================================================== */

function hand(cx, cy, len, angleDeg, width, color) {
  const rad = (angleDeg - 90) * Math.PI / 180;
  const x2 = cx + Math.cos(rad) * len;
  const y2 = cy + Math.sin(rad) * len;
  return `<line x1="${cx}" y1="${cy}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"
    stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`;
}

/**
 * @param {Date} t        要显示的时间
 * @param {object} opt    { size, showText }
 * @returns {string}      SVG 字符串
 */
function buildClock(t, opt = {}) {
  const size = opt.size || 200;
  const cx = size / 2, cy = size / 2;
  const R = size / 2 - 8;

  const h = t.getHours() % 12;
  const m = t.getMinutes();
  const s = t.getSeconds();

  /* 角度：12 点方向为 0° */
  const secA = s * 6;
  const minA = m * 6 + s * 0.1;
  const hourA = h * 30 + m * 0.5;

  let out = [];
  out.push(`<svg class="tl-clock" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
    xmlns="http://www.w3.org/2000/svg" role="img"
    aria-label="快照时间 ${String(t.getHours()).padStart(2,'0')}:${String(m).padStart(2,'0')}">`);

  /* 表盘 */
  out.push(`  <circle cx="${cx}" cy="${cy}" r="${R}" fill="#0f151d" stroke="#2dd4bf" stroke-width="2"/>`);
  out.push(`  <circle cx="${cx}" cy="${cy}" r="${R - 6}" fill="none" stroke="#1c2634" stroke-width="1"/>`);

  /* 12 个刻度 */
  for (let i = 0; i < 12; i++) {
    const a = (i * 30 - 90) * Math.PI / 180;
    const r1 = R - (i % 3 === 0 ? 14 : 9);
    const r2 = R - 4;
    const x1 = cx + Math.cos(a) * r1, y1 = cy + Math.sin(a) * r1;
    const x2 = cx + Math.cos(a) * r2, y2 = cy + Math.sin(a) * r2;
    const w = i % 3 === 0 ? 2.5 : 1.5;
    const c = i % 3 === 0 ? '#dde7f0' : '#5d7085';
    out.push(`  <line x1="${x1.toFixed(2)}" y1="${y1.toFixed(2)}" x2="${x2.toFixed(2)}" y2="${y2.toFixed(2)}"
      stroke="${c}" stroke-width="${w}" stroke-linecap="round"/>`);
  }

  /* 时针 / 分针 / 秒针 */
  out.push('  ' + hand(cx, cy, R * 0.50, hourA, 5, '#dde7f0'));
  out.push('  ' + hand(cx, cy, R * 0.72, minA, 3.2, '#8fa3b8'));
  out.push('  ' + hand(cx, cy, R * 0.82, secA, 1.4, '#f87171'));
  out.push(`  <circle cx="${cx}" cy="${cy}" r="4" fill="#2dd4bf"/>`);

  /* 数字时间（给纯文本读的备选） */
  if (opt.showText !== false) {
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(m).padStart(2, '0');
    const ss = String(s).padStart(2, '0');
    out.push(`  <text x="${cx}" y="${size - 4}" text-anchor="middle"
      font-family="ui-monospace,monospace" font-size="11" fill="#5d7085">${hh}:${mm}:${ss}</text>`);
  }

  out.push('</svg>');
  return out.join('\n');
}

module.exports = { buildClock };
