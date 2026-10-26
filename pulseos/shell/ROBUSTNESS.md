# 磁盘满防护 + 多进程文件锁

> 两项「关乎系统能不能活」的补丁。
> 都零依赖，都用原生 API。

---

## 一、磁盘满防护

### 问题

```js
fs.writeSync(...)   // 磁盘满 → throw ENOSPC
fs.fsyncSync(...)   // 硬件故障 → throw EIO
```

**未捕获 = 整个进程挂掉。**

而且更危险的是**静默丢写**：如果吞掉异常继续跑，用户以为存了，其实没有。

### 错误分类

| errno | 含义 | 应对 | 能否重试 |
|---|---|---|---|
| `ENOSPC` / `EDQUOT` | 磁盘满 / 配额超 | **只读降级**（拒绝新写，已有数据可读） | ❌ |
| `EIO` / `EROFS` / `EACCES` | 硬件故障 / 只读挂载 | **故障降级**（拒绝一切写） | ❌ |
| `EMFILE` / `ENFILE` | 句柄耗尽 | 关闲置 fd 再试 | ✅ |
| `EAGAIN` / `EBUSY` | 临时占用 | 重试 | ✅ |

### 降级状态机

```
normal ──ENOSPC──> readonly ──磁盘腾空──> normal
   │                   
   └──EIO────────> fault ──────需重启───> normal
```

**关键：降级后必须让调用方知道。**

```js
const r = store.append('inc', [1]);
if (!r.ok) {
  // r.degraded === 'readonly' | 'fault'
  // r.code === 'ENOSPC'
  // r.error === '磁盘已满（只读降级）[write: ENOSPC]'
}
```

**绝不静默返回 success。**

### 实测：6/6 通过

```
▸ 写入 ENOSPC（磁盘满）
    写入结果          {"ok":false,"degraded":"readonly","code":"ENOSPC"}
    降级状态          {"level":"readonly","reason":"磁盘已满（只读降级）"}
    进程存活          ✓ 没有崩

▸ fsync EIO（硬件故障）
    写入结果          {"ok":false,"degraded":"fault","code":"EIO"}
    降级状态          {"level":"fault","reason":"IO 故障（拒绝全部写入）"}

▸ 磁盘满 → 腾出空间 → 恢复
    失败写入          {"ok":false,"code":"ENOSPC"}
    tryRecover        {"ok":true,"recovered":true}
    恢复后写入         {"ok":true,"seq":6}
    恢复后 n          6

▸ compaction 时快照写失败
    compact           {"ok":false,"error":"快照写入失败（旧段保留，数据安全）: ENOSPC"}
    保留段数          1
    恢复后 n          50      ← 数据完整
```

**最后一个场景最重要**：快照写失败时**保留所有旧段**，数据一条不丢。

### 数据安全的关键顺序

```js
compact() {
  // ① 先写快照。失败 → 直接返回，一个段都不删
  let w;
  try { w = writeSnapshot(...); }
  catch (e) { return { ok:false, error:'快照失败（旧段保留）' }; }

  // ② 快照确认落盘，才删旧段
  this.log.dropSegmentsBefore(seq);
}
```

**顺序反了就会永久丢数据。**

---

## 二、多进程文件锁

### 为什么不用 `proper-lockfile`

项目**全程零依赖**。`proper-lockfile` 会拉进来 5~8 个传递依赖。

Node 没有内置 `fcntl`，但有三种原生原子手段：

| 手段 | 原子性来源 | 我的评价 |
|---|---|---|
| `openSync(path, 'wx')` | `O_EXCL`，内核保证 | ✅ **选它** |
| `mkdirSync(path)` | 目录创建原子 | 也行，但多一层开销 |
| `linkSync(tmp, path)` | 硬链接原子 | 也行，但跨文件系统会失败 |

选 `O_EXCL` 还因为：**能在锁文件里写 PID/主机名**，方便诊断"谁锁着"。

### 三种锁问题

#### ① 互斥

6 个进程同时抢，只有一个拿到，其余等待或超时。

#### ② 僵尸锁（最麻烦）

**`kill -9` 不会执行清理代码，锁文件留在磁盘上。**

解法：

```js
// 锁文件里写 PID
{ pid: 1234, host: 'myhost', at: ..., hb: ... }

// 抢锁失败时，探测 PID 是否还活着
try {
  process.kill(meta.pid, 0);    // 不发信号，只检查存在
  return true;                   // 活着
} catch (e) {
  if (e.code === 'EPERM') return true;   // 存在但没权限 = 活着
  return false;                            // ESRCH = 已死
}
```

#### ③ 强夺竞态（最隐蔽）

如果 A 和 B **同时**发现锁是僵尸，都去删、都去建 —— 两个都以为自己持锁。

解法：**用 `rename` 抢清理权。**

```js
const tmp = path + '.stale.' + process.pid + '.' + Date.now();
fs.renameSync(path, tmp);    // ★ 原子：只有一个进程能成功
fs.unlinkSync(tmp);
return this._tryOnce();      // 重新抢
```

`rename` 在同一文件系统内是原子的，**只有一个能成功**。失败的会走回 `_tryOnce()` 重新判断。

### 实测

#### ① 互斥 + 不丢写

```
6 个进程同时抢锁，每个写 40 条

  p0    ✓ 拿到锁    40 条
  p1    ✓ 拿到锁    40 条
  ...
  p5    ✓ 拿到锁    40 条

  总写入: 240
  恢复后记录数: 240   去重后: 240   重复: 0
  ✓ 无丢失、无重复
```

#### ② 僵尸锁回收

```
持有者: pid=27305  存活=true
持锁期间别人抢: ✓ 被拒
kill -9 后锁文件: 仍在（僵尸）
kill 后别人抢:   ✓ 拿到（僵尸回收成功）
```

#### ③ 严苛测试：写到一半强杀

```
第1轮  僵尸锁=有(存活否)  抢锁=✓(强夺)  恢复n= 540  跳号=无  ✓
第2轮  僵尸锁=有(存活否)  抢锁=✓(强夺)  恢复n= 562  跳号=无  ✓
第3轮  僵尸锁=有(存活否)  抢锁=✓(强夺)  恢复n= 280  跳号=无  ✓
第4轮  僵尸锁=有(存活否)  抢锁=✓(强夺)  恢复n= 568  跳号=无  ✓
第5轮  僵尸锁=有(存活否)  抢锁=✓(强夺)  恢复n= 305  跳号=无  ✓
```

**5 轮全部：僵尸锁强夺成功 + 数据完整 + 无跳号。**

---

## 三、用法

```js
const { LockedStore } = require('./shell/lock');

// 自动抢锁，抢不到就抛异常（不会静默降级）
const store = new LockedStore({
  dir: '/var/pulse/counter',
  mode: 'fsync',
  heartbeatMs: 5000,      // 每 5 秒心跳，防止被误判僵尸
});

let state = store.recover(applyFn).state;

const r = store.append('inc', [1]);
if (!r.ok) {
  if (r.degraded === 'readonly') {
    // 磁盘满：报警，但不要停服务（读还能用）
  } else if (r.degraded === 'fault') {
    // 硬件故障：立刻告警
  }
}

store.close();   // 释放锁 + 关闭 WAL
```

---

## 四、必须承认的局限

### 磁盘满测试

| 局限 | 说明 |
|---|---|
| **monkey-patch 不是真 ENOSPC** | 我改了 `fs.writeSync` 让它当场抛错。真实 ENOSPC 可能延迟到下一次 write 或 fsync 才报（页缓存会先接受） |
| 没测「写到一半被杀 + 磁盘满」 | 组合场景没覆盖 |
| 没测真实只读挂载 | `mount -o ro` 的行为没验证 |

**所以本测试证明的是「错误处理逻辑正确」，不是「真实硬件异常下的行为」。**

### 文件锁测试

| 局限 | 说明 |
|---|---|
| 都在同一台机器 | 没测 NFS/网络文件系统（那上面 `O_EXCL` 靠不住） |
| 忙等而非阻塞 | `acquire()` 用 busy-wait，高竞争下会烧 CPU |
| 30 秒心跳超时 | 跨主机时，长任务必须调 `heartbeat()`，否则被误判僵尸 |
| 没测时钟回拨 | NTP 调整可能让心跳判断出错 |

---

## 五、现在的完整清单

| 项 | 状态 |
|---|---|
| 分段 WAL | ✅ |
| 快照（原子 + CRC） | ✅ |
| Compaction | ✅ |
| 崩溃恢复 | ✅ 40 轮 |
| **磁盘满 / IO 错误防护** | ✅ **6/6** |
| **多进程文件锁** | ✅ **3/3 + 5 轮强杀** |
| 增量快照 | ❌ |
| 网络文件系统 | ❌ |
| 完整断电测试 | ❌ 需真机拔电源 |

### 距离「工业级」还差什么

```
❌ 增量快照    —— 状态几百 MB 时全量序列化会卡住
❌ NFS 支持    —— O_EXCL 在 NFS 上不可靠，需要 fsync+verify
❌ 真断电验证  —— 需要硬件（树莓派拔电源）
❌ 备份/复制   —— 单点，磁盘坏了就全没
```

**前三项都可以做，第四项需要另一台机器。**

---

## 六、测试命令

```bash
# 磁盘满（6 个场景）
node shell/diskfull_test.js

# 文件锁（3 项）
node shell/lock_test.js

# 严格：强杀中途
node /tmp/lockkill.js      # 见本文件"严苛测试"一节的脚本

# 崩溃恢复（40 轮）
TRIALS=10 node shell/crash_test.js

# WAL 延迟影响
N=20000 node shell/bench_wal.js
```
