'use strict';
/* ==========================================================================
 *  agent_worker_patch.js —— 把 AgentLoop 接进 MQTT worker
 *  --------------------------------------------------------------------------
 *  这个文件不单独跑，是被 worker.js require 的「能力补丁」。
 *
 *  ★ 新增的 MQTT 能力
 *
 *     run_agent   { task, maxSteps?, maxWallMs? }  → 一次完整 Agent 闭环
 *     agent_log   { run_id, since? }               → 拉取这次运行的审计日志
 *
 *  ★ 关键设计：长任务不能堵住 MQTT
 *
 *      Agent 一次跑 10~60 秒。如果同步跑，期间所有 MQTT 消息都会被堵。
 *      所以：
 *        ① 立刻回 ack {ok:true, run_id, accepted:true}
 *        ② 后台异步跑
 *        ③ 每步通过 evt 主题实时推
 *        ④ 跑完推 final 到 reply
 *
 *  ★ 安全边界（三级白名单 + 预算）
 *
 *      · ALLOW_AGENT 环境变量控制是否启用（默认关）
 *      · maxSteps / maxWallMs 硬上限，调用方不能超
 *      · 沙箱 rootfs 由 worker 启动时固定，调用方不能指定
 * ========================================================================== */
const crypto = require('crypto');
const { AgentLoop, OpenAIBrain } = require('./agent');
const { EnvManager } = require('./envs');

/* ---------------- 预算硬顶（调用方不能超） ---------------- */
const AGENT_LIMITS = {
  maxSteps: 12,
  maxWallMs: 120000,        // 2 分钟
  maxConcurrent: 2,         // 同时最多 2 个 Agent 跑
  maxTaskChars: 2000,
};

/* ---------------- 运行记录 ---------------- */
const runs = new Map();     // run_id -> { task, status, events, result, startedAt, ... }

function createAgentBridge(opts) {
  const {
    rootfs,                    // 沙箱镜像（worker 启动时固定）
    pub,                       // (topic, obj, retain?) => void
    NS,                        // 命名空间前缀
    brainOpts = {},            // 传给 OpenAIBrain
    allowAgent = false,        // ★ 默认关闭
    persistMs = 600000,        // 运行记录保留 10 分钟
  } = opts;

  /* 没启用就直接返回空补丁 */
  if (!allowAgent) {
    return {
      enabled: false,
      capabilities: {},
      info: () => ({ enabled: false, reason: '未启用（需要 --allow-agent）' }),
    };
  }

  const available = new Set();

  /* ---------------- 清理过期运行记录 ---------------- */
  const gc = setInterval(() => {
    const now = Date.now();
    for (const [id, r] of runs) {
      if (now - r.startedAt > persistMs && r.status !== 'running') runs.delete(id);
    }
  }, 60000);
  if (gc.unref) gc.unref();

  /* ======================================================================
   *  run_agent —— 跑一次完整闭环
   * ==================================================================== */
  async function runAgent(params) {
    const task = String(params.task || '').trim();
    if (!task) return { ok: false, error: '缺少 params.task' };
    if (task.length > AGENT_LIMITS.maxTaskChars) {
      return { ok: false, error: 'task 超过 ' + AGENT_LIMITS.maxTaskChars + ' 字符' };
    }

    /* 并发限制 */
    const running = [...runs.values()].filter(r => r.status === 'running').length;
    if (running >= AGENT_LIMITS.maxConcurrent) {
      return {
        ok: false,
        error: '当前已有 ' + running + ' 个 Agent 在跑（上限 ' + AGENT_LIMITS.maxConcurrent + '）',
        running: [...runs.entries()].filter(([, r]) => r.status === 'running').map(([id]) => id),
      };
    }

    /* 预算：调用方可以调小，不能调大 */
    const maxSteps = Math.min(parseInt(params.maxSteps, 10) || AGENT_LIMITS.maxSteps, AGENT_LIMITS.maxSteps);
    const maxWallMs = Math.min(parseInt(params.maxWallMs, 10) || AGENT_LIMITS.maxWallMs, AGENT_LIMITS.maxWallMs);

    const runId = 'run_' + crypto.randomBytes(5).toString('hex');
    const rec = {
      run_id: runId, task, status: 'running',
      startedAt: Date.now(), endedAt: null,
      events: [], maxSteps, maxWallMs,
      step: 0,
    };
    runs.set(runId, rec);

    /* ★ 立刻返回 ack，不阻塞 MQTT */
    const ack = { ok: true, run_id: runId, accepted: true, maxSteps, maxWallMs };

    /* 后台异步跑 */
    (async () => {
      let envs = null;
      try {
        envs = new EnvManager({ rootfs, allowNet: false });
        const brain = new OpenAIBrain(brainOpts);
        if (!brain.available) throw new Error('没有 LLM key（放 .secrets/deepseek.env）');

        const loop = new AgentLoop({
          envs, brain, maxSteps, maxWallMs,
          onEvent: (ev) => {
            /* 每步实时推 evt */
            if (ev.kind === 'step') {
              rec.step = ev.step;
              rec.events.push({
                t: ev.t, step: ev.step, thought: ev.thought,
                tool: ev.tool, args: ev.args,
                ok: ev.obs && ev.obs.ok,
                stdout: ev.obs && ev.obs.stdout ? String(ev.obs.stdout).slice(0, 800) : undefined,
                error: ev.obs && ev.obs.error ? String(ev.obs.error).slice(0, 400) : undefined,
                ms: ev.ms,
              });
              pub(NS + 'evt', JSON.stringify({
                run_id: runId, kind: 'step', step: ev.step,
                thought: ev.thought, tool: ev.tool,
                argsBrief: JSON.stringify(ev.args || {}).slice(0, 300),
                ok: ev.obs && ev.obs.ok,
                out: ev.obs && ev.obs.stdout ? String(ev.obs.stdout).slice(0, 300) : undefined,
                err: ev.obs && ev.obs.error ? String(ev.obs.error).slice(0, 200) : undefined,
                ms: ev.ms,
              }));
            } else if (ev.kind === 'task') {
              pub(NS + 'evt', JSON.stringify({
                run_id: runId, kind: 'start', step: 0, tool: '(start)',
                task, ok: true, ms: 0,
              }));
            } else if (ev.kind === 'cleanup') {
              pub(NS + 'evt', JSON.stringify({ run_id: runId, kind: 'cleanup', killed: ev.killed }));
            } else if (ev.kind === 'stop' || ev.kind === 'brain_error') {
              pub(NS + 'evt', JSON.stringify({ run_id: runId, kind: ev.kind, reason: ev.reason || ev.error }));
            }
          },
        });

        const r = await loop.run(task);

        rec.status = r.ok ? 'done' : 'failed';
        rec.endedAt = Date.now();
        rec.result = {
          ok: r.ok, answer: r.answer, steps: r.steps,
          elapsedMs: r.elapsedMs, stopped: r.stopped,
        };

        /* 最终结果推 reply */
        pub(NS + 'reply', JSON.stringify({
          run_id: runId, ok: r.ok, done: true,
          answer: r.answer, steps: r.steps,
          elapsed_ms: r.elapsedMs,
          stopped: r.stopped,
          audit_count: rec.events.length,
        }));

      } catch (e) {
        rec.status = 'error';
        rec.endedAt = Date.now();
        rec.result = { ok: false, error: e.message };
        pub(NS + 'reply', JSON.stringify({
          run_id: runId, ok: false, done: true, error: e.message,
        }));
      } finally {
        try { if (envs) envs.destroy(); } catch (e) {}
      }
    })();

    return ack;
  }

  /* ======================================================================
   *  agent_log —— 拉审计日志（复盘用）
   * ==================================================================== */
  function agentLog(params) {
    const id = String(params.run_id || '');
    const rec = runs.get(id);
    if (!rec) return { ok: false, error: '没有这次运行: ' + id, known: [...runs.keys()] };
    const since = parseInt(params.since, 10) || 0;
    return {
      ok: true,
      run_id: id,
      task: rec.task,
      status: rec.status,
      step: rec.step,
      started_at: rec.startedAt,
      elapsed_ms: (rec.endedAt || Date.now()) - rec.startedAt,
      result: rec.result || null,
      events: rec.events.filter(e => e.t > since),
      cursor: rec.events.length ? rec.events[rec.events.length - 1].t : since,
    };
  }

  /* ======================================================================
   *  agent_cancel —— 请求取消（协作式，靠 maxWallMs 兜底）
   * ==================================================================== */
  function agentCancel(params) {
    const id = String(params.run_id || '');
    const rec = runs.get(id);
    if (!rec) return { ok: false, error: '没有这次运行: ' + id };
    if (rec.status !== 'running') return { ok: true, already: rec.status };
    /* 协作取消：把 maxWallMs 打到极小，下次检查时就退 */
    rec.maxWallMs = 1;
    rec.cancelling = true;
    return { ok: true, run_id: id, cancelling: true };
  }

  /* ---------------- 挂到 capability 表 ---------------- */
  const capabilities = {
    run_agent: {
      desc: '跑一次完整 Agent 闭环（Brain 决策 + 沙箱执行）。异步：立刻回 ack，结果走 reply，每步走 evt。',
      params: {
        task: 'string, 任务描述（≤2000 字符）',
        maxSteps: 'number?, 最多几步（≤12）',
        maxWallMs: 'number?, 总墙钟上限（≤120000）',
      },
      run: runAgent,
    },
    agent_log: {
      desc: '拉取某次 Agent 运行的审计日志（含每步 thought/tool/obs）。',
      params: { run_id: 'string', since: 'number?' },
      run: agentLog,
    },
    agent_cancel: {
      desc: '请求取消一次运行（协作式）。',
      params: { run_id: 'string' },
      run: agentCancel,
    },
  };

  return {
    enabled: true,
    capabilities,
    info: () => ({
      enabled: true,
      limits: AGENT_LIMITS,
      rootfs,
      running: [...runs.values()].filter(r => r.status === 'running').length,
      total_runs: runs.size,
      recent: [...runs.entries()].slice(-5).map(([id, r]) => ({
        run_id: id, status: r.status, step: r.step, task: r.task.slice(0, 40),
      })),
    }),
  };
}

module.exports = { createAgentBridge, AGENT_LIMITS };
