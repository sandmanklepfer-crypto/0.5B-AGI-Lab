# 剥掉 HTTP：PulseOS 的真实速度

> QPS 359 → 774（剥掉 HTTP），再到 **1,074,651**（剥掉落盘）。
> 每一层剥掉之后，数字都跳一个数量级。

---

## 一、之前的 QPS 359 为什么毫无意义

`server.js` 是 HTTP 包装，`pulse()` 本身只要 2.76ms，剩下 127ms 全在：

```
TCP 握手 + HTTP 头解析 + JSON 双向序列化 + 事件循环排队
```

**那是 Node HTTP 服务器的极限，不是 PulseOS 的能力。**

---

## 二、剥第一层：HTTP

新增 `index.js` —— 干净的库入口：

```js
const pulse = require('pulseos');
const rt = pulse.create({ dir: './state' });

rt.deploy(`
  service counter {
    state { n: int = 0 }
    on "inc"(x) { set n = n + x return n }
  }
`);

const r = rt.invoke('counter', 'inc', [5]);
// { ok: true, result: 5, ms: 0.42, stateBytes: 7 }
```

**零网络。** HTTP 保留为调试接口，不是主路径。

### 实测对比（同 50 内核 / 500 次调用）

| 指标 | 直连（库） | HTTP | 倍数 |
|---|---|---|---|
| **p50** | **1.182 ms** | 3.338 ms | HTTP 慢 2.8x |
| **p95** | **2.024 ms** | 4.607 ms | HTTP 慢 2.3x |
| **QPS** | **774** | 283 | **2.7x 快** |
| 部署 50 个 | 202 ms | 2395 ms | **11.9x 快** |

**HTTP 那层吃掉了 63.5% 的时间。**

交叉验证：50 个内核全部一致 ✓

---

## 三、剥第二层：落盘（真正的瓶颈）

QPS 774 还是慢。拆开看才发现——**问题不在 HTTP，在持久化**。

| 操作 | p50 | p95 | QPS |
|---|---|---|---|
| **纯计算**（`mod.run`，不落盘） | **417 ns** | 833 ns | **1,074,651** |
| 计算 + 落盘（`rt.invoke`） | 1.163 ms | 2.138 ms | 787 |

```
纯计算 p50 = 417 纳秒
落盘后 p50 = 1.163 毫秒
          = 计算成本的 2,790 倍
```

### 这个数字意味着什么

**PulseScript 编译出的代码执行一次只要 0.4 微秒。**
**但每次 invoke 都做了：**

```
① JSON.stringify(state)          ← 序列化
② zlib.deflateRawSync(level 9)   ← 最高压缩级别
③ fs.writeFileSync               ← 同步写盘
```

**这三件事加起来 1.16ms，是计算本身的 2800 倍。**

### 对比 Node 原生

```
空函数调用          ~10 ns
JSON.stringify 小对象  ~1 µs
zlib 压缩 100 字节     ~50 µs
fs.writeFileSync 小文件 ~100 µs
```

**我们测出的 417ns 说明编译产物已经接近 V8 的原生函数调用速度。**

---

## 四、三层对比总表

```
┌──────────────────────────────────────────────────┐
│  QPS 359     HTTP 包装                             │
│  ─────────────────────────────────────────────   │
│  QPS 774     剥掉 HTTP（库直调）      2.2x         │
│  ─────────────────────────────────────────────   │
│  QPS 1,074,651  剥掉落盘（纯计算）    1,390x       │
└──────────────────────────────────────────────────┘
```

**真正的问题不是形态，是持久化策略。**

---

## 五、正确的下一步

既然瓶颈是「每次调用都落盘」，解法就很清楚：

### 方案 A：批量落盘（推荐）

```
invoke() → 只改内存状态，标脏
         → 每 5~10ms 或每 N 次，统一 WAL 落盘一次
```

**代价**：可能丢最后 N ms 的操作（WAL.md 实测过 group 模式）
**收益**：把 1.16ms 摊到 N 次调用上

预估：

| 批量大小 | 单次摊销 | 预估 QPS |
|---|---|---|
| 1（现在） | 1.16 ms | 787 |
| 10 | 0.116 ms | ~8,600 |
| 100 | 0.012 ms | ~85,000 |
| 不落盘 | 417 ns | 1,074,651 |

### 方案 B：异步落盘

```
invoke() → 改内存，返回
         → 后台 fsync（不阻塞调用方）
```

**代价**：进程崩溃丢未落盘的
**收益**：调用方完全不等 IO

### 方案 C：只落 WAL 不落全量（已经有）

`wal.js` 已经实现了——记录操作而非状态。但 `index.js` 的 `invoke()` 还在用 `k._save()`（全量状态写盘）。

**所以最直接的优化是：把 `index.js` 的落盘换成 WAL。**

---

## 六、必须说清的边界

### 1,074,651 QPS 是怎么得来的

```
100000 次循环，纯 mod.run()，同一进程，无 IO
lat1 收集每次的纳秒级耗时
```

**这不是"能扛 100 万并发"**，是"单线程单次调用只要 417 纳秒"。

```
1 / 417ns = 2,398,081 次/秒（理论）
实测 1,074,651（含循环开销、数组 push）
```

### 仍然没证明的

```
✗ 多核并行（Node 单线程）
✗ 真实网络下的并发（那要看 HTTP 那层）
✗ 50 个大模型 API 并发（没有聊天模型 key）
✗ 真实业务负载（现在测的是最小 handler）
```

### 这个 QPS 也没有实际意义

**因为没有任何真实系统愿意为了一次计算丢掉持久化。**

真正该追求的是：**在保证不丢数据的前提下，把 QPS 从 787 提到 1 万以上。**

而那个路径很清楚：**批量落盘**。

---

## 七、代码位置

```
index.js              ★ 新增：库入口
bench_direct.js       ★ 新增：直连 vs HTTP 对比
server.js                HTTP 调试接口（不是主路径）
```

### 用法

```js
// 进程内直调（快）
const pulse = require('./index');
const rt = pulse.create({ dir: './state' });
const r = rt.invoke('counter', 'inc', [1]);

// 远程/调试（慢，但能跨进程）
// node shell/server.js  →  POST /api/pulse
```

---

## 八、复现

```bash
# 直连 vs HTTP
KERNELS=50 REQ=500 node bench_direct.js

# 纯计算（这个在 bench_direct.js 内部，也可以单独跑）
node -e "
const pulse=require('./index');
const rt=pulse.create({root:'/tmp/x'});
rt.deploy('service c { state { n: int = 0 } on \"inc\" { set n = n + 1 } }');
const k=rt.shell.kernels.get('c'), mod=rt._cache.get('c');
let st=k.state, t=process.hrtime.bigint();
for(let i=0;i<100000;i++) st=mod.run('inc',[],st).state;
console.log('纯计算 QPS:', (1e5/(Number(process.hrtime.bigint()-t)/1e6)*1000).toFixed(0));
"
```
