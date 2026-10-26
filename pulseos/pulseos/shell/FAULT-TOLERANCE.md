# 故障转移与熔断 —— 让多节点不再是脆弱玩具

> 上一版最痛的问题：**节点一挂，调用就失败。**
> 这一版补上了三件事。

---

## 一、三个新增机制

```
① 健康检查    每 N 秒 ping 所有节点，离线/上线自动维护
② 故障转移    同名服务在多个节点时，主节点挂了自动切备用
③ 熔断        连续失败到阈值就"打开"，短时间内直接拒绝
               避免每次调用都等一次连接超时
```

### 为什么需要熔断

没有熔断时，节点挂了之后每次调用都要等：

```
调用 → connect ECONNREFUSED（快）
     → 但如果节点是"黑洞"（SYN 不响应），要等 8 秒超时
     → 10 次调用 = 80 秒
```

**熔断把"等 8 秒"变成"立即返回错误"**，整个系统不会被一个死节点拖垮。

---

## 二、实测

### 故障转移

```
=== 1. 正常：prio 0 的 nodeA ===
  inc → 1 | 节点 nodeA | 故障转移 false

=== 2. 杀掉 nodeA ===

=== 3. 自动故障转移 ===
  inc → 1 | 节点 nodeB | 故障转移 true
  尝试序列: nodeA → nodeB
     nodeA ok=false 节点 nodeA 不可达: connect ECONNREFUSED 127.0.0.1:8911
     nodeB ok=true
  get → {"n":1,"who":"B机"} | 节点 nodeB
```

**注意 `who:"B机"`** —— 它确实切到了 nodeB 的独立状态。

### 熔断打开

```
初始:     nodeA:closed  nodeB:closed   节点在线 2/2
探测1:    nodeA:closed  nodeB:closed   节点在线 1/2
探测2:    nodeA:closed  nodeB:closed   节点在线 1/2
探测3:    nodeA:open    nodeB:closed   节点在线 1/2   ← 第 3 次打开
探测4:    nodeA:open    nodeB:closed   节点在线 1/2
```

**阈值 3 次，第 3 次探测时打开。**

### 稳定后的性能

```
第1次 → 节点 nodeB | 成功 true | 耗时 143ms   ← 含失败重试
第2次 → 节点 nodeB | 成功 true | 耗时  14ms   ← 直接走 B
第3次 → 节点 nodeB | 成功 true | 耗时   8ms
```

**熔断打开后，不再尝试死节点，延迟从 143ms 降到 8ms。**

### 汇总

```
节点 1/2 在线
调用 8 | 成功 8 | 故障转移 1 | 失败 0
  nodeA  online=false  fail=1
  nodeB  online=true   fail=0
服务 counter 副本 2 在线 1 → nodeA○ nodeB●
```

---

## 三、熔断器状态机

```
        ┌──────────┐
        │  closed  │  正常，放行
        └────┬─────┘
             │ 连续失败 ≥ 3
             ▼
        ┌──────────┐
        │   open   │  拒绝一切，立即返回错误
        └────┬─────┘
             │ 超过 openMs（默认 10s）
             ▼
        ┌──────────┐
        │ halfOpen │  放一个探针过去
        └────┬─────┘
        成功 │   │ 失败
             ▼   ▼
        closed  open
```

**关键：`halfOpen` 只放一个探针。** 如果放多个，节点刚恢复就被打垮。

---

## 四、优先级：谁先被尝试

```js
ds.addNode('nodeA', '127.0.0.1', 8911, { priority: 0 });   // 主
ds.addNode('nodeB', '127.0.0.1', 8912, { priority: 1 });   // 备
```

排序规则：

```
priority 数字小 → 先试
+ 不健康节点 +1000（自动沉底）
+ 手动 setPrefer() 可覆盖
```

### 手动指定

```js
ds.setPrefer('counter', 'nodeB');   // 强制走 B
await ds.call('counter', 'inc', []);

// 或者单次指定
await ds.call('counter', 'inc', [], { node: 'nodeA' });
```

---

## 五、重试策略

```js
new RemoteKernel({ ..., retry: 1 });
```

- `retry: 0` → 不重试，失败即失败（延迟敏感）
- `retry: 1` → 重试 1 次（默认，容忍瞬时抖动）
- **退避**：第 n 次重试等 `120 × n` 毫秒

**注意：重试针对"瞬时抖动"，故障转移针对"节点真挂了"。两者不重复——重试在 RemoteKernel 内，故障转移在 DistributedShell。**

---

## 六、自动健康检查

```js
const ds = new DistributedShell({ healthMs: 15000 });
ds.addNode('nodeA', ...);
ds.startHealthLoop();      // 后台每 15 秒 ping 一次
```

或者命令行：

```bash
node shell/dist.js --node nodeA=127.0.0.1:8911 --node nodeB=127.0.0.1:8912 --watch 5
```

输出（每 15 秒刷新）：

```
[14:32:01] ═══════════════════════════════
  ● nodeA      1 个微内核  counter
  ○ nodeB      1 个微内核  离线
  ─────────────────────────────────
  节点 1/2 在线   微内核 2   调用 8 (成功 8, 故障转移 1, 失败 0)
```

---

## 七、修复的三个 bug（记下来）

### bug 1：节点表没同步

`probeAll()` 标记 `online=false`，但调用失败时没更新节点表，导致 `overview()` 仍显示在线。

**修法**：`_invoke()` 里失败时同步 `n.failCount++; n.online = false;`

### bug 2：熔断器状态没传到副本

`RemoteKernel.info()` 返回了 `breaker: {...}`，但 `dist.js` 读的是 `x.breaker.state` —— **字段名不一致**。

**修法**：`info()` 额外返回 `breakerState: this.breaker.state`，dist 直接读它。

### bug 3：`probeAll()` 不通知熔断器（最隐蔽）

节点挂了，`probeAll()` 把 `n.online=false`，但**没调用 `rk.breaker.fail()`**。

结果：熔断器一直是 `closed`，永远不会打开。

**修法**：探测失败时给它名下所有 `RemoteKernel` 各记一次失败。

> **这个 bug 只有实测才暴露** —— 单测 `Breaker` 类永远发现不了，因为它逻辑正确；
> 是"谁来调用它"这一层漏了。

---

## 八、还缺什么

| 缺 | 影响 | 难度 |
|---|---|---|
| **自动重试队列** | 现在失败就是失败，不会稍后重试 | 中 |
| **状态复制** | 节点 B 的状态是空的，不是 A 的副本 | **高**（见下） |
| **被动探活** | 现在靠主动 ping，不能从异常中学习 | 低 |
| **半开限流** | halfOpen 只放 1 个，高流量时会瞬间又打垮 | 中 |

### 最重要的一条：这不是"高可用"，是"故障转移"

```
现在：nodeA 挂了 → 切到 nodeB → nodeB 的状态是它自己的（空的）
真正的高可用：nodeA 挂了 → 切到 nodeB → nodeB 有 nodeA 的状态
```

**中间差的是「状态复制」—— 而那是下一个里程碑。**

现在的定位是：**服务可切换，状态不共享。** 对"无状态服务"够用，对"有状态服务"只是降级。

---

## 九、用法

```js
const { DistributedShell } = require('./shell/dist');

const ds = new DistributedShell({ root: './state' });

ds.addNode('phone',  '192.168.1.10', 8901, { priority: 0 });
ds.addNode('laptop', '192.168.1.11', 8902, { priority: 1 });
ds.addNode('vps',    '1.2.3.4',      8903, { priority: 2 });

ds.startHealthLoop();       // 后台每 15s 探活

const r = await ds.call('counter', 'inc', []);
// { ok: true, result: 5, node: 'phone', failover: false }

await ds.stopHealthLoop();
```
