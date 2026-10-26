# 批量落盘：QPS 1051 → 62,232

> 上一轮发现真瓶颈：落盘是计算的 2,790 倍（417ns → 1.16ms）。
> 这一轮修掉了。**快 59 倍，远超 1 万的目标。**

---

## 一、问题回顾

```
纯计算          417 ns
计算 + 全量落盘  1,163 ns    ← 落盘占了 64%
```

每次 `invoke()` 都做三件事：

```
JSON.stringify(state) + zlib.deflateRawSync(level 9) + fs.writeFileSync
```

**这三件事 828µs，而计算本身只要 1µs。**

---

## 二、解法：三种持久化模式

```js
pulse.create({ root: './state', durability: 'batch' })
```

| 模式 | 行为 | 适用 |
|---|---|---|
| **`sync`** | 每次 invoke 立即落盘 | 不可丢的操作（记账、订单） |
| **`batch`**（默认） | 攒 64 次 或 20ms 再落盘 | 大多数业务 |
| **`none`** | 完全不落盘 | 纯计算、可重算的缓存 |

### 关键实现细节

```js
// 不能只靠 setInterval —— 同步死循环会饿死它（WAL.md 踩过）
if (this._pending >= this.batchSize) {
  this._flush();                    // 同步检查
}
```

`setInterval` 只作后备。

---

## 三、实测（20,000 次 invoke）

| 模式 | p50 | p95 | p99 | QPS |
|---|---|---|---|---|
| `sync` | 828 µs | 1.65 ms | 2.36 ms | **1,051** |
| **`batch`** | **1.1 µs** | **2.0 µs** | 784 µs | **62,232** |
| `none` | 1.2 µs | 3.9 µs | 6.0 µs | 388,736 |

```
sync → batch:   QPS 1,051 → 62,232    快 59.2x
sync → none:    QPS 1,051 → 388,736   快 370x
```

### 关于 batch 的 p99 = 784µs

**那是撞上批量落盘的那一刻。**

这正是 `WAL.md` 里发现的「长尾」规律：

> **均匀的慢（sync，每条 828µs）比偶尔的卡（batch，p99 784µs）更糟。**

因为 batch 的 p50 只要 1.1µs，**99% 的请求几乎零开销**，只有 1% 需要等落盘。

---

## 四、正确性验证（这是最重要的）

速度快但丢数据 = 废物。所以测了三种情形：

| 情形 | 结果 |
|---|---|
| **① `flush()` 后正常关闭** | 落盘 1000 → 重开 1000   **✓ 零丢失** |
| **② 不 flush 直接断电** | 落盘 1000 → 重开 960   **丢 40 次** |

**40 < batchSize(64)，完全符合预期。**

### 语义承诺

```
batch 模式：
  · 调 flush()        → 不丢任何已确认的
  · 正常 close()      → 不丢任何已确认的
  · 进程被 kill -9    → 丢最后 ≤64 次（或 ≤20ms）内的
```

**这是明确的、可预期的，不是"可能丢"。**

---

## 五、修复的 bug：重开后服务全丢

第一次测试三种模式，重开后 `n = undefined`，服务列表是空的。

**原因**：`index.js` 的 `PulseOS` 构造函数只新建 `AggregatedShell`，**没有从磁盘恢复已部署的服务**。

`server.js` 早就修过这个问题（`_src` 源码持久化 + 启动扫描），但 `index.js` 漏了。

**修法**：

```js
// 构造时
this._restore();     // 扫 root/_src/*.pulse，registerAll + 重建编译缓存

// deploy 时
fs.writeFileSync(path.join(srcDir, a.name + '.pulse'), src);

// undeploy 时
fs.unlinkSync(...);
```

修后：`重开服务 = c`，`n = 1000` **✓**

> **这个 bug 只有"新开一个 PulseOS 实例"才会暴露。**
> 单实例内循环 20000 次永远发现不了 —— 和之前那个「重启后 50 个微内核丢失」是同一类错误。

---

## 六、用法

```js
const pulse = require('./index');

// 大多数业务
const rt = pulse.create({ root: './state', durability: 'batch' });

// 记账 / 订单
const rt = pulse.create({ root: './state', durability: 'sync' });

// 纯计算
const rt = pulse.create({ root: './state', durability: 'none' });

rt.invoke('counter', 'inc', [1]);

// 想强一致时
rt.flush();

// 或关闭时（自动 flush）
rt.close();
```

### 网关

```bash
node shell/gateway.js --port 8899 --durability batch --batch 64 --batch-ms 20
```

加了 `POST /flush` 端点，AI 想强一致时可以调。

---

## 七、这解决的是什么

```
之前：开门迎客，外部一并发，硬盘顶不住
现在：62,232 QPS，p50 1.1µs
```

**这才是「可以开门」的状态。**

但要说清边界：

| 已解决 | 未解决 |
|---|---|
| ✅ 落盘不是瓶颈了 | ❌ 落盘仍是全量状态（状态大了会慢） |
| ✅ 三种模式可选 | ❌ 未用 WAL 增量（还在写全量 `.box`） |
| ✅ flush 保证不丢 | ❌ 多进程仍要 `lock.js`（index.js 没接） |

**下一步该做**：把 `invoke()` 的落盘从「全量 `.box`」换成「WAL 增量」，那样状态大了也不慢。

但现在这个 62,232 QPS 已经够用了。

---

## 八、复现

```bash
node -e "
const pulse=require('./index');
const fs=require('fs');
const SRC='service c { state { n: int = 0 } on \"inc\" { set n = n + 1 } }';
for (const m of ['sync','batch','none']) {
  const d='/tmp/b-'+m; try{fs.rmSync(d,{recursive:true,force:true})}catch(e){}
  const rt=pulse.create({root:d,durability:m});
  rt.deploy(SRC);
  for(let i=0;i<2000;i++) rt.invoke('c','inc',[]);
  const t=process.hrtime.bigint();
  for(let i=0;i<20000;i++) rt.invoke('c','inc',[]);
  const ms=Number(process.hrtime.bigint()-t)/1e6;
  rt.close();
  console.log(m.padEnd(8), (20000/ms*1000).toFixed(0).padStart(8), 'QPS');
  fs.rmSync(d,{recursive:true,force:true});
}
"
```
