# 外部沙箱：PulseOS 调度重用环境，PulseScript 保持纯净

> **方案 A**：不在 PulseScript 里开 `spawn`/`exec`，而是写 `shell/sandbox.js` 由 PulseOS 调用。

---

## 一、为什么不开 RCE

先看这条实测——`compile.js` 原来的 `id` 分支有 `return e.v` 兜底，等于把宿主作用域交给调用方：

```
require("fs").readFileSync("/etc/passwd")   → root:x:0:0:root:/root:/bin/bash
require("child_process").execSync("id")     → uid=0(root)
gateway.js 默认 listen('0.0.0.0') + HMAC 空
```

**这三条同时成立 = 公网无鉴权 RCE，uid=0。**

所以「为了跑 Ubuntu 而在 PulseScript 里加 `spawn_env`」这条路**直接堵死**。PulseScript 的纯净性是整个架构的护城河，不能为了 100ms 打开它。

---

## 二、PulseScript 的补丁（11 轮攻击 11 拦）

| 攻击 | 结果 |
|---|---|
| `require("fs")` | ✓ 编译期拒绝 |
| 读 `/etc/passwd` | ✓ 编译期拒绝 |
| `execSync("id")` | ✓ 编译期拒绝 |
| `process` / `globalThis` / `module` / `__dirname` | ✓ 编译期拒绝 |
| `eval` / `Function` | ✓ 编译期拒绝 |
| `len.constructor` / `__proto__` / `prototype` | ✓ 编译期拒绝（原型链） |
| `len["constructor"]` | ✓ 语法守卫拒绝 |

**三层防御：**

1. **标识符白名单** —— 只允许状态字段 / 参数 / `let` 变量 / 内置函数，其他编译期报错
2. **成员访问黑名单** —— `constructor` `__proto__` `prototype` `call` `apply` `bind` `caller` `arguments`
3. **产物顶部遮盖** —— `const require = undefined; const process = undefined; ...`（即使编译器被绕过）

解释器路径同样加了守卫（不只是编译器）。

---

## 三、沙箱实测数据

**环境**：`/workspace/_cx/rootfs-ubuntu/root`（Ubuntu 24.04.5，435MB）

| 操作 | 耗时 |
|---|---|
| `chroot /bin/true`（纯拉起） | **27 ~ 32 ms** |
| `chroot python3`（拉起+启动） | **90 ~ 140 ms** |
| 端到端（拉起→算→取结果→销毁） | **100 ms** |
| 宿主直接 `python3`（对照） | 142 ms |
| 一次性 `apt install python3` | 54 秒 |

**比宿主直接跑 python 还快一点**（少了 shell 包装）。

### 11 个任务并发（模拟 11 个 agent）

```
sha256   x          ✓  138.0ms
sha256   y          ✓  129.6ms
primes   500        ✓   96.9ms
primes   1000       ✓   91.6ms
primes   2000       ✓   90.9ms
run      2**64      ✓   99.9ms
run      1000^1000  ✓  164.7ms
run      Σi²        ✓  192.9ms
sha256   a          ✓  191.1ms
sha256   b          ✓  207.8ms
run      done       ✓  176.6ms
──────────────────────────────
合计墙钟 1582ms   11/11 成功
```

跑完沙箱统计：`runs: 12  failures: 0  p50: 134ms  p95: 201ms` — **零失败**。

---

## 四、安全边界（实测，不是宣称）

| 测试 | 结果 | 说明 |
|---|---|---|
| 读宿主 `/workspace` | ✅ 拦 | chroot 隔离，宿主路径不可见 |
| 读 `/etc/passwd` | ⚠️ 能读 | **但读的是 rootfs 自己的**（md5 与宿主不同） |
| 写 `/tmp/ESCAPE.txt` | ⚠️ 能写 | **写在 rootfs 的 /tmp**，宿主 `/tmp` 干净 |
| 看 `/proc` | ✅ 拦 | 未挂 /proc（Android seccomp 禁止 mount 后 chroot） |
| 访问 `127.0.0.1` | ✅ 拦 | 宿主 22 端口不可达 |
| **出网 TCP** | ✅ **已封** | Python 层守卫覆盖 `socket` / `urllib` / `http.client` |
| 路径逃逸 `../../` | ✅ 拦 | `_inner()` 检查 `rootfs` 前缀 |

**唯一弱点：`allowNet: true` 会出网**（默认 false）。因为 Android 无 `iptables`，网络只能在 Python 层拦，不是内核层。

---

## 五、跨边界因果（这才叫「接上 OS」）

```
PulseScript:  on "hash"(text) { emit "sha256" { text: text } }
                        ↓  PulseOS 因果派发器
NativeKernel: pysandbox.sha256   ← JS 直调，不在 PulseScript 里
                        ↓  chroot + python3
                   2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
```

实测：`j → pysandbox.sha256  ✓ 与标准值一致  294.86ms`

**关键：PulseScript 依然纯净 —— 它只能 `emit`，摸不到沙箱对象。**
（尝试 `set x = pysandbox.run("...")` 编译期就被拒）

---

## 六、修掉的两个 bug

### bug 1：`resolveTarget` 不认原生微内核

```
TypeError: Cannot read properties of undefined (reading 'handlers')
```

`resolveTarget` 假设所有内核都有 `k.svc.handlers`，但原生微内核是 `k.handlers`。

修法：加 `_hasOp()` 同时兼容两种形状。

### bug 2：`emit` 传整个 payload，沙箱收到 `[object Object]`

```
sha256("hello") 返回 b28c94b2...
```

因为 `emit "sha256" { text: t }` 派发时传的是 `{text:'hello'}` 整个对象，
handler 里 `String({text:'hello'})` = `"[object Object]"`。

**验证：** `sha256("[object Object]")` = `b28c94b2...` ✓ 完全对上。

修法：`NativeKernel` 加 `paramKeys`，按 key 解包成位置参数。

---

## 七、用法

```js
const pulse = require('./index');
const rt = pulse.create({ root: './state', durability: 'batch' });

/* 挂沙箱（会探测一次 chroot 是否可用） */
const info = rt.attachSandbox('/path/to/rootfs', { allowNet: false });
// { name: 'pysandbox', available: true, probeMs: 27.4 }

/* 直接调 */
rt.invoke('pysandbox', 'sha256', ['hello']);   // → { sha256: '2cf24dba…', ms: 79 }
rt.invoke('pysandbox', 'primes', [2000]);      // → { primes: 303, n: 2000, ms: 88 }
rt.invoke('pysandbox', 'probe', [5]);          // → { p50: 32.1, min: 26.6, max: 64.3 }

/* 或从 PulseScript emit 过去（跨边界因果） */
rt.deploy(`
  service job {
    state { n: int = 0 }
    on "hash"(t) { set n = n + 1 emit "sha256" { text: t } return n }
  }
`);
rt.invoke('job', 'hash', ['hello']);
```

---

## 八、诚实的限制

| 限制 | 原因 | 能不能解决 |
|---|---|---|
| 没有 `/proc` | Android seccomp 禁止 mount 后 chroot | ❌ 换真 Linux 才能 |
| 网络只在 Python 层拦 | 无 `iptables` | ⚠️ 改用 `--network none` 的容器 |
| 每次 100ms | 进程创建 + 解释器启动 | ❌ 物理成本 |
| 435MB 磁盘 | Ubuntu rootfs | ✅ 换 Alpine 可到 64MB |
| 单进程串行 | `spawnSync` 阻塞 | ✅ 换 `spawn` + Promise 可并发 |

**「用完内存归零」这句要打折：** chroot 进程退出后内存确实释放，但 **435MB rootfs 一直在磁盘上**，不会消失。

---

## 九、这套东西的正确定位

```
PulseOS       2µs      调度 / 状态演进 / 因果分发      ← F1 赛车
沙箱          100ms    拉起环境 / 跑重活 / 返回结果     ← 重型卡车
```

**赛车不拉货，卡车不跑圈。** 混在一起两个都会废：
- 让 PulseScript 直接开 shell → 变成有 RCE 的 Docker
- 让沙箱做状态机 → 丢掉 2µs 的调度优势

**边界清晰，各司其职。**
