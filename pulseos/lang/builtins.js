'use strict';
/* ==========================================================================
 *  builtins.js —— 内置函数（唯一真源）
 *  --------------------------------------------------------------------------
 *  解释器（pulsescript.js）和编译器（compile.js）都从这里取，
 *  保证两边行为完全一致 —— 否则解释执行和编译执行的语义会漂移。
 * ========================================================================== */

module.exports = {
  /* --- 基础 --- */
  len: (x) => (x == null ? 0 : (Array.isArray(x) ? x.length : (typeof x === 'string' ? x.length : Object.keys(x).length))),
  now: () => Date.now(),
  int: (x) => Math.trunc(Number(x) || 0),
  num: (x) => Number(x) || 0,
  str: (x) => String(x == null ? '' : x),
  bool: (x) => !!x,
  min: (a, b) => Math.min(a, b),
  max: (a, b) => Math.max(a, b),
  abs: (x) => Math.abs(x),
  floor: (x) => Math.floor(x),
  round: (x) => Math.round(x),

  /* --- 列表 --- */
  slice: (a, s, e) => (a || []).slice(s, e),
  sum: (a) => (a || []).reduce((x, y) => x + (Number(y) || 0), 0),
  first: (a) => (a && a.length ? a[0] : null),
  last: (a) => (a && a.length ? a[a.length - 1] : null),
  reverse: (a) => (a || []).slice().reverse(),
  sort: (a) => (a || []).slice().sort((x, y) => (x > y ? 1 : x < y ? -1 : 0)),
  unique: (a) => [...new Set(a || [])],
  flatten: (a) => (a || []).reduce((o, x) => o.concat(Array.isArray(x) ? x : [x]), []),
  range: (n) => Array.from({ length: Math.max(0, n | 0) }, (_, i) => i),
  indexOf: (a, v) => (a || []).indexOf(v),
  contains: (a, v) => (Array.isArray(a) ? a.indexOf(v) >= 0 : String(a == null ? '' : a).indexOf(String(v)) >= 0),

  /* --- 高阶（无闭包语法，用字段名代替） --- */
  pluck: (a, key) => (a || []).map(x => (x == null ? null : x[key])),
  filterGt: (a, key, n) => (a || []).filter(x => { const v = key ? x[key] : x; return Number(v) > n; }),
  filterLt: (a, key, n) => (a || []).filter(x => { const v = key ? x[key] : x; return Number(v) < n; }),
  filterEq: (a, key, v) => (a || []).filter(x => (key ? x[key] : x) === v),
  sumBy: (a, key) => (a || []).reduce((o, x) => o + (Number(key ? x[key] : x) || 0), 0),
  avgBy: (a, key) => (a && a.length ? (a.reduce((o, x) => o + (Number(key ? x[key] : x) || 0), 0) / a.length) : 0),
  maxBy: (a, key) => (a && a.length ? Math.max(...a.map(x => Number(key ? x[key] : x) || 0)) : 0),
  minBy: (a, key) => (a && a.length ? Math.min(...a.map(x => Number(key ? x[key] : x) || 0)) : 0),
  countBy: (a, key, v) => (a || []).filter(x => (key ? x[key] : x) === v).length,

  /* --- 字符串 --- */
  upper: (s) => String(s == null ? '' : s).toUpperCase(),
  lower: (s) => String(s == null ? '' : s).toLowerCase(),
  trim: (s) => String(s == null ? '' : s).trim(),
  split: (s, d) => String(s == null ? '' : s).split(d == null ? ',' : d),
  join: (a, d) => (a || []).join(d == null ? ',' : d),
  substr: (s, a, b) => String(s == null ? '' : s).substr(a, b),
  replace: (s, a, b) => String(s == null ? '' : s).split(String(a)).join(String(b)),
  startsWith: (s, p) => String(s == null ? '' : s).startsWith(String(p)),
  endsWith: (s, p) => String(s == null ? '' : s).endsWith(String(p)),

  /* --- 字典 --- */
  keys: (o) => Object.keys(o || {}),
  values: (o) => Object.values(o || {}),
  has: (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k),
  get: (o, k, d) => (o != null && o[k] !== undefined ? o[k] : (d === undefined ? null : d)),
  put: (o, k, v) => { const c = Object.assign({}, o || {}); c[k] = v; return c; },
  del: (o, k) => { const c = Object.assign({}, o || {}); delete c[k]; return c; },
  size: (o) => (o == null ? 0 : Object.keys(o).length),
};
