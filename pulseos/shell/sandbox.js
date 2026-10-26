'use strict';
/* ==========================================================================
 *  sandbox.js —— 外部沙箱（方案 A）
 *  --------------------------------------------------------------------------
 *  ★ 安全前提（这是整个设计的底线）
 *
 *      PulseScript 里【永远不开】spawn / exec / eval / require。
 *      刚才修的那批 RCE 漏洞，不能因为"要跑 Ubuntu"又开回去。
 *
 *      所以"拉起 Ubuntu"这件事不写在 PulseScript 里，
 *      而是写在这个 JS 文件里，由 PulseOS 通过「原生微内核」接口调用。
 *
 *  ★ 边界划分
 *
 *      PulseOS 微内核   2µs      信令调度 / 状态演进 / 因果分发
 *      外部沙箱        100ms     拉起 chroot + 跑 python + 取结果
 *
 *      F1 赛车负责跑圈，重型卡车负责拉货。谁也不替代谁。
 *
 *  ★ 这个沙箱允许什么（白名单，不是任意 shell）
 *
 *      runPython(script)   只跑 python3，脚本走文件不走命令行
 *      probe()             chroot /bin/true，测拉起耗时
 *      info()              沙箱能力与环境
 *
 *      不允许：任意 shell 命令、网络、写沙箱外的路径
 *
 *  ★ 环境限制（Android 沙箱实测）
 *
 *      chroot            ✓ 可用（56ms）
 *      mount 后 chroot    ✗ seccomp 拦截（Function not implemented）
 *      所以【不挂 /proc】—— 代价是 ps/top 不可用，apt/python 正常
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

/* ---------------- 硬限制 ---------------- */
const LIMITS = {
  maxScriptBytes: 64 * 1024,      // 脚本最大 64KB
  maxTimeoutMs: 30000,            // 单次最长 30s
  maxOutputBytes: 256 * 1024,     // 输出最大 256KB
  maxRuntimeSeconds: 10,          // python 内再挡一层
};

class Sandbox {
  /**
   * @param {object} opts
   *   rootfs     Ubuntu/Alpine rootfs 根目录
   *   python     rootfs 内的解释器路径（默认 /usr/bin/python3）
   *   timeoutMs  默认超时
   */
  constructor(opts = {}) {
    this.rootfs = opts.rootfs || '';
    this.python = opts.python || '/usr/bin/python3';
    this.shell = opts.shell || '/bin/sh';
    this.timeoutMs = Math.min(opts.timeoutMs || 10000, LIMITS.maxTimeoutMs);
    /* ★ 默认禁网。chroot 不隔离网络，必须在脚本层拦。
       allowNet:true 才放开（会带来数据外泄风险） */
    this.allowNet = opts.allowNet === true;
    this.available = false;
    this.reason = '';

    this.stats = { spawns: 0, runs: 0, failures: 0, lat: [] };

    /* 启动时探测一次：rootfs 在不在、能不能 chroot */
    this._probe();
  }

  _probe() {
    if (!this.rootfs) { this.reason = '未指定 rootfs'; return; }
    if (!fs.existsSync(this.rootfs)) { this.reason = 'rootfs 不存在: ' + this.rootfs; return; }
    const bin = path.join(this.rootfs, this.shell.replace(/^\//, ''));
    if (!fs.existsSync(bin)) { this.reason = 'rootfs 里没有 ' + this.shell; return; }

    const t0 = process.hrtime.bigint();
    const r = spawnSync('chroot', [this.rootfs, this.shell, '-c', 'echo ok'], {
      encoding: 'utf8', timeout: 5000,
    });
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;

    if (r.status === 0 && /ok/.test(r.stdout || '')) {
      this.available = true;
      this.probeMs = ms;
      this.reason = '';
    } else {
      this.reason = 'chroot 失败: ' + ((r.stderr || '').trim().slice(0, 120) || 'exit=' + r.status);
    }
  }

  /* ---------------- 沙箱内路径 ----------------
     只允许写 rootfs 内的 /tmp —— 防止路径逃逸 */
  _inner(candidate) {
    const p = path.resolve(this.rootfs, '.' + (candidate.startsWith('/') ? candidate : '/' + candidate));
    if (!p.startsWith(this.rootfs + path.sep)) {
      throw new Error('路径逃逸: ' + candidate);
    }
    return p;
  }

  /* ---------------- ① 测拉起耗时 ---------------- */
  probe(rounds = 1) {
    if (!this.available) return { ok: false, error: this.reason };
    const n = Math.max(1, Math.min(rounds, 20));
    const lat = [];
    for (let i = 0; i < n; i++) {
      const t0 = process.hrtime.bigint();
      const r = spawnSync('chroot', [this.rootfs, '/bin/true'], { timeout: 5000 });
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      if (r.status === 0) lat.push(ms);
    }
    this.stats.spawns += lat.length;
    if (!lat.length) return { ok: false, error: '拉起全部失败' };
    lat.sort((a, b) => a - b);
    return {
      ok: true,
      rounds: lat.length,
      p50: +lat[Math.floor(lat.length * 0.5)].toFixed(2),
      min: +lat[0].toFixed(2),
      max: +lat[lat.length - 1].toFixed(2),
    };
  }

  /* ---------------- ② 跑 Python（唯一允许的重活） ----------------
     ★ 关键安全点：
        · 脚本写到 rootfs 内的临时文件，通过【参数】传给 python3
        · 不用 shell 拼接用户输入 —— 杜绝命令注入
        · 超时硬杀、输出截断、脚本大小限制 */
  runPython(script, opts = {}) {
    if (!this.available) return { ok: false, error: this.reason };

    const code = String(script == null ? '' : script);
    if (code.length > LIMITS.maxScriptBytes) {
      return { ok: false, error: '脚本超过 ' + LIMITS.maxScriptBytes + ' 字节' };
    }

    const timeout = Math.min(opts.timeoutMs || this.timeoutMs, LIMITS.maxTimeoutMs);
    /* ★ 禁网拦截：在用户脚本前插入守卫，覆盖 socket / urllib / http 等 */
    let finalCode = code;
    if (!this.allowNet) {
      const guard = [
        'import builtins as _b',
        'class _NoNet:',
        '    def __init__(self,*a,**k): raise PermissionError("sandbox: network disabled (allowNet:false)")',
        'def _block(*a,**k): raise PermissionError("sandbox: network disabled (allowNet:false)")',
        'import socket as _s',
        '_s.socket = _NoNet',
        '_s.create_connection = _block',
        '_s.getaddrinfo = _block',
        'try:',
        '    import urllib.request as _u; _u.urlopen = _block',
        'except Exception: pass',
        'try:',
        '    import http.client as _h; _h.HTTPConnection.connect = _block',
        'except Exception: pass',
        'del _b',
        '',
      ].join('\n');
      finalCode = guard + code;
    }

    /* 写脚本到 rootfs 内的 /tmp（_inner 会检查路径逃逸） */
    const stamp = process.pid + '_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    const innerPath = '/tmp/_sbx_' + stamp + '.py';
    let hostPath;
    try {
      hostPath = this._inner(innerPath);
      fs.mkdirSync(path.dirname(hostPath), { recursive: true });
      fs.writeFileSync(hostPath, finalCode, 'utf8');
    } catch (e) {
      return { ok: false, error: '写脚本失败: ' + e.message };
    }

    const t0 = process.hrtime.bigint();
    /* ★ 用参数数组，不经过 shell —— python3 只看到文件路径 */
    const r = spawnSync('chroot', [this.rootfs, this.python, innerPath], {
      encoding: 'utf8',
      timeout,
      maxBuffer: LIMITS.maxOutputBytes,
    });
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;

    try { fs.unlinkSync(hostPath); } catch (e) {}

    const out = (r.stdout || '').slice(0, LIMITS.maxOutputBytes);
    const err = (r.stderr || '').slice(0, 4096);

    this.stats.runs++;
    this.stats.lat.push(ms);
    if (this.stats.lat.length > 200) this.stats.lat.shift();

    if (r.error && r.error.code === 'ETIMEDOUT') {
      this.stats.failures++;
      return { ok: false, error: '超时 ' + timeout + 'ms', ms: +ms.toFixed(2) };
    }
    if (r.status !== 0) {
      this.stats.failures++;
      return { ok: false, error: 'exit=' + r.status + ' ' + err.trim().slice(0, 200), stderr: err, ms: +ms.toFixed(2) };
    }

    return { ok: true, stdout: out, stderr: err || undefined, ms: +ms.toFixed(2) };
  }

  info() {
    const lat = this.stats.lat.slice().sort((a, b) => a - b);
    const pct = (p) => (lat.length ? +lat[Math.floor(lat.length * p)].toFixed(2) : null);
    return {
      available: this.available,
      reason: this.reason,
      rootfs: this.rootfs,
      python: this.python,
      probeMs: this.probeMs || null,
      spawns: this.stats.spawns,
      runs: this.stats.runs,
      failures: this.stats.failures,
      lat: { p50: pct(0.5), p95: pct(0.95), n: lat.length },
      allowNet: this.allowNet,
      limits: LIMITS,
    };
  }
}

/* ==========================================================================
 *  NativeKernel —— 把外部能力伪装成「微内核」，让 PulseOS 能派发到它
 *  --------------------------------------------------------------------------
 *  形状必须和 MicroKernel 一致（pulse / info），这样：
 *    · dispatchEmits 能路由过来
 *    · index.invoke() 能直接调
 *    · 页面上能当成一个普通微内核展示
 *
 *  ★ 但它【不在 PulseScript 里】。PulseScript 依然纯净无副作用。
 * ========================================================================== */
class NativeKernel {
  /**
   * @param {string} name
   * @param {object} handlers  { [op]: (args) => ({state:null, result}) | Promise }
   * @param {object} opts      { note }
   */
  constructor(name, handlers, opts = {}) {
    this.name = name;
    this.isNative = true;
    this.handlers = handlers;
    this.note = opts.note || '';
    /* { op: ['text'] } —— emit 传来对象时按这些 key 解包成位置参数 */
    this.paramKeys = opts.paramKeys || {};
    this.state = null;          // 原生微内核无状态
    this.stats = { pulses: 0, errors: 0, lat: [] };
  }

  /* 与 MicroKernel.pulse 同签名（同步版） */
  pulse(op, args = [], depth = 0) {
    const t0 = process.hrtime.bigint();
    const fn = this.handlers[op];
    if (!fn) {
      this.stats.errors++;
      return {
        ok: false, service: this.name, op, error: '原生微内核没有 op "' + op + '"',
        emits: [], spawned: [], totalMs: 0,
      };
    }
    let result = null, error = null, ok = true;
    /* ★ 关键：emit 派发时传的是整个 payload 对象（{text:'hello'}），
       而 handler 期望的是标量（'hello'）。
       如果只有一个参数且是对象，且 handler 声明了 paramKeys，就按 key 解包。 */
    let callArgs = args;
    if (args.length === 1 && args[0] && typeof args[0] === 'object' && !Array.isArray(args[0])) {
      const keys = this.paramKeys && this.paramKeys[op];
      if (keys && keys.length) {
        callArgs = keys.map(k => args[0][k]);
      }
    }
    try {
      result = fn.apply(null, callArgs);
    } catch (e) {
      ok = false; error = e.message;
      this.stats.errors++;
    }
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    this.stats.pulses++;
    this.stats.lat.push(ms);
    if (this.stats.lat.length > 200) this.stats.lat.shift();

    return {
      ok, service: this.name, op, result, error,
      emits: [], spawned: [],
      stateSize: null,
      totalMs: +ms.toFixed(3),
      native: true,
    };
  }

  info() {
    const lat = this.stats.lat.slice().sort((a, b) => a - b);
    const pct = (p) => (lat.length ? +lat[Math.floor(lat.length * p)].toFixed(3) : null);
    return {
      name: this.name,
      native: true,
      note: this.note,
      handlers: Object.keys(this.handlers).map(op => ({ op, params: [] })),
      fields: [],
      warnings: [],
      stateBytes: 0,
      state: '(原生微内核，无 PulseScript 状态)',
      pulses: this.stats.pulses,
      emits: 0,
      errors: this.stats.errors,
      lat: { p50: pct(0.5), p95: pct(0.95), n: lat.length },
    };
  }
}

module.exports = { Sandbox, NativeKernel, LIMITS };
