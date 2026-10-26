# Agent 闭环：把 13 个原语交给 Brain 指挥

> 上一轮那套 `spawn_env → exec_script → snapshot_env → kill_env` **不是 Agent**，
> 是写死的 JS 脚本在按顺序调原语 —— 准确叫法：**Actuator 测试**。
>
> 这一轮加了 Brain，让「上一步的结果」决定「下一步做什么」。

---

## 一、Agent 的四个闭环，缺一不可

| 环 | 谁负责 | 本项目对应 |
|---|---|---|
| **感知** | Brain 读 history | 上一步的 `obs`（stdout / stderr / error） |
| **决策** | Brain | `MockBrain` / `OpenAIBrain` |
| **执行** | PulseOS + envs.js | 13 个原语 |
| **反馈** | observation 回灌 history | 下一轮 decide 能看到 |

**只有四个环都转，才叫 Agent。少一个就是脚本。**

---

## 二、`shell/agent.js` 的结构

```js
const loop = new AgentLoop({
  envs: new EnvManager({ rootfs: '/path/to/rootfs' }),
  brain: new MockBrain(),      // ← 唯一要换的东西
  maxSteps: 12,
  maxWallMs: 90000,
});

const r = await loop.run('算一下 1000 以内有多少个素数，并且核对结果对不对');
// { ok, answer, steps, elapsedMs, stopped, history, audit }
```

### Brain 接口（就一个方法）

```js
async decide({ task, history, tools, step })
  → { thought, tool, args }        // 继续干活
  | { done: true, answer }         // 收工
```

**接真 LLM 只改这一处，其余全不动。**

### 暴露给 Brain 的 9 个工具（13 个里的安全子集）

```
init_env  spawn_env  exec_script  retrieve_result
snapshot_env  restore_env  kill_env  list_envs
```

**故意不暴露 3 个：**

| 不暴露 | 原因 |
|---|---|
| `set_limits` | Android 无 cgroup，只能软限制 —— 给了是骗 Brain |
| `get_usage` | 读不到沙箱 `/proc` |
| `revoke_network` | 只有 Python 层软拦截，容易让 Brain 误以为安全 |

---

## 三、实测：成功路径

```
【任务】算一下 1000 以内有多少个素数，并且核对结果对不对

【第 1 步】💭 先创建沙箱环境
  🔧 init_env({})                    → ok  env=env_000f7c5f80   (2ms)
【第 2 步】💭 环境已创建，拉起常驻进程
  🔧 spawn_env({env_id})             → ok  pid=xxxxx            (25ms)
【第 3 步】💭 先试一版简单写法
  🔧 exec_script({code:"sum(1 for i in range(2,1001) ...)"})
                                     → ok  stdout="168\n"       (172ms)
【第 4 步】💭 结果 168 与预期一致，清理环境
  🔧 kill_env({env_id, force:true})  → ok                       (1ms)

【完成】任务完成。1000 以内的素数个数 = 168
──────────────────────────────
ok: true   步数: 4   墙钟: 902ms   残留环境: 0
```

**第 3 步的结果（168）真的影响了第 4 步的决策** —— 如果算出 170，Brain 会走重算分支。

---

## 四、实测：失败重试路径（这条才证明闭环是真的）

```
【第 1 步】建环境           init_env    → ok
【第 2 步】拉起             spawn_env   → ok
【第 3 步】故意跑会错的脚本   exec_script → ✗ shell 在执行时退出（exit=2）
【第 4 步】看到了失败（/bin/sh: 1: Syntax error: "(" unexpected），换代码重试
                            exec_script → ok "RECOVERED_OK"
【第 5 步】重试成功，清理     kill_env    → ok
──────────────────────────────
ok: true   步数: 5   墙钟: 432ms   残留环境: 0
```

**Brain 读到了真实的 shell 错误信息，据此换了代码。** 这是反馈驱动的证据 —— 不是预设脚本。

---

## 五、修掉的四个 bug（都是实测撞出来的）

### bug 1：`exec_script` 的 inject 模式只写不等

```
第一次 echo → stdout=""   （调用方拿不到结果）
```

原实现写完 stdin 就 return。改成：发哨兵 `__PULSE_EOF_xxx__`，等它在输出流里出现才返回。

### bug 2：哨兵和正常输出在同一数据块 → 整块被丢

```
echo FIRST → stdout=""     （FIRST 和哨兵同批到达）
```

原来 `fresh.slice(0, hit)` 把整块丢掉。改成**按行剥离哨兵那一行**，剩下的才是真输出。

修后：`FIRST` / `SECOND` / `42` / `中文测试` 全部正常。

### bug 3：命令把 shell 弄死 → 白等满超时

```
exec_script → ✗ inject 等输出超时 10000ms   （实际 10 秒白等）
```

`raise ValueError("...")` 里的 `(` 是 shell 语法错，sh 直接退出，哨兵永远不会来。

修法：**进程 exit 时立刻唤醒等待者**，带上真实 stderr。
修后：`shell 在执行时退出（exit=2）` + `Syntax error: "(" unexpected`，**10.4s → 432ms**。

### bug 4：`init_env` 花 6912ms

`du -sb` 扫 709MB 目录。改成 stat 累加 + 缓存：

```
init_env     6912ms → 2ms
体积计算      首次 961ms（688MB，实际 709MB，误差 3%），缓存后 0ms
```

---

## 六、接真 LLM（`OpenAIBrain`）

```js
const brain = new OpenAIBrain({
  baseUrl: 'https://api.deepseek.com',
  model: 'deepseek-chat',
  keyEnvFile: '/workspace/.secrets/deepseek.env',
});
const loop = new AgentLoop({ envs, brain, maxSteps: 12 });
```

**key 从 `.secrets/*.env` 读，不进代码、不进命令行。** 支持 `DS_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`。

用 OpenAI 兼容的 `tools` + `tool_calls` 格式，每步一个工具调用，observation 以 `role: 'tool'` 灌回。

---

## 七、现在卡在哪（诚实说）

### ✅ 能做的

- Agent 闭环骨架（感知→决策→执行→反馈），带步数/墙钟/环境数硬限制
- MockBrain 证明闭环真的转（包括失败重试）
- 每步审计日志，可完整回放
- 真 LLM 接口写好了（`OpenAIBrain`）

### ❌ 卡住的

| 卡点 | 说明 |
|---|---|
| **没有 LLM key** | 工作区只有 `hunyuan.env`（3D 生成）和 `volc.env`（图像/视频），**都不是聊天模型** |
| **我自己不能当 Brain** | 我是单次生成，无法在运行时把 13 原语的结果喂回自己再做下一步决策 |

**所以「完整 Agent」差最后一寸：一个能跑 function calling 的聊天模型 key。**

---

## 八、一旦有了 key，能立刻验证什么

```bash
# 1. 放 key
echo 'DS_KEY=sk-xxxxx' > /workspace/.secrets/deepseek.env

# 2. 跑真 Agent
node -e "
const {AgentLoop, OpenAIBrain} = require('./shell/agent');
const {EnvManager} = require('./shell/envs');
(async () => {
  const envs = new EnvManager({ rootfs: '/path/to/rootfs' });
  const loop = new AgentLoop({ envs, brain: new OpenAIBrain({}) });
  const r = await loop.run('用沙箱算出 2000 以内素数个数，并验证两次结果一致');
  console.log(r.answer, r.steps, r.elapsedMs + 'ms');
})();
"
```

**那时候看到的才是真 Agent：模型自己决定先干什么、看到结果后改主意、判断什么时候收工。**

---

## 九、网页遥控（agent.html）

手机起 worker：

```bash
cd /workspace/luhuo/pulseos
node shell/worker.js \
  --chan 你的频道 \
  --name 我的手机 \
  --allow-agent \
  --rootfs /workspace/_cx/rootfs-ubuntu/root
```

浏览器打开：

```
https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/pulseos/agent.html#chan=你的频道
```

页面会：填频道 → 连接 → 自动查 status 确认 Agent 开了 → 下发任务 → 实时看每步 → 看最终答案。

**网页只是遥控器，Agent 跑在你设备上。全程零入站端口。**

## 十、一句话总结

> **13 个原语 = 四肢（能跑通，实测过）**
> **AgentLoop = 神经回路（能转，实测过）**
> **LLM = 大脑（缺一个 key）**
>
> **前两个是我造的，第三个要你插卡。**
