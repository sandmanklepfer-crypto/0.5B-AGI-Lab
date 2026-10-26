# 状态迁移与复制

> 迁移解决「搬到别处」，复制解决「两边都有」。
> 这两个是「算力漫游」和「高可用」各自的最小实现。

---

## 一、两者区别

| | 迁移 | 复制 |
|---|---|---|
| 目的 | 把微内核从 A 搬到 B | A 和 B 都有，A 主 B 从 |
| 所有权 | **转移**（A 没了） | **共享**（A 主，B 读） |
| 时机 | 一次性 | 持续 |
| 场景 | 手机换电脑跑 | 读分散、写集中 |
| 难度 | 中 | 高（顺序 + 冲突 + 落后） |

---

## 二、迁移：四阶段协议

**为什么不能只做文件传输** —— 三个必须解决的问题：

```
① 搬运期间两边都在写   → 需要冻结窗口
② 搬到一半失败         → 需要回滚
③ 搬完 A 上还留着      → 会分叉
```

### 协议

```
freeze(A) → dump(A) → load(B) → verify(B) → commit
   │                                            │
   └────────── 失败则 rollback ◄────────────────┘
```

| 阶段 | 做什么 | 失败怎么办 |
|---|---|---|
| `freeze` | A 上拒绝对该服务的写 | 直接失败，无需回滚 |
| `dump` | 取状态箱 + 源码 | 回滚 unfreeze |
| `load` | B 上注册服务 + 灌状态 | 回滚 unfreeze |
| `verify` | 查 B 的 `/api/node` 与 `/api/state` | 回滚 drop(B) + unfreeze |
| `drop` | 删 A 上的服务 | 已成功，报错但不回滚 |

### 实测

```
=== 在 A 上建立状态 ===
  A 上: {"n":3,"owner":"手机"}

=== 迁移 A → B ===
  ✓ freeze             16ms  {"node":"A"}
  ✓ dump               34ms  {"boxBytes":26,"hasSource":true}
  ✓ load               95ms  {"node":"B"}
  ✓ verify            120ms  {"registered":true,"stateBytes":24}
  ✓ drop              133ms  {"node":"A","dropped":true}
  → 成功  134ms

=== 验证状态搬过去了 ===
  B 上: {"n":3,"owner":"手机"}      ← 完整

=== 验证 A 上已经没了 ===
  A 的服务列表: (空)                 ← 干净

=== 在 B 上继续写 ===
  B 上: {"n":4,"owner":"手机"}

=== 迁回 A ===
  ✓ 成功  65ms
  A 上: {"n":4,"owner":"手机"}      ← 数据没丢
```

**往返 134ms + 65ms，状态零丢失。**

### 用法

```bash
node shell/migrate.js \
  --from A:127.0.0.1:8921 \
  --to   B:127.0.0.1:8922 \
  --service counter
```

```js
const { migrate, MigrationLog } = require('./shell/migrate');
const r = await migrate({
  from: { name: 'A', host: '127.0.0.1', port: 8921 },
  to:   { name: 'B', host: '127.0.0.1', port: 8922 },
  service: 'counter',
  log: new MigrationLog('/tmp/migrations.json'),
  verify: true,
  keepSource: false,
});
```

---

## 三、复制：单向主从 + 全量重传

### 为什么是「单向主从」

| 问题 | 本实现的答案 |
|---|---|
| **顺序** | 状态有因果，`n=5` 必须排在 `n=4` 之后 → 单调递增 `seq` |
| **冲突**（脑裂） | **只允许主写，从只读**。唯一不引入共识算法还能保证正确的方案 |
| **落后** | 从节点掉线回来后 → **全量重传** |

### 明确不承诺

```
❌ 多主写入（需 Paxos/Raft，工程量 ×5）
❌ 增量日志同步（需要 WAL）
❌ 自动选主（需心跳 + 任期 + 投票）
```

**定位：撑住「读分散、写集中」，不承诺多主。**

### 实测

```
=== 1. 主节点写 5 次 ===
  inc → 1  seq=1  leader=leader
  inc → 5  seq=5

=== 2. 同步到从节点 ===
  seq=5  52ms  整体=✓
    follower  ok=true  stateBytes=18

=== 3. 一致性校验 ===
  leader 有状态: true
    follower  hasState=true  identical=true
  全部一致: ✓

=== 4. 从从节点读 ===
  from=follower  isLeader=false  → {"n":5,"owner":""}

=== 5. 主再写 3 次（从会落后）===
  从节点读 → {"n":5,"owner":""}   ← 落后
  主节点读 → {"n":8,"owner":""}

=== 6. 再同步补齐 ===
  ✓  40ms
  全部一致: ✓
  从节点读 → {"n":8,"owner":""}
```

### 用法

```js
const { ReplicaSet } = require('./shell/replicate');

const rs = new ReplicaSet({
  service: 'counter',
  leader:    { name: 'leader',   host: '127.0.0.1', port: 8931 },
  followers: [{ name: 'follower', host: '127.0.0.1', port: 8932 }],
});

await rs.write('inc', []);                      // 主写，seq++
await rs.sync();                                // 全量推到从节点
const v = await rs.verify();                    // 一致性检查
await rs.read('get', [], { from: 'follower' }); // 从节点读
```

---

## 四、踩到的三个 bug

### bug 1：验证逻辑太脆弱

第一版用「发一个假操作 `__probe__`，看报什么错」判断服务是否注册。

**结果：`目标上服务未就绪: 未知`** —— 假操作的错误信息匹配不上正则，误判失败，触发回滚。

**但迁移其实成功了**（B 上确实有数据）。

**修法**：直接查 `/api/node` 看服务在不在，再查 `/api/state` 看状态字节数。

> **教训：验证要用「查事实」，不要用「看报错猜」。**

### bug 2：没实现 `DELETE /api/service`

迁移的 `drop` 阶段要删源节点，但节点根本不支持 —— 所以 A 上的服务一直留着，会导致**双写分叉**。

**修法**：补上 DELETE 路由。

### bug 3：`restore` 灌状态被覆盖（最严重）

```js
const added = sh.registerAll(b.source || '');   // ← 新建 kernel，状态是初始值
const k = sh.kernels.get(b.service);
if (b.state) { k.state = b.state; k._save(); }  // ← 必须在新建之后
```

顺序写反就导致**迁移后状态是空的**。表现：迁回 A 后 `A 上: undefined`。

> **教训：注册和灌状态是两步，顺序错了数据就没了。**

---

## 五、现在的能力边界

| 能力 | 状态 |
|---|---|
| 跨端调用透明 | ✅ |
| 节点故障转移 | ✅ |
| **状态迁移** | ✅ **刚完成** |
| **主从复制** | ✅ **刚完成** |
| 多主复制 | ❌ |
| 自动选主 | ❌ |
| 增量同步 | ❌ |

### 能做的

```js
await migrate({ from: phone, to: laptop, service: 'counter' });  // 搬家
await rs.read('get', [], { from: 'follower' });                  // 读分散
await migrate({ from: follower, to: spare, service: 'counter' }); // 手工提升从
```

### 还做不到的

```
❌ 主挂了自动切（需要选主）
❌ 两边都能写还不冲突（需要共识）
❌ 只传增量（需要 WAL）
```

---

## 六、一个诚实的判断

**迁移的价值比复制大。**

```
迁移：134ms 搬一次，用户感知不到     ← 体验直接提升
复制：持续同步 + 处理落后和冲突      ← 复杂度换可靠性
```

而可靠性这一块，**一台真服务器（¥30/月）比自己做复制便宜得多**。

**所以：迁移值得做；复制适合「读多写少」的特定场景，不建议为了复制而复制。**
