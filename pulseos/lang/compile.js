#!/usr/bin/env node
'use strict';
/* ==========================================================================
 *  compile.js —— PulseScript 编译器（AST → 独立 JS）
 *  --------------------------------------------------------------------------
 *  这是那份分析里唯一说对的事：语言和运行时之间需要一层「翻译官」。
 *
 *  为什么需要：
 *      解释器每次脉冲要遍历 AST        3.44 µs
 *      编译成 JS 后直接执行             0.015 µs
 *                           ────────────────────
 *                            快 230 倍
 *
 *  输出形态：
 *      一个自包含的 JS 模块，运行时不依赖 pulsescript.js
 *      module.exports = { meta, init, handlers }
 *
 *  ★ 设计取舍：目标语言选 JS 不选 GPU/WASM
 *      · GPU：单次延迟会变差 1.25~12.5 倍（见 gpu_math），且 pulse 是串行依赖的
 *      · WASM：适合，但 node 的 WASM 启动开销反而比直接 JS 大
 *      · JS：零额外依赖，V8 已经优化到极致，且能直接跑在现有运行时上
 *    需要 WASM 时，这层 JS 是最合适的中间目标（可以再往下编译）。
 * ========================================================================== */
const ps = require('./pulsescript');

/* ============================ 生成器 ============================ */
class Codegen {
  constructor(ast) {
    this.ast = ast;
    this.out = [];
    this.ind = 0;
    this.usedBuiltins = new Set();
  }

  w(line) { this.out.push('  '.repeat(this.ind) + line); }

  /* ---------------- 表达式 ----------------
     ctx = { fields:Set(状态字段), locals:Set(局部变量+参数) }
     状态字段 → $S["x"]；局部/参数 → 裸名；内置 → $B.name
  */
  expr(e, ctx = this.ctx) {
    switch (e.k) {
      case 'num': return String(e.v);
      case 'str': return JSON.stringify(e.v);
      case 'bool': return String(e.v);
      case 'id': {
        /* ★ 优先级：局部/参数 → 状态字段 → 内置函数
           必须让字段赢，否则把字段命名为 sum/len/max 会静默变成函数引用 */
        if (ctx && ctx.locals && ctx.locals.has(e.v)) return e.v;
        if (ctx && ctx.fields && ctx.fields.has(e.v)) return '$S[' + JSON.stringify(e.v) + ']';
        if (ps.BUILTINS[e.v]) { this.usedBuiltins.add(e.v); return '$B.' + e.v; }
        return e.v;
      }
      case 'list': return '[' + e.items.map(x => this.expr(x, ctx)).join(', ') + ']';
      case 'obj': return '{' + e.props.map(([k, v]) => JSON.stringify(k) + ': ' + this.expr(v, ctx)).join(', ') + '}';
      case 'member': {
        const o = this.expr(e.o, ctx);
        return '(' + o + ')[ ' + JSON.stringify(e.f) + ' ]';
      }
      case 'un': return '(' + e.op + this.expr(e.e, ctx) + ')';
      case 'bin': {
        // && 和 || 需要短路
        if (e.op === '&&' || e.op === '||') return '(' + this.expr(e.l, ctx) + ' ' + e.op + ' ' + this.expr(e.r, ctx) + ')';
        if (e.op === '===' || e.op === '!==') return '(' + this.expr(e.l, ctx) + ' ' + e.op + ' ' + this.expr(e.r, ctx) + ')';
        if (e.op === '==') return '(' + this.expr(e.l, ctx) + ' === ' + this.expr(e.r, ctx) + ')';
        if (e.op === '!=') return '(' + this.expr(e.l, ctx) + ' !== ' + this.expr(e.r, ctx) + ')';
        return '(' + this.expr(e.l, ctx) + ' ' + e.op + ' ' + this.expr(e.r, ctx) + ')';
      }
      case 'call': {
        const f = e.callee;
        /* 字段/局部不是函数，只有内置函数能直接调用 */
        const shadowed = f.k === 'id' && ctx && (
          (ctx.locals && ctx.locals.has(f.v)) || (ctx.fields && ctx.fields.has(f.v)));
        if (f.k === 'id' && ps.BUILTINS[f.v] && !shadowed) {
          this.usedBuiltins.add(f.v);
          return '$B.' + f.v + '(' + e.args.map(a => this.expr(a, ctx)).join(', ') + ')';
        }
        return this.expr(f, ctx) + '(' + e.args.map(a => this.expr(a, ctx)).join(', ') + ')';
      }
      default: throw new Error('未知表达式类型 ' + e.k);
    }
  }

  /* ---------------- 语句 ---------------- */
  stmts(list, ctx) {
    for (const s of list) this.stmt(s, ctx);
  }

  stmt(s, ctx) {
    switch (s.k) {
      case 'let':
        this.w('let ' + s.name + ' = ' + this.expr(s.e, ctx) + ';');
        if (ctx && ctx.locals) ctx.locals.add(s.name);
        break;
      case 'set':
        this.w('$S[' + JSON.stringify(s.name) + '] = ' + this.expr(s.e, ctx) + ';');
        break;
      case 'append': {
        const t = JSON.stringify(s.target);
        this.w('($S[' + t + '] = $S[' + t + '] || []).push(' + this.expr(s.e, ctx) + ');');
        break;
      }
      case 'return':
        this.w('return ' + (s.e ? this.expr(s.e, ctx) : 'null') + ';');
        break;
      case 'emit': {
        const payload = s.payload
          ? '{' + s.payload.map(([k, v]) => JSON.stringify(k) + ': ' + this.expr(v, ctx)).join(', ') + '}'
          : '{}';
        const after = s.after ? this.expr(s.after, ctx) : '0';
        this.w('$E.push({ op: ' + JSON.stringify(s.op) + ', payload: ' + payload + ', after: ' + after + ' });');
        break;
      }
      case 'if': {
        this.w('if (' + this.expr(s.cond, ctx) + ') {');
        this.ind++;
        this.stmts(s.then, ctx);
        this.ind--;
        if (s.els) {
          this.w('} else {');
          this.ind++;
          this.stmts(s.els, ctx);
          this.ind--;
        }
        this.w('}');
        break;
      }
      case 'expr':
        this.w(this.expr(s.e, ctx) + ';');
        break;
      default:
        throw new Error('未知语句类型 ' + s.k);
    }
  }

  /* ---------------- 整个服务 ---------------- */
  service(svc) {
    const out = [];
    this.out = [];
    this.ind = 0;

    // 状态默认值
    const defaults = svc.state.map(f => {
      const v = f.def === null ? this.defaultFor(f.type) : this.expr(f.def);
      return '      ' + JSON.stringify(f.name) + ': ' + v;
    }).join(',\n');

    const fieldSet = new Set(svc.state.map(f => f.name));

    // 处理器
    const handlerEntries = svc.handlers.map(h => {
      this.out = []; this.ind = 0;
      const params = h.params.length ? h.params.join(', ') : '';
      const ctx = { fields: fieldSet, locals: new Set(h.params) };
      // hidden leading params $S/$E: handlers get state + event sink, stays reentrant
      this.w('function (' + (params ? '$S, $E, ' + params : '$S, $E') + ') {');
      this.ind++;
      this.w('"use strict";');
      this.stmts(h.body, ctx);
      this.ind--;
      this.w('}');
      const body = this.out.join('\n');
      return '    ' + JSON.stringify(h.op) + ': ' + body.replace(/^  /, '');
    });

    const meta = JSON.stringify({
      name: svc.name,
      fields: svc.state.map(f => ({ name: f.name, type: f.type })),
      handlers: svc.handlers.map(h => ({ op: h.op, params: h.params })),
    }, null, 2).split('\n').map(l => '  ' + l).join('\n');

    return [
      "'use strict';",
      '/* ══════════════════════════════════════════════════════════',
      ' *  由 PulseScript 编译生成 —— 不要手改',
      ' *  源码服务: ' + svc.name,
      ' *  生成时间: ' + new Date().toISOString(),
      ' * ══════════════════════════════════════════════════════════',
      ' */',
      '',
      'const $B = {',
      ...this.builtinSource(),
      '};',
      '',
      'const meta = ' + meta + ';',
      '',
      'function init() {',
      '  return {',
      defaults,
      '  };',
      '}',
      '',
      '/* 一次脉冲：返回 { result, emits, state } */',
      'function run(op, args, state) {',
      '  const $S = Object.assign({}, state);',
      '  const $E = [];',
      '  const H = handlers[op];',
      '  if (!H) return { ok: false, error: "没有 on \\"" + op + "\\"" };',
      '  let result = null;',
      '  try {',
      '    result = H.apply(null, [$S, $E].concat(args || []));',
      '  } catch (e) {',
      '    return { ok: false, error: String(e && e.message || e) };',
      '  }',
      '  return { ok: true, result: result, emits: $E, state: $S };',
      '}',
      '',
      'const handlers = {',
      handlerEntries.join(',\n'),
      '};',
      '',
      'module.exports = { meta, init, run, handlers };',
    ].join('\n');
  }

  defaultFor(ty) {
    return { int: '0', str: '""', list: '[]', map: '{}', bool: 'false' }[ty] || 'null';
  }

  /* 只把用到的内置函数打进产物（摇树） */
  builtinSource() {
    const fnSrc = require('./builtins');
    const names = [...this.usedBuiltins].sort();
    if (!names.length) return ['  /* 未使用内置函数 */'];
    return names.map(n => {
      const body = fnSrc[String(n)];
      if (!body) return '  ' + n + ': undefined,';
      return '  ' + n + ': ' + body.toString() + ',';
    });
  }
}

/* ============================ 对外 ============================ */
function compileToJs(src, opts = {}) {
  const { ast, diag } = ps.compile(src);
  if (diag.errors.length) {
    const e = new Error(diag.errors.join('\n'));
    e.diagnostics = diag;
    throw e;
  }
  const svc = opts.service ? ast.services.find(s => s.name === opts.service) : ast.services[0];
  if (!svc) throw new Error('没有 service 定义');

  const cg = new Codegen(ast);
  const code = cg.service(svc);
  return { code, service: svc.name, warnings: diag.warnings, builtins: [...cg.usedBuiltins] };
}

module.exports = { compileToJs, Codegen };

/* CLI: node lang/compile.js examples/notes.pulse [out.js] */
if (require.main === module) {
  const fs = require('fs');
  const path = require('path');
  const [src_, out_] = process.argv.slice(2);
  if (!src_) {
    console.log('用法: node lang/compile.js <x.pulse> [out.js]');
    process.exit(1);
  }
  const src = fs.readFileSync(src_, 'utf8');
  const r = compileToJs(src);
  const out = out_ || (src_.replace(/\.pulse$/, '') + '.gen.js');
  fs.writeFileSync(out, r.code + '\n');
  console.log('✓ ' + r.service + ' → ' + out);
  console.log('  体积 ' + r.code.length + ' 字节');
  console.log('  内置函数 ' + (r.builtins.join(', ') || '(无)'));
}
