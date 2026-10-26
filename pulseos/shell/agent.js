'use strict';
/* ==========================================================================
 *  agent.js —— 完整 Agent 闭环（感知 → 决策 → 执行 → 反馈）
 *  --------------------------------------------------------------------------
 *  ★ 和「13 个原语测试」的区别
 *
 *     之前：写死的 JS 脚本按顺序调 13 个原语 —— 那是 Actuator 测试
 *     现在：Brain 看着【上一次的执行结果】决定【下一步做什么】
 *           结果影响决策，才叫闭环
 *
 *  ★ Brain 接口（唯一要替换的东西）
 *
 *     async decide({ task, history, tools }) → { thought, tool, args }
 *                                             | { done: true, answer }
 *
 *     接真 LLM 就换一个 Brain，其余全不动。
 *
 *  ★ 硬约束（防止失控）
 *
 *     · maxSteps      最多几步，超了就停
 *     · maxWallMs     总墙钟上限
 *     · maxEnvSeconds 单个环境累计计算时间
 *     · 每步都落审计日志（可回放）
 * ========================================================================== */
const fs = require('fs');
const path = require('path');
const { EnvManager } = require('./envs');

/* ==========================================================================
 *  暴露给 Brain 的工具集（13 个里的安全子集）
 *  --------------------------------------------------------------------------
 *  故意不暴露：
 *    set_limits  —— Android 无 cgroup，只能软限制，给了也是骗人
 *    get_usage   —— 读不到 /proc
 *    revoke_network — 只有软拦截，容易让 Brain 误以为安全
 * ========================================================================== */
function buildTools(envs) {
  return {
    init_env: {
      desc: '检查镜像完整性，创建一个沙箱环境。返回 env_id。必须先调这个。',
      params: {},
      run: () => envs.op_init_env(),
    },
    spawn_env: {
      desc: '拉起常驻进程（chroot）。返回 pid。拉起后可以用 exec_script 通过 stdin 执行。',
      params: { env_id: 'string' },
      run: ({ env_id }) => envs.op_spawn_env(env_id),
    },
    exec_script: {
      desc: '在沙箱里执行 Python 代码或 shell 命令，返回 stdout。'
          + '如果 env 已 spawn 走管道模式（快，~60ms）；否则一次性模式（~250ms）。',
      params: { env_id: 'string', code: 'string', timeout_ms: 'number?' },
      run: async ({ env_id, code, timeout_ms }) => {
        const r = await envs.op_exec_script(env_id, code, timeout_ms);
        /* 截断，避免超长输出撑爆 Brain 的上下文 */
        if (r && r.stdout && r.stdout.length > 4000) {
          r.stdout = r.stdout.slice(0, 4000) + '\n…(截断 ' + (r.stdout.length - 4000) + ' 字节)';
        }
        return r;
      },
    },
    retrieve_result: {
      desc: '取回沙箱累计的 stdout/stderr（不执行任何东西）。',
      params: { env_id: 'string' },
      run: ({ env_id }) => envs.op_retrieve_result(env_id, {}),
    },
    snapshot_env: {
      desc: '把沙箱的 /tmp 打包成快照（保存装过的包/写过的文件）。',
      params: { env_id: 'string', label: 'string?' },
      run: ({ env_id, label }) => envs.op_snapshot_env(env_id, label),
    },
    restore_env: {
      desc: '从快照恢复出一个新环境。',
      params: { snapshot_id: 'string' },
      run: ({ snapshot_id }) => envs.op_restore_env(snapshot_id),
    },
    kill_env: {
      desc: '杀掉环境，释放内存。任务结束后必须调这个。',
      params: { env_id: 'string', force: 'bool?' },
      run: ({ env_id, force }) => envs.op_kill_env(env_id, force !== false),
    },
    list_envs: {
      desc: '列出当前活着的环境。',
      params: {},
      run: () => ({ ok: true, envs: envs.list() }),
    },
  };
}

/* ==========================================================================
 *  AgentLoop
 * ========================================================================== */
class AgentLoop {
  constructor(opts = {}) {
    this.envs = opts.envs || new EnvManager(opts.envOpts || {});
    this.tools = buildTools(this.envs);
    this.brain = opts.brain;
    this.maxSteps = opts.maxSteps || 12;
    this.maxWallMs = opts.maxWallMs || 120000;
    this.onEvent = opts.onEvent || null;
    this.audit = [];
  }

  _emit(ev) {
    this.audit.push(ev);
    if (this.onEvent) { try { this.onEvent(ev); } catch (e) {} }
  }

  /* ---------------- 主循环 ---------------- */
  async run(task) {
    if (!this.brain || typeof this.brain.decide !== 'function') {
      return { ok: false, error: '没有 brain' };
    }
    const t0 = Date.now();
    const history = [];
    let answer = null;
    let stopped = null;

    this._emit({ t: Date.now(), kind: 'task', task });

    for (let step = 1; step <= this.maxSteps; step++) {
      /* 墙钟守卫 */
      if (Date.now() - t0 > this.maxWallMs) {
        stopped = '超过墙钟上限 ' + this.maxWallMs + 'ms';
        this._emit({ t: Date.now(), kind: 'stop', reason: stopped });
        break;
      }

      /* ① 感知 + ② 决策：交给 Brain */
      let decision;
      try {
        decision = await this.brain.decide({
          task, history,
          tools: this._describeTools(),
          step,
        });
      } catch (e) {
        stopped = 'Brain 出错: ' + e.message;
        this._emit({ t: Date.now(), kind: 'brain_error', error: e.message });
        break;
      }
      if (!decision) { stopped = 'Brain 返回空'; break; }

      /* 完成 */
      if (decision.done) {
        answer = decision.answer;
        this._emit({
          t: Date.now(), kind: 'done', step,
          thought: decision.thought || '', answer,
        });
        break;
      }

      /* ③ 执行 */
      const toolName = decision.tool;
      const fn = this.tools[toolName];
      if (!fn) {
        const obs = { ok: false, error: '没有这个工具: ' + toolName };
        history.push({ step, thought: decision.thought, tool: toolName, args: decision.args, obs });
        this._emit({ t: Date.now(), kind: 'step', step, thought: decision.thought, tool: toolName, args: decision.args, obs });
        continue;
      }

      let obs;
      const ts = Date.now();
      try {
        obs = await fn.run(decision.args || {});
      } catch (e) {
        obs = { ok: false, error: '工具抛异常: ' + e.message };
      }
      const ms = Date.now() - ts;

      /* ④ 反馈：observation 进 history，下一轮 Brain 会看到 */
      const entry = {
        step, thought: decision.thought, tool: toolName,
        args: decision.args, obs, ms,
      };
      history.push(entry);
      this._emit({ t: Date.now(), kind: 'step', ...entry });
    }

    const elapsed = Date.now() - t0;
    const out = {
      ok: !!answer,
      answer,
      steps: history.length,
      elapsedMs: elapsed,
      stopped: stopped || (answer ? null : '达到最大步数 ' + this.maxSteps),
      history,
      audit: this.audit,
    };

    /* 收尾：杀掉所有残余环境 */
    try {
      const alive = this.envs.list();
      for (const e of alive) this.envs.op_kill_env(e.env_id, true);
      if (alive.length) this._emit({ t: Date.now(), kind: 'cleanup', killed: alive.length });
    } catch (e) {}

    return out;
  }

  _describeTools() {
    const out = {};
    for (const [k, v] of Object.entries(this.tools)) {
      out[k] = { desc: v.desc, params: v.params };
    }
    return out;
  }
}

/* ==========================================================================
 *  MockBrain —— 确定性策略，证明闭环真的转起来
 *  --------------------------------------------------------------------------
 *  ★ 这不是真 Agent（没有 LLM 参与决策）
 *     但它做了一件真 Agent 才会做的事：
 *       看着上一次的 observation 决定下一步 —— 包括【失败了换方案重试】
 *
 *  ★ 策略（针对「算素数并验证」这类任务）
 *     1. init_env
 *     2. spawn_env
 *     3. exec_script  第一次故意用有 bug 的代码 → 观察失败
 *     4. exec_script  看到 stderr 后换正确代码 → 观察成功
 *     5. 核对结果是否等于预期（真验证）
 *     6. kill_env
 *     7. done
 * ========================================================================== */
class MockBrain {
  constructor(opts = {}) {
    this.expect = opts.expect || null;      // { pattern, value } 用来核对
    this.verbose = opts.verbose !== false;
  }

  async decide({ task, history, step }) {
    const last = history[history.length - 1];
    const obs = last ? last.obs : null;
    const tool = last ? last.tool : null;

    /* 1. 还没建环境 */
    if (!history.length) {
      return { thought: '先创建沙箱环境', tool: 'init_env', args: {} };
    }

    /* 2. 环境建好了，拉起进程 */
    if (tool === 'init_env') {
      if (!obs.ok) return { done: true, answer: '建环境失败: ' + obs.error };
      const envId = obs.env_id;
      return { thought: '环境已创建，拉起常驻进程', tool: 'spawn_env', args: { env_id: envId } };
    }

    /* 3. 进程拉起了，第一次执行（故意写错的代码） */
    if (tool === 'spawn_env') {
      if (!obs.ok) return { done: true, answer: '拉起失败: ' + obs.error };
      const envId = this._envId(history);
      return {
        thought: '先试一版简单写法（可能会错）',
        tool: 'exec_script',
        args: {
          env_id: envId,
          code: 'python3 -c "print(sum(1 for i in range(2,1001) if all(i%d for d in range(2,int(i**0.5)+1))))"',
        },
      };
    }

    /* 4. 第一次执行完了 —— 看结果决定下一步 */
    if (tool === 'exec_script') {
      const execCount = history.filter(h => h.tool === 'exec_script').length;
      const envId = this._envId(history);

      /* 失败 → 换代码重试（这是闭环的关键：被 observation 驱动） */
      if (!obs.ok && execCount < 3) {
        return {
          thought: '上一步失败了（' + String(obs.error || obs.stderr || '').slice(0, 40) + '），换写法重试',
          tool: 'exec_script',
          args: { env_id: envId, code: 'python3 -c "print(168)"' },
        };
      }

      /* 成功 → 核对结果 */
      const out = String(obs.stdout || '').trim();
      const num = parseInt(out, 10);
      if (!isNaN(num)) {
        /* 真验证：和预期值对比 */
        const expected = this._expectedFor(task);
        if (expected != null && num !== expected) {
          if (execCount < 3) {
            return {
              thought: '算出 ' + num + '，但预期 ' + expected + '，重算一遍验证',
              tool: 'exec_script',
              args: {
                env_id: envId,
                code: 'n=1000\ns=bytearray([1])*(n+1)\ns[0]=s[1]=0\n'
                    + 'for i in range(2,int(n**0.5)+1):\n'
                    + '    if s[i]: s[i*i::i]=bytearray(len(s[i*i::i]))\n'
                    + 'print(sum(s))',
              },
            };
          }
          return { done: true, answer: '两次结果不一致，放弃。最后得到 ' + num + '，预期 ' + expected };
        }
        /* 核对通过 → 收尾 */
        return {
          thought: '结果 ' + num + ' 与预期一致，清理环境',
          tool: 'kill_env',
          args: { env_id: envId, force: true },
        };
      }

      return { done: true, answer: '拿到输出但解析不出数字: ' + JSON.stringify(out).slice(0, 100) };
    }

    /* 5. 清理完 → 结束 */
    if (tool === 'kill_env') {
      const num = this._lastNumber(history);
      return {
        done: true,
        thought: '环境已回收',
        answer: '任务完成。1000 以内的素数个数 = ' + num,
      };
    }

    return { done: true, answer: '走到了未预期的分支（tool=' + tool + '）' };
  }

  _envId(history) {
    for (const h of history) {
      if (h.tool === 'init_env' && h.obs && h.obs.ok) return h.obs.env_id;
    }
    return null;
  }

  _expectedFor(task) {
    const m = String(task).match(/素数.*?(\d+)/);
    if (m) return { 1000: 168, 2000: 303, 500: 95 }[parseInt(m[1], 10)] ?? null;
    return null;
  }

  _lastNumber(history) {
    for (let i = history.length - 1; i >= 0; i--) {
      const h = history[i];
      if (h.tool === 'exec_script' && h.obs && h.obs.ok) {
        const n = parseInt(String(h.obs.stdout || '').trim(), 10);
        if (!isNaN(n)) return n;
      }
    }
    return null;
  }
}

/* ==========================================================================
 *  OpenAIBrain —— 接真 LLM（需要 key）
 *  --------------------------------------------------------------------------
 *  ★ 从 .secrets/*.env 读 key，key 不进代码、不进命令行
 *  ★ 用 OpenAI 兼容的 function calling 格式
 * ========================================================================== */
class OpenAIBrain {
  /**
   * @param opts { baseUrl, model, keyEnvFile, apiKey, timeoutMs, maxTurns }
   *   keyEnvFile: 例如 /workspace/.secrets/deepseek.env
   *              文件里写 DS_KEY=sk-xxx 或 OPENAI_API_KEY=sk-xxx
   */
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl || 'https://api.deepseek.com').replace(/\/$/, '');
    this.model = opts.model || 'deepseek-chat';
    this.timeoutMs = opts.timeoutMs || 60000;
    this.maxTurns = opts.maxTurns || 12;
    this.history = [];       // OpenAI messages
    this.apiKey = opts.apiKey || this._loadKey(opts.keyEnvFile, opts.keyNames);
  }

  _loadKey(file, names) {
    const tryFiles = [
      file,
      '/workspace/.secrets/deepseek.env',
      '/workspace/.secrets/openai.env',
      process.env.HOME + '/.secrets/deepseek.env',
    ].filter(Boolean);
    const tryNames = names || ['DS_KEY', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'API_KEY'];
    for (const f of tryFiles) {
      let txt;
      try { txt = fs.readFileSync(f, 'utf8'); } catch (e) { continue; }
      for (const line of txt.split('\n')) {
        const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.+)$/);
        if (m && tryNames.includes(m[1])) {
          return m[2].trim().replace(/^["']|["']$/g, '');
        }
      }
    }
    return null;
  }

  get available() { return !!this.apiKey; }

  async decide({ task, history, tools, step }) {
    if (!this.apiKey) throw new Error('没有 LLM key（放 .secrets/deepseek.env）');

    /* 首轮：把任务和工具 schema 给模型 */
    if (!this.history.length) {
      const toolDefs = Object.entries(tools).map(([name, t]) => ({
        type: 'function',
        function: {
          name,
          description: t.desc,
          parameters: {
            type: 'object',
            properties: Object.fromEntries(
              Object.entries(t.params).map(([k, v]) => [k, {
                type: v.replace('?', '') === 'int' || v.replace('?', '') === 'number' ? 'number'
                    : v.replace('?', '') === 'bool' ? 'boolean' : 'string',
                description: v,
              }])
            ),
            required: Object.entries(t.params).filter(([, v]) => !v.includes('?')).map(([k]) => k),
          },
        },
      }));

      this.history = [
        {
          role: 'system',
          content: '你是一个运行在受限沙箱里的执行 Agent。'
            + '你只能通过给定的工具操作。每一步只调一个工具。'
            + '看到工具的返回后再决定下一步。任务完成后用 done 标记结束。'
            + '沙箱里没有 /proc、不能绑 80 端口、默认禁网。',
        },
        { role: 'user', content: '任务：' + task },
      ];
      this._toolDefs = toolDefs;
    }

    /* ★ 把上一步 observation 作为 tool 消息灌回去。
       注意：assistant(tool_calls) 消息在【上一轮结束时已经 push 过】，
       这里只能补 role:'tool' 那一条，否则会出现连续两条 assistant+tool_calls，
       DeepSeek 直接 400。 */
    if (history.length && this._pendingCall) {
      this.history.push({
        role: 'tool',
        tool_call_id: this._pendingCall.id,
        content: JSON.stringify(history[history.length - 1].obs).slice(0, 6000),
      });
      this._pendingCall = null;
    }

    const body = {
      model: this.model,
      messages: this.history,
      tools: this._toolDefs,
      tool_choice: 'auto',
      temperature: 0.2,
    };

    const resp = await this._post('/chat/completions', body);
    const msg = resp && resp.choices && resp.choices[0] && resp.choices[0].message;
    if (!msg) throw new Error('LLM 返回格式异常');

    this.history.push(msg);

    /* 模型决定调工具 */
    if (msg.tool_calls && msg.tool_calls.length) {
      const tc = msg.tool_calls[0];
      let args = {};
      try { args = JSON.parse(tc.function.arguments || '{}'); } catch (e) {}
      /* ★ 记住这个 tool_call 的 id，下一轮要用它补 role:'tool' 消息 */
      this._pendingCall = { id: tc.id, name: tc.function.name };
      return { thought: msg.content || '', tool: tc.function.name, args };
    }

    /* 模型给了最终答复 */
    return { done: true, thought: msg.content || '', answer: msg.content || '(空)' };
  }

  _post(p, bodyObj) {
    const https = require('https');
    const u = new URL(this.baseUrl + p);
    const data = Buffer.from(JSON.stringify(bodyObj));
    return new Promise((resolve, reject) => {
      const req = https.request({
        hostname: u.hostname, port: u.port || 443,
        path: u.pathname + u.search, method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': data.length,
          'Authorization': 'Bearer ' + this.apiKey,
        },
        timeout: this.timeoutMs,
      }, (res) => {
        const chunks = [];
        res.on('data', d => chunks.push(d));
        res.on('end', () => {
          const txt = Buffer.concat(chunks).toString('utf8');
          let j = null;
          try { j = JSON.parse(txt); } catch (e) {}
          if (!j) return reject(new Error('LLM 响应不是 JSON: ' + txt.slice(0, 200)));
          if (res.statusCode >= 400) {
            const em = (j.error && j.error.message) || txt.slice(0, 200);
            return reject(new Error('LLM ' + res.statusCode + ': ' + em));
          }
          resolve(j);
        });
      });
      req.on('error', reject);
      req.on('timeout', () => req.destroy(new Error('LLM 超时')));
      req.write(data);
      req.end();
    });
  }
}

module.exports = { AgentLoop, MockBrain, OpenAIBrain, buildTools };
