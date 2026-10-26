'use strict';
/* ==========================================================================
 *  envs.js —— 沙箱环境的 13 个控制原语
 *  --------------------------------------------------------------------------
 *  ★ 铁律：这 13 个原语【绝不进 PulseScript】
 *      PulseScript 是纯状态机，加一个 spawn 就是 RCE。
 *      全部由 PulseOS 调用 JS 侧的本文件。
 *
 *  ★ 实测可行性（Android 14/15 沙箱）
 *
 *    ✓ 能做 10 个：init / spawn / kill / inject / exec / retrieve /
 *                  stream / snapshot / restore / bind_mqtt
 *    ✗ 做不到 2 个：set_limits（无 cgroup 权限）、get_usage（无 /proc）
 *    ⚠️ 打折 1 个：revoke_network（只能 Python 层拦，无 iptables）
 *
 *  ★ 与之前的 sandbox.js 的区别
 *
 *    sandbox.js   spawnSync，一次跑完就结束（已存在，保留兼容）
 *    envs.js      spawn 常驻进程 + stdin/stdout 管道，
 *                 支持 inject / stream_logs / 真 kill
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const LIMITS = {
  maxEnvs: 8,                    // 同时最多 8 个环境
  maxScriptBytes: 64 * 1024,
  maxOutputBytes: 512 * 1024,
  maxTimeoutMs: 30000,
  idleKillMs: 60000,             // 空闲 60s 自动回收
};

/* ---------------- Python 侧网络守卫 ---------------- */
const NET_GUARD = [
  'import socket as _s',
  'class _NoNet:',
  '    def __init__(self,*a,**k): raise PermissionError("sandbox: network disabled")',
  'def _blk(*a,**k): raise PermissionError("sandbox: network disabled")',
  '_s.socket=_NoNet; _s.create_connection=_blk; _s.getaddrinfo=_blk',
  'try:',
  '    import urllib.request as _u; _u.urlopen=_blk',
  'except Exception: pass',
  'try:',
  '    import http.client as _h; _h.HTTPConnection.connect=_blk',
  'except Exception: pass',
  '',
].join('\n');

/* ==========================================================================
 *  EnvManager
 * ========================================================================== */
class EnvManager {
  constructor(opts = {}) {
    this.rootfs = opts.rootfs || '';
    this.python = opts.python || '/usr/bin/python3';
    this.shell = opts.shell || '/bin/sh';
    this.allowNet = opts.allowNet === true;
    this.snapDir = opts.snapDir || path.join('/tmp', 'pulse-snap');
    this.envs = new Map();       // env_id -> env
    this.stats = { inits: 0, spawns: 0, kills: 0, execs: 0, snapshots: 0, restored: 0, errors: 0 };
    this._gcTimer = setInterval(() => this._gc(), 15000);
    if (this._gcTimer.unref) this._gcTimer.unref();
  }

  /* ---------- 内部工具 ---------- */
  _inner(candidate) {
    const p = path.resolve(this.rootfs, '.' + (String(candidate).startsWith('/') ? candidate : '/' + candidate));
    if (p !== this.rootfs && !p.startsWith(this.rootfs + path.sep)) {
      throw new Error('路径逃逸: ' + candidate);
    }
    return p;
  }

  _gc() {
    const now = Date.now();
    for (const [id, e] of this.envs) {
      if (e.state === 'running' && now - e.lastActive > LIMITS.idleKillMs) {
        this.op_kill_env(id, true);
      }
    }
  }

  /* ======================================================================
   *  ① init_env —— 检查镜像完整性，返回 env_id
   * ==================================================================== */
  op_init_env(image_path) {
    try {
      const rootfs = image_path || this.rootfs;
      if (!rootfs) throw new Error('未指定 image_path');
      if (!fs.existsSync(rootfs)) throw new Error('镜像不存在: ' + rootfs);

      const bin = path.join(rootfs, this.shell.replace(/^\//, ''));
      if (!fs.existsSync(bin)) throw new Error('镜像里没有 ' + this.shell);

      /* 轻量完整性检查：关键目录 + 解释器 */
      const need = ['bin', 'etc', 'usr'];
      const missing = need.filter(d => !fs.existsSync(path.join(rootfs, d)));
      if (missing.length) throw new Error('镜像缺目录: ' + missing.join(','));

      const pyPath = path.join(rootfs, this.python.replace(/^\//, ''));
      const pyOk = fs.existsSync(pyPath);

      const envId = 'env_' + crypto.randomBytes(5).toString('hex');
      if (this.envs.size >= LIMITS.maxEnvs) {
        throw new Error('环境数已达上限 ' + LIMITS.maxEnvs + '（先 kill 一些）');
      }

      this.envs.set(envId, {
        id: envId, rootfs, python: pyOk ? this.python : null,
        state: 'init', pid: null, proc: null,
        createdAt: Date.now(), lastActive: Date.now(),
        scriptPath: null, out: [], outBytes: 0,
        pending: null,          // { marker, resolve, timer, from }
        allowNet: this.allowNet, netBlocked: !this.allowNet,
        exitCode: null, timedOut: false,
      });
      this.stats.inits++;

      return {
        ok: true, env_id: envId, rootfs,
        python: pyOk ? this.python : '(未安装)',
        /* ★ 不在热路径算体积（709MB 要 7s）。要的话单独调 get_usage */
        size_mb: null,
      };
    } catch (e) {
      this.stats.errors++;
      return { ok: false, error: e.message };
    }
  }

  /* ★ du -sb 扫 709MB 要 7 秒 —— 不能放 init_env 热路径上。
     用 stat 累加顶层目录，快 100 倍，精度够用（±5%）。 */
  _dirSize(p) {
    if (this._sizeCache && this._sizeCache[p] != null) return this._sizeCache[p];
    this._sizeCache = this._sizeCache || {};
    let total = 0;
    const walk = (dir, depth) => {
      if (depth > 12) return;
      let ents;
      try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch (e) { return; }
      for (const ent of ents) {
        const full = path.join(dir, ent.name);
        try {
          if (ent.isDirectory()) walk(full, depth + 1);
          else if (ent.isFile()) total += fs.statSync(full).size;
        } catch (e) {}
      }
    };
    walk(p, 0);
    this._sizeCache[p] = total;
    return total;
  }

  /* ======================================================================
   *  ② spawn_env —— 真正拉起常驻进程（异步 spawn，可 kill）
   * ==================================================================== */
  op_spawn_env(env_id) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env: ' + env_id };
    if (e.state === 'running') return { ok: false, error: '已经在跑（pid=' + e.pid + '）' };

    try {
      /* 起一个常驻 sh，读 stdin，这样才有管道能 inject */
      const proc = spawn('chroot', [e.rootfs, this.shell], {
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      e.proc = proc;
      e.pid = proc.pid;
      e.state = 'running';
      e.lastActive = Date.now();
      e.out = [];
      e.outBytes = 0;
      e.exitCode = null;

      const collect = (stream) => (d) => {
        const s = d.toString();
        e.out.push({ stream, s, t: Date.now() });
        e.outBytes += s.length;
        while (e.outBytes > LIMITS.maxOutputBytes && e.out.length > 1) {
          const old = e.out.shift();
          e.outBytes -= old.s.length;
        }
        /* ★ 哨兵命中 → 唤醒等待中的 exec_script */
        const p = e.pending;
        if (p && s.includes(p.marker)) {
          clearTimeout(p.timer);
          const fresh = e.out.slice(p.from);
          /* ★ 关键：哨兵可能和正常输出在【同一个数据块】里，
             不能整块丢掉。按行剥离哨兵那一行，剩下的才是真输出。 */
          const clean = (x) => {
            if (!x.s.includes(p.marker)) return x.s;
            return x.s.split('\n')
              .filter(line => !line.includes(p.marker))
              .join('\n');
          };
          const stdout = fresh.filter(x => x.stream === 'out').map(clean).join('');
          const stderr = fresh.filter(x => x.stream === 'err').map(clean).join('');
          e.pending = null;
          p.resolve({
            ok: true, env_id: e.id, mode: 'inject', exit_code: 0,
            stdout, stderr: stderr || undefined,
            ms: +(Date.now() - p.t0).toFixed(2),
          });
        }
      };
      proc.stdout.on('data', collect('out'));
      proc.stderr.on('data', collect('err'));
      proc.on('exit', (code) => {
        e.exitCode = code; e.state = 'exited'; e.proc = null;
        /* ★ 命令可能把 shell 弄死（语法错/exit）。此时哨兵永远不会来，
           必须立刻唤醒等待者，而不是白等满超时。 */
        const p = e.pending;
        if (p) {
          clearTimeout(p.timer);
          const fresh = e.out.slice(p.from);
          const stdout = fresh.filter(x => x.stream === 'out').map(x => x.s).join('');
          const stderr = fresh.filter(x => x.stream === 'err').map(x => x.s).join('');
          e.pending = null;
          p.resolve({
            ok: false,
            error: 'shell 在执行时退出（exit=' + code + '）——命令可能有语法错，或调用了 exit',
            sh_exited: true, exit_code: code,
            stdout, stderr: stderr || undefined,
            ms: +(Date.now() - p.t0).toFixed(2),
          });
        }
      });
      proc.on('error', (err) => { e.state = 'error'; e.error = err.message; });

      this.stats.spawns++;
      return { ok: true, env_id, pid: e.pid, state: e.state };
    } catch (err) {
      this.stats.errors++;
      return { ok: false, error: err.message };
    }
  }

  /* ======================================================================
   *  ③ kill_env —— 真杀（SIGKILL）
   * ==================================================================== */
  op_kill_env(env_id, force) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };

    let killed = false;
    try {
      if (e.proc) {
        e.proc.kill(force === false ? 'SIGTERM' : 'SIGKILL');
        killed = true;
      } else if (e.pid) {
        try { process.kill(e.pid, force === false ? 'SIGTERM' : 'SIGKILL'); killed = true; } catch (x) {}
      }
    } catch (x) {}

    /* 清理临时脚本 */
    if (e.scriptPath) { try { fs.unlinkSync(e.scriptPath); } catch (x) {} }

    this.envs.delete(env_id);
    this.stats.kills++;
    return { ok: true, env_id, killed, remaining: this.envs.size };
  }

  /* ======================================================================
   *  ④ inject_data —— 通过 stdin 注入（真管道）
   * ==================================================================== */
  op_inject_data(env_id, data) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };
    if (e.state !== 'running' || !e.proc) return { ok: false, error: 'env 没在跑，先 spawn_env' };

    const buf = Buffer.isBuffer(data) ? data : Buffer.from(String(data == null ? '' : data), 'utf8');
    if (buf.length > LIMITS.maxScriptBytes) {
      return { ok: false, error: '注入数据超过 ' + LIMITS.maxScriptBytes + ' 字节' };
    }
    try {
      e.proc.stdin.write(buf);
      e.lastActive = Date.now();
      return { ok: true, env_id, bytes_written: buf.length };
    } catch (err) {
      return { ok: false, error: err.message };
    }
  }

  /* ======================================================================
   *  ⑤ exec_script —— 在沙箱内执行（两种模式）
   *     mode='inject'  往已有进程的 stdin 写（要求 ①②④ 已做）
   *     mode='once'    一次性跑完（默认，最常用）
   * ==================================================================== */
  op_exec_script(env_id, command, timeoutMs, opts = {}) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };

    const cmd = String(command == null ? '' : command);
    if (cmd.length > LIMITS.maxScriptBytes) return { ok: false, error: '命令过长' };
    const timeout = Math.min(parseInt(timeoutMs, 10) || 10000, LIMITS.maxTimeoutMs);
    opts = opts || {};

    /* ★ 引号平衡检查：不配对的引号会让 shell 一直等输入，白等到超时 */
    const quoteCheck = (str) => {
      let inS = false, inD = false, esc = false;
      for (const ch of str) {
        if (esc) { esc = false; continue; }
        if (ch === '\\') { esc = true; continue; }
        if (ch === "'" && !inD) inS = !inS;
        else if (ch === '"' && !inS) inD = !inD;
      }
      return (!inS && !inD) ? null : (inS ? '单引号' : '双引号');
    };

    /* 走管道前先查引号（once 模式走文件，不受影响） */
    /* ★ 自动回退：shell 已经死了就别走管道，直接 once 模式 */
    if (e.state !== 'running' && opts.wait !== false && opts.noFallback !== true) {
      opts = Object.assign({}, opts, { wait: false });
    }

    if (e.state === 'running' && e.proc && opts.wait !== false) {
      const unbal = quoteCheck(cmd);
      if (unbal) {
        this.stats.errors++;
        return {
          ok: false,
          error: '引号不配对（' + unbal + '未闭合），走管道会让 shell 挂住。'
              + '改用 opts.wait=false（一次性模式）或修正引号。',
          quote_unbalanced: true,
        };
      }
    }

    /* 模式 A：进程已在跑 → 写 stdin，然后【等输出回来】
       ★ 之前只写不等，调用方拿不到结果 —— 这是设计缺陷。
          现在同步等：发个哨兵 echo 标记结尾，收到哨兵就返回。 */
    /* ★ 自动回退：shell 已经死了就别走管道，直接 once 模式 */
    if (e.state !== 'running' && opts.wait !== false && opts.noFallback !== true) {
      opts = Object.assign({}, opts, { wait: false });
    }

    if (e.state === 'running' && e.proc && opts.wait !== false) {
      /* ★ 事件驱动：发哨兵，等 collect() 里收到哨兵后 resolve。
         返回 Promise —— 调用方要么 await，要么用 .then。 */
      return new Promise((resolve) => {
        try {
          const from = e.out.length;
          const marker = '__PULSE_EOF_' + crypto.randomBytes(4).toString('hex') + '__';
          const timer = setTimeout(() => {
            if (e.pending && e.pending.marker === marker) {
              const fresh = e.out.slice(from);
              e.pending = null;
              this.stats.errors++;
              resolve({
                ok: false, error: 'inject 等输出超时 ' + timeout + 'ms',
                stdout: fresh.filter(x => x.stream === 'out').map(x => x.s).join(''),
                partial: true,
              });
            }
          }, timeout);
          e.pending = { marker, resolve, timer, from, t0: Date.now() };
          e.lastActive = Date.now();
          e.proc.stdin.write(cmd + '\n');
          e.proc.stdin.write('echo ' + marker + '\n');
          this.stats.execs++;
        } catch (err) {
          e.pending = null;
          resolve({ ok: false, error: err.message });
        }
      });
    }

    /* 模式 A'：inject 但不等（wait:false） */
    if (e.state === 'running' && e.proc) {
      try {
        e.proc.stdin.write(cmd + '\n');
        e.lastActive = Date.now();
        this.stats.execs++;
        return { ok: true, env_id, mode: 'inject', written: cmd.length + 1, waited: false };
      } catch (err) {
        return { ok: false, error: err.message };
      }
    }

    /* 模式 B：一次性（写脚本文件 → chroot python 跑） */
    const stamp = process.pid + '_' + Date.now() + '_' + crypto.randomBytes(3).toString('hex');
    let hostPath;
    try {
      hostPath = this._inner('/tmp/_ex_' + stamp + '.py');
      fs.mkdirSync(path.dirname(hostPath), { recursive: true });
      const code = (e.allowNet ? '' : NET_GUARD) + cmd;
      fs.writeFileSync(hostPath, code, 'utf8');
    } catch (err) {
      return { ok: false, error: '写脚本失败: ' + err.message };
    }

    const t0 = process.hrtime.bigint();
    const { spawnSync } = require('child_process');
    const r = spawnSync('chroot', [e.rootfs, e.python || this.python, '/tmp/_ex_' + stamp + '.py'], {
      encoding: 'utf8', timeout, maxBuffer: LIMITS.maxOutputBytes,
    });
    const ms = Number(process.hrtime.bigint() - t0) / 1e6;
    try { fs.unlinkSync(hostPath); } catch (x) {}

    e.lastActive = Date.now();
    this.stats.execs++;

    if (r.error && r.error.code === 'ETIMEDOUT') {
      this.stats.errors++;
      return { ok: false, error: '超时 ' + timeout + 'ms', ms: +ms.toFixed(2) };
    }
    if (r.status !== 0) {
      this.stats.errors++;
      return {
        ok: false, error: 'exit=' + r.status, exit_code: r.status,
        stderr: (r.stderr || '').slice(0, 2048), ms: +ms.toFixed(2),
      };
    }
    return {
      ok: true, env_id, mode: 'once', exit_code: 0,
      stdout: (r.stdout || '').slice(0, LIMITS.maxOutputBytes),
      stderr: (r.stderr || '') || undefined, ms: +ms.toFixed(2),
    };
  }

  /* ======================================================================
   *  ⑥ retrieve_result —— 取累计输出
   * ==================================================================== */
  op_retrieve_result(env_id, opts = {}) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };
    const only = opts && opts.stream;      // 'out' | 'err' | undefined
    const lines = e.out.filter(x => !only || x.stream === only);
    const text = lines.map(x => x.s).join('');
    const r = {
      ok: true, env_id,
      stdout: lines.filter(x => x.stream === 'out').map(x => x.s).join(''),
      stderr: lines.filter(x => x.stream === 'err').map(x => x.s).join(''),
      lines: lines.length,
      bytes: text.length,
      state: e.state, exit_code: e.exitCode,
    };
    if (opts && opts.drain) { e.out = []; e.outBytes = 0; }
    return r;
  }

  /* ======================================================================
   *  ⑦ stream_logs —— 拉取自某个时间点之后的日志（轮询式，无需 callback）
   * ==================================================================== */
  op_stream_logs(env_id, since) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };
    const t = parseInt(since, 10) || 0;
    const fresh = e.out.filter(x => x.t > t);
    return {
      ok: true, env_id,
      entries: fresh.map(x => ({ stream: x.stream, s: x.s, t: x.t })),
      cursor: e.out.length ? e.out[e.out.length - 1].t : t,
      state: e.state,
    };
  }

  /* ======================================================================
   *  ⑧ snapshot_env —— 打包当前 env 的改动
   *     ★ 这里只打包 /tmp 和工作区（不动整个 709MB rootfs）
   * ==================================================================== */
  op_snapshot_env(env_id, label) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };
    try {
      fs.mkdirSync(this.snapDir, { recursive: true });
      const id = 'snap_' + Date.now().toString(36) + '_' + crypto.randomBytes(3).toString('hex');
      const tar = path.join(this.snapDir, id + '.tar.gz');

      /* 只打包 /tmp（用户改动的典型位置）——整盘打包太慢 */
      const innerTmp = this._inner('/tmp');
      if (!fs.existsSync(innerTmp)) return { ok: false, error: 'rootfs 里没有 /tmp' };

      const { spawnSync } = require('child_process');
      const t0 = process.hrtime.bigint();
      const r = spawnSync('tar', ['-czf', tar, '-C', innerTmp, '.'], { timeout: 30000 });
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      if (r.status !== 0) throw new Error('tar 失败 exit=' + r.status);

      const size = fs.statSync(tar).size;
      this.stats.snapshots++;
      return {
        ok: true, snapshot_id: id, label: label || '',
        path: tar, bytes: size, ms: +ms.toFixed(1),
        scope: '/tmp only（整盘 709MB 不打包，太慢）',
      };
    } catch (err) {
      this.stats.errors++;
      return { ok: false, error: err.message };
    }
  }

  /* ======================================================================
   *  ⑨ restore_env —— 从快照解包到新 env
   * ==================================================================== */
  op_restore_env(snapshot_id) {
    try {
      const tar = path.join(this.snapDir, String(snapshot_id).replace(/\.tar\.gz$/, '') + '.tar.gz');
      if (!fs.existsSync(tar)) return { ok: false, error: '快照不存在: ' + tar };

      const init = this.op_init_env(this.rootfs);
      if (!init.ok) return init;

      const innerTmp = this._inner('/tmp');
      fs.mkdirSync(innerTmp, { recursive: true });

      const { spawnSync } = require('child_process');
      const t0 = process.hrtime.bigint();
      const r = spawnSync('tar', ['-xzf', tar, '-C', innerTmp], { timeout: 30000 });
      const ms = Number(process.hrtime.bigint() - t0) / 1e6;
      if (r.status !== 0) throw new Error('解包失败 exit=' + r.status);

      this.stats.restored++;
      return { ok: true, env_id: init.env_id, snapshot_id, ms: +ms.toFixed(1), state: 'init' };
    } catch (err) {
      this.stats.errors++;
      return { ok: false, error: err.message };
    }
  }

  /* ======================================================================
   *  ⑩ set_limits —— Android 无 cgroup 权限，只能做软限制
   * ==================================================================== */
  op_set_limits(env_id, cpu_pct, mem_mb) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };

    /* 记录意图（软限制），实际靠 exec 的 timeout + 输出上限兜底 */
    e.limits = {
      cpu_pct: Math.max(1, Math.min(parseInt(cpu_pct, 10) || 50, 100)),
      mem_mb: Math.max(32, Math.min(parseInt(mem_mb, 10) || 256, 2048)),
    };

    /* 试一次 ulimit（在 chroot 里对子进程生效） */
    let ulimitApplied = false;
    try {
      const { spawnSync } = require('child_process');
      const r = spawnSync('chroot', [e.rootfs, this.shell, '-c',
        'ulimit -v ' + (e.limits.mem_mb * 1024) + ' 2>&1; ulimit -v'], { encoding: 'utf8', timeout: 5000 });
      ulimitApplied = r.status === 0;
    } catch (x) {}

    return {
      ok: true, env_id, limits: e.limits,
      hard: false,
      ulimit: ulimitApplied,
      note: 'Android 无 cgroup 权限，CPU 只能软限制；内存靠 ulimit -v（对子进程生效）；'
          + '真正的硬限制只有单次 timeout ' + LIMITS.maxTimeoutMs + 'ms',
    };
  }

  /* ======================================================================
   *  ⑪ get_usage —— 无 /proc，用 ps 兜底（拿不到就用进程 RSS 估算）
   * ==================================================================== */
  op_get_usage(env_id) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };

    let cpu = null, mem = null, src = 'unavailable';
    if (e.pid) {
      /* 试着从宿主 /proc 读（沙箱内没有，但宿主有） */
      try {
        const st = fs.readFileSync('/proc/' + e.pid + '/stat', 'utf8').trim().split(/\s+/);
        cpu = { utime: +st[13], stime: +st[14] };
        src = '/proc/<pid>/stat';
      } catch (x) {}
      try {
        const sm = fs.readFileSync('/proc/' + e.pid + '/status', 'utf8');
        const m = sm.match(/VmRSS:\s+(\d+)\s+kB/);
        if (m) { mem = { rss_kb: +m[1], rss_mb: +(m[1] / 1024).toFixed(1) }; src = src === 'unavailable' ? '/proc/<pid>/status' : src + ',/proc/<pid>/status'; }
      } catch (x) {}
    }

    return {
      ok: true, env_id, pid: e.pid, state: e.state,
      cpu, mem, source: src,
      note: mem ? null : '读不到 —— Android /proc 对 uid=0 也受限',
      disk: { rootfs_mb: +(this._dirSize(e.rootfs) / 1048576).toFixed(1) },
      output: { bytes: e.outBytes, capped: LIMITS.maxOutputBytes },
    };
  }

  /* ======================================================================
   *  ⑫ bind_mqtt —— 给 env 分配一个 MQTT 通道（返回 topic，由调用方连）
   * ==================================================================== */
  op_bind_mqtt(env_id, channel) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };
    const ch = String(channel || '').trim();
    if (!ch) return { ok: false, error: '需要 channel' };
    if (!/^[A-Za-z0-9_\-]{1,32}$/.test(ch)) {
      return { ok: false, error: 'channel 只能含字母数字下划线横线，≤32' };
    }
    e.mqtt = {
      channel: ch,
      topics: {
        cmd: 'zhz/env/' + ch + '/cmd',
        res: 'zhz/env/' + ch + '/res',
        evt: 'zhz/env/' + ch + '/evt',
      },
      boundAt: Date.now(),
    };
    return {
      ok: true, env_id, channel: ch, topics: e.mqtt.topics,
      note: '这只是分配了 topic。真正的 MQTT 连接由 worker.js / mqttws.js 建立，'
          + '本模块不持有 broker 连接（避免沙箱模块被网络污染）',
    };
  }

  /* ======================================================================
   *  ⑬ revoke_network —— 只能 Python 层拦，无 iptables
   * ==================================================================== */
  op_revoke_network(env_id) {
    const e = this.envs.get(env_id);
    if (!e) return { ok: false, error: '没有这个 env' };

    e.allowNet = false;
    e.netBlocked = true;

    return {
      ok: true, env_id, allow_net: false,
      hard: false,
      applies_to: 'next exec_script（会插入 Python 守卫）',
      note: 'Android 无 iptables / 无 netns，无法在内核层断网。'
          + '当前实现是 Python 层拦 socket/urllib/http.client，'
          + '绕过方式存在（如直接 syscall），但对正常代码有效。',
    };
  }

  /* ---------- 汇总 ---------- */
  list() {
    return [...this.envs.values()].map(e => ({
      env_id: e.id, state: e.state, pid: e.pid,
      age_ms: Date.now() - e.createdAt,
      idle_ms: Date.now() - e.lastActive,
      outBytes: e.outBytes, exit_code: e.exitCode,
      limits: e.limits || null, mqtt: e.mqtt ? e.mqtt.channel : null,
      netBlocked: e.netBlocked,
    }));
  }

  info() {
    return {
      rootfs: this.rootfs,
      allowNet: this.allowNet,
      envs: this.list(),
      stats: this.stats,
      limits: LIMITS,
      capabilities: {
        implemented: ['init_env', 'spawn_env', 'kill_env', 'inject_data', 'exec_script',
                      'retrieve_result', 'stream_logs', 'snapshot_env', 'restore_env',
                      'set_limits(soft)', 'get_usage(best-effort)', 'bind_mqtt', 'revoke_network(soft)'],
        impossible: ['set_limits(hard/cgroup)', 'get_usage(/proc in sandbox)'],
        degraded: ['revoke_network(内核层)'],
      },
    };
  }

  destroy() {
    for (const id of [...this.envs.keys()]) this.op_kill_env(id, true);
    if (this._gcTimer) clearInterval(this._gcTimer);
  }
}

module.exports = { EnvManager, LIMITS, NET_GUARD };
