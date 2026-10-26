'use strict';
/* ==========================================================================
 *  PulseScript —— 脉冲原生的声明式语言
 *  --------------------------------------------------------------------------
 *  设计目标只有三条：
 *    1. 强制小状态（编译期就告诉你 state 有多大）
 *    2. 只描述「因果与时序」，不描述内存与指针
 *    3. AI 友好 —— 没有继承、没有泛型、没有生命周期标注
 *
 *  语法（全部）：
 *
 *      service notes {
 *        state {
 *          items: list = []
 *          count: int  = 0
 *        }
 *
 *        on "add"(text) {
 *          append(items, text)
 *          set count = count + 1
 *          emit "changed" { n: count }
 *        }
 *
 *        on "list" {
 *          return items
 *        }
 *      }
 *
 *  关键字：service state on let set append return emit if
 *  类型：  int str list map bool
 * ========================================================================== */

/* ============================ 1. 词法 ============================ */
const KEYWORDS = new Set(['service', 'state', 'on', 'let', 'set', 'append', 'return', 'emit', 'if', 'else', 'true', 'false']);

function lex(src) {
  const out = [];
  let i = 0, line = 1;
  const push = (t, v) => out.push({ t, v, line });

  while (i < src.length) {
    const c = src[i];

    if (c === '\n') { line++; i++; continue; }
    if (c === ' ' || c === '\t' || c === '\r') { i++; continue; }

    // 注释
    if (c === '#') { while (i < src.length && src[i] !== '\n') i++; continue; }
    if (c === '/' && src[i + 1] === '/') { while (i < src.length && src[i] !== '\n') i++; continue; }

    // 字符串
    if (c === '"' || c === "'") {
      const q = c; i++;
      let s = '';
      while (i < src.length && src[i] !== q) {
        if (src[i] === '\\') { s += src[i + 1] === 'n' ? '\n' : src[i + 1]; i += 2; }
        else s += src[i++];
      }
      if (i >= src.length) throw err('字符串未闭合', line);
      i++; push('str', s); continue;
    }

    // 数字
    if (/[0-9]/.test(c)) {
      let n = '';
      while (i < src.length && /[0-9._]/.test(src[i])) { if (src[i] !== '_') n += src[i]; i++; }
      push('num', parseFloat(n)); continue;
    }

    // 标识符 / 关键字
    if (/[A-Za-z_$]/.test(c)) {
      let id = '';
      while (i < src.length && /[A-Za-z0-9_$]/.test(src[i])) id += src[i++];
      push(KEYWORDS.has(id) ? 'kw' : 'id', id); continue;
    }

    // 多字符符号
    const two = src.substr(i, 2);
    if (['==', '!=', '<=', '>=', '&&', '||', '->'].includes(two)) { push('op', two); i += 2; continue; }

    // 单字符
    if ('{}()[],:.=+-*/<>!'.includes(c)) { push('op', c); i++; continue; }

    throw err('无法识别的字符 "' + c + '"', line);
  }
  push('eof', null);
  return out;
}

function err(msg, line) {
  const e = new Error(msg + (line ? ' (第 ' + line + ' 行)' : ''));
  e.line = line;
  return e;
}

/* ============================ 2. 语法 ============================ */
function parse(tokens) {
  let p = 0;
  const peek = (k = 0) => tokens[p + k];
  const next = () => tokens[p++];
  const isKw = (v, k = 0) => peek(k).t === 'kw' && peek(k).v === v;
  const isOp = (v, k = 0) => peek(k).t === 'op' && peek(k).v === v;

  function expect(v) {
    const t = next();
    if (t.t !== 'op' && t.t !== 'kw') throw err('期望 "' + v + '"，得到 "' + t.v + '"', t.line);
    if (t.v !== v) throw err('期望 "' + v + '"，得到 "' + t.v + '"', t.line);
    return t;
  }

  /* ---- 程序 ---- */
  function program() {
    const services = [];
    while (peek().t !== 'eof') {
      if (isKw('service')) services.push(service());
      else throw err('顶层只能是 service，得到 "' + peek().v + '"', peek().line);
    }
    return { services };
  }

  function service() {
    next(); // service
    const name = next();
    if (name.t !== 'id') throw err('service 需要名字', name.line);
    expect('{');

    const svc = { name: name.v, state: [], handlers: [] };
    while (!isOp('}')) {
      if (isKw('state')) svc.state = stateBlock();
      else if (isKw('on')) svc.handlers.push(handler());
      else throw err('service 里只能是 state 或 on，得到 "' + peek().v + '"', peek().line);
    }
    expect('}');
    return svc;
  }

  function stateBlock() {
    next(); // state
    expect('{');
    const fields = [];
    while (!isOp('}')) {
      const nm = next();
      if (nm.t !== 'id') throw err('字段名非法', nm.line);
      expect(':');
      const ty = next();
      if (ty.t !== 'id') throw err('类型非法', ty.line);
      let def = null;
      if (isOp('=')) { next(); def = expr(); }
      fields.push({ name: nm.v, type: ty.v, def });
      if (isOp(',')) next();
    }
    expect('}');
    return fields;
  }

  function handler() {
    next(); // on
    const op = next();
    if (op.t !== 'str') throw err('on 后面要跟字符串，如 on "add"', op.line);

    const params = [];
    if (isOp('(')) {
      next();
      while (!isOp(')')) {
        const a = next();
        if (a.t !== 'id') throw err('参数名非法', a.line);
        params.push(a.v);
        if (isOp(',')) next();
      }
      expect(')');
    }
    expect('{');
    const body = block();
    return { op: op.v, params, body };
  }

  function block() {
    const stmts = [];
    while (!isOp('}')) {
      if (peek().t === 'eof') throw err('块未闭合', peek().line);
      stmts.push(stmt());
    }
    expect('}');
    return stmts;
  }

  function stmt() {
    // let x = expr
    if (isKw('let')) {
      next();
      const nm = next();
      expect('=');
      return { k: 'let', name: nm.v, e: expr() };
    }
    // set x = expr
    if (isKw('set')) {
      next();
      const nm = next();
      expect('=');
      return { k: 'set', name: nm.v, e: expr() };
    }
    // append(list, item)
    if (isKw('append')) {
      next();
      expect('(');
      const target = next().v;
      expect(',');
      const e = expr();
      expect(')');
      return { k: 'append', target, e };
    }
    // return expr
    if (isKw('return')) {
      next();
      // 注意：不能直接用 isOp('}') 判断空返回，
      // 因为 return { ... } 的 '{' 看起来也一样。
      // 这里用「下一个是 '}' 且再下一个也是语句边界」的近似判断。
      if (isOp('}')) return { k: 'return', e: null };
      return { k: 'return', e: expr() };
    }
    // emit "op" { k: v } [after ms]
    if (isKw('emit')) {
      next();
      const op = next();
      if (op.t !== 'str') throw err('emit 后面要跟字符串', op.line);
      let payload = null;
      if (isOp('{')) {
        next();
        payload = [];
        while (!isOp('}')) {
          const k = next();
          if (k.t !== 'id' && k.t !== 'str') throw err('对象键非法', k.line);
          expect(':');
          payload.push([k.v, expr()]);
          if (isOp(',')) next();
        }
        expect('}');
      }
      let after = null;
      if (isKw('after')) { next(); after = expr(); }
      return { k: 'emit', op: op.v, payload, after };
    }
    // if cond { } [else { }]
    if (isKw('if')) {
      next();
      const cond = expr();
      expect('{');
      const then = block();
      let els = null;
      if (isKw('else')) { next(); expect('{'); els = block(); }
      return { k: 'if', cond, then, els };
    }
    // 表达式语句
    const e = expr();
    return { k: 'expr', e };
  }

  /* ---- 表达式（优先级爬升） ---- */
  function expr() { return orExpr(); }

  function orExpr() {
    let l = andExpr();
    while (isOp('||')) { next(); l = { k: 'bin', op: '||', l, r: andExpr() }; }
    return l;
  }
  function andExpr() {
    let l = eqExpr();
    while (isOp('&&')) { next(); l = { k: 'bin', op: '&&', l, r: eqExpr() }; }
    return l;
  }
  function eqExpr() {
    let l = cmpExpr();
    while (isOp('==') || isOp('!=')) { const o = next().v; l = { k: 'bin', op: o, l, r: cmpExpr() }; }
    return l;
  }
  function cmpExpr() {
    let l = addExpr();
    while (isOp('<') || isOp('>') || isOp('<=') || isOp('>=')) {
      const o = next().v; l = { k: 'bin', op: o, l, r: addExpr() };
    }
    return l;
  }
  function addExpr() {
    let l = mulExpr();
    while (isOp('+') || isOp('-')) { const o = next().v; l = { k: 'bin', op: o, l, r: mulExpr() }; }
    return l;
  }
  function mulExpr() {
    let l = unary();
    while (isOp('*') || isOp('/')) { const o = next().v; l = { k: 'bin', op: o, l, r: unary() }; }
    return l;
  }
  function unary() {
    if (isOp('!')) { next(); return { k: 'un', op: '!', e: unary() }; }
    if (isOp('-')) { next(); return { k: 'un', op: '-', e: unary() }; }
    return postfix();
  }
  function postfix() {
    let e = primary();
    while (true) {
      if (isOp('.')) { next(); const f = next(); e = { k: 'member', o: e, f: f.v }; }
      else if (isOp('(')) {
        next();
        const args = [];
        while (!isOp(')')) { args.push(expr()); if (isOp(',')) next(); }
        expect(')');
        e = { k: 'call', callee: e, args };
      } else break;
    }
    return e;
  }
  function primary() {
    const t = peek();
    if (t.t === 'num') { next(); return { k: 'num', v: t.v }; }
    if (t.t === 'str') { next(); return { k: 'str', v: t.v }; }
    if (t.t === 'kw' && (t.v === 'true' || t.v === 'false')) { next(); return { k: 'bool', v: t.v === 'true' }; }
    if (t.t === 'kw' && t.v === 'if') throw err('if 不能作表达式', t.line);
    if (t.t === 'id') { next(); return { k: 'id', v: t.v }; }
    if (isOp('(')) { next(); const e = expr(); expect(')'); return e; }
    if (isOp('[')) {
      next();
      const items = [];
      while (!isOp(']')) { items.push(expr()); if (isOp(',')) next(); }
      expect(']');
      return { k: 'list', items };
    }
    // 对象字面量 { k: v, ... }
    if (isOp('{')) {
      next();
      const props = [];
      while (!isOp('}')) {
        const k = next();
        if (k.t !== 'id' && k.t !== 'str') throw err('对象键非法', k.line);
        expect(':');
        props.push([String(k.v), expr()]);
        if (isOp(',')) next();
      }
      expect('}');
      return { k: 'obj', props };
    }
    throw err('无法解析的表达式 "' + t.v + '"', t.line);
  }

  return program();
}

/* ============================ 3. 静态检查 ============================ */
function check(prog) {
  const errors = [];
  const warnings = [];
  for (const svc of prog.services) {
    const fieldNames = new Set(svc.state.map(f => f.name));

    // 状态默认值类型检查
    for (const f of svc.state) {
      const ty = f.type;
      if (!['int', 'str', 'list', 'map', 'bool'].includes(ty)) {
        errors.push(`[${svc.name}] 未知类型 "${ty}"，可用：int str list map bool`);
      }
    }

    // handler 里引用的字段必须已声明
    for (const h of svc.handlers) {
      walk(h.body, (node) => {
        if (node.k === 'set' && !fieldNames.has(node.name)) {
          errors.push(`[${svc.name}] on "${h.op}": set 了未声明的字段 "${node.name}"`);
        }
        if (node.k === 'append' && !fieldNames.has(node.target)) {
          errors.push(`[${svc.name}] on "${h.op}": append 到未声明的字段 "${node.target}"`);
        }
      });
    }

    // 重复 op 检查
    const seen = new Set();
    for (const h of svc.handlers) {
      if (seen.has(h.op)) errors.push(`[${svc.name}] 重复的 on "${h.op}"`);
      seen.add(h.op);
    }

    if (!svc.handlers.length) warnings.push(`[${svc.name}] 没有任何 on 处理器，服务无法被调用`);
  }
  return { errors, warnings };
}

function walk(stmts, fn) {
  for (const s of stmts) {
    fn(s);
    if (s.k === 'if') { walk(s.then, fn); if (s.els) walk(s.els, fn); }
  }
}

/* ============================ 4. 解释执行 ============================ */
function makeState(svc) {
  const st = {};
  for (const f of svc.state) {
    st[f.name] = f.def === null ? defaultOf(f.type) : evalExpr(f.def, {}, {});
  }
  return st;
}

function defaultOf(ty) {
  return { int: 0, str: '', list: [], map: {}, bool: false }[ty];
}

const BUILTINS = {
  len: (x) => (x == null ? 0 : (Array.isArray(x) ? x.length : (typeof x === 'string' ? x.length : Object.keys(x).length))),
  now: () => Date.now(),
  int: (x) => Math.trunc(Number(x) || 0),
  str: (x) => String(x == null ? '' : x),
  min: (a, b) => Math.min(a, b),
  max: (a, b) => Math.max(a, b),
  slice: (a, s, e) => (a || []).slice(s, e),
  sum: (a) => (a || []).reduce((x, y) => x + (Number(y) || 0), 0),
};

function evalExpr(e, st, env) {
  switch (e.k) {
    case 'num': return e.v;
    case 'str': return e.v;
    case 'bool': return e.v;
    case 'id':
      if (e.v in env) return env[e.v];
      if (e.v in BUILTINS) return BUILTINS[e.v];
      if (st && e.v in st) return st[e.v];
      return undefined;
    case 'list': return e.items.map(x => evalExpr(x, st, env));
    case 'obj': {
      const o = {};
      for (const [k, v] of e.props) o[k] = evalExpr(v, st, env);
      return o;
    }
    case 'member': {
      const o = evalExpr(e.o, st, env);
      return o == null ? undefined : o[e.f];
    }
    case 'un': {
      const v = evalExpr(e.e, st, env);
      return e.op === '!' ? !v : -v;
    }
    case 'bin': {
      const a = evalExpr(e.l, st, env);
      if (e.op === '&&') return a && evalExpr(e.r, st, env);
      if (e.op === '||') return a || evalExpr(e.r, st, env);
      const b = evalExpr(e.r, st, env);
      switch (e.op) {
        case '+': return (typeof a === 'string' || typeof b === 'string') ? String(a) + String(b) : a + b;
        case '-': return a - b;
        case '*': return a * b;
        case '/': return b === 0 ? 0 : a / b;
        case '==': return a === b;
        case '!=': return a !== b;
        case '<': return a < b;
        case '>': return a > b;
        case '<=': return a <= b;
        case '>=': return a >= b;
      }
      return undefined;
    }
    case 'call': {
      const f = evalExpr(e.callee, st, env);
      if (typeof f !== 'function') return undefined;
      return f.apply(null, e.args.map(x => evalExpr(x, st, env)));
    }
  }
  return undefined;
}

/* 执行一个 handler。返回 { ok, result, emits, state } */
function runHandler(svc, op, args, state) {
  const h = svc.handlers.find(x => x.op === op);
  if (!h) return { ok: false, error: `服务 ${svc.name} 没有 on "${op}"` };

  const st = JSON.parse(JSON.stringify(state || makeState(svc)));
  const env = {};
  h.params.forEach((pn, i) => { env[pn] = args[i]; });

  const emits = [];
  let result = null;
  let returned = false;

  const exec = (stmts) => {
    for (const s of stmts) {
      if (returned) return;
      switch (s.k) {
        case 'let': env[s.name] = evalExpr(s.e, st, env); break;
        case 'set': st[s.name] = evalExpr(s.e, st, env); break;
        case 'append': {
          if (!Array.isArray(st[s.target])) st[s.target] = [];
          st[s.target].push(evalExpr(s.e, st, env));
          break;
        }
        case 'return': result = s.e ? evalExpr(s.e, st, env) : null; returned = true; break;
        case 'emit': {
          const payload = {};
          if (s.payload) for (const [k, v] of s.payload) payload[k] = evalExpr(v, st, env);
          emits.push({ op: s.op, payload, after: s.after ? evalExpr(s.after, st, env) : 0 });
          break;
        }
        case 'if': {
          if (evalExpr(s.cond, st, env)) exec(s.then);
          else if (s.els) exec(s.els);
          break;
        }
        case 'expr': evalExpr(s.e, st, env); break;
      }
    }
  };

  exec(h.body);
  return { ok: true, result, emits, state: st };
}

/* ============================ 5. 状态体积 ============================ */
function stateSize(state) {
  const raw = Buffer.from(JSON.stringify(state), 'utf8');
  return { raw: raw.length, json: JSON.stringify(state) };
}

/* ============================ 6. 对外 ============================ */
function compile(src) {
  const ast = parse(lex(src));
  const diag = check(ast);
  return { ast, diag };
}

module.exports = { lex, parse, check, compile, makeState, runHandler, stateSize, BUILTINS };
