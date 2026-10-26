# PulseOS 聚合态外壳 · 使用说明

> 把散落的微内核，聚合成一个能看见、能操作的系统。

---

## 一、跑起来

```bash
cd pulseos
node shell/server.js
```

输出：
```
  ◈ PulseOS 聚合态外壳
  ─────────────────────────────────────
  已装载 audit（audit.pulse）
  已装载 notes（notes.pulse）
  已装载 sensor（sensor.pulse）
  ─────────────────────────────────────
  http://127.0.0.1:8899
```

打开浏览器访问 `http://127.0.0.1:8899`。

---

## 二、界面有什么

```
┌─────────────────────────────────────────────┐
│ 系统总览   服务数 / 总脉冲 / 状态合计 / 因果边 │
├─────────────────────────────────────────────┤
│ 微内核列表                                   │
│  ┌──────────┬──────────┬──────────┐         │
│  │ notes    │ sensor   │ audit    │         │
│  │ 22 B     │ 38 B     │ 22 B     │         │
│  │ add list │ push     │ sampled  │         │
│  │ stats    │ report   │ report   │         │
│  └──────────┴──────────┴──────────┘         │
├─────────────────────────────────────────────┤
│ 因果链   14:32:01  sensor.push → audit.sampled │
├─────────────────────────────────────────────┤
│ PulseScript 编辑器  [检查] [编译并部署]       │
├─────────────────────────────────────────────┤
│ 输出                                         │
└─────────────────────────────────────────────┘
```

**点服务上任意方法名，直接触发一次脉冲。**

---

## 三、PulseScript 语法（全部）

```
service 名字 {
  state {
    字段: 类型 = 默认值
  }

  on "方法名"(参数) {
    语句
  }
}
```

### 类型

| 类型 | 默认值 | 说明 |
|---|---|---|
| `int` | `0` | 整数 |
| `str` | `""` | 字符串 |
| `list` | `[]` | 列表 |
| `map` | `{}` | 字典 |
| `bool` | `false` | 布尔 |

### 语句

| 语句 | 作用 |
|---|---|
| `set 字段 = 表达式` | 改状态 |
| `let 变量 = 表达式` | 局部变量（不持久化） |
| `append 列表, 值` | 追加 |
| `return 表达式` | 返回值 |
| `emit "事件" { 键: 值 }` | **派生**：触发其他服务 |
| `emit "事件" { } after 毫秒` | 延迟派生 |
| `if 条件 { } else { }` | 分支 |

### 内置函数

`len` `now` `int` `str` `min` `max` `slice` `sum`

### 示例

```
service sensor {
  state {
    window: list = []
    total: int   = 0
    peak: int    = 0
    n: int       = 0
  }

  on "push"(v) {
    append(window, v)
    if len(window) > 8 {
      set window = slice(window, len(window) - 8, len(window))
    }
    set total = total + v
    set n = n + 1
    if v > peak { set peak = v }
    emit "sampled" { v: v, n: n }
  }

  on "report" {
    return { avg: int(total / max(n, 1)), peak: peak, samples: n }
  }
}
```

---

## 四、因果自动路由

这是 PulseScript 的核心机制。

```
sensor 里 emit "sampled" { v: 97 }
         ↓
聚合层查找：哪个服务声明了 on "sampled"？
         ↓
        audit 有 → 路由过去
```

实测效果：

```
sensor.push(97)  →  sensor.push → audit.sampled
```

**你不需要写"我要调用 audit"。你只描述"发生了一个 sampled 事件"，路由由系统解决。**

想强制指定目标：

```
emit "sampled" { __to: "audit", v: 97 }
```

### 规则优先级

1. 有 `__to` → 用它
2. 本服务有这个 `on` → 就地触发
3. 全局唯一匹配 → 路由过去
4. 多个服务都有 → **不路由**（避免歧义）

---

## 五、三条铁律（写服务时要记住）

### 铁律一：state 必须小

编译时会显示预估大小：

```
✓ sensor · 2 个方法 [push, report] · 初始状态 38B · 极佳
✓ 大服务 · 2 个方法 [add, list] · 初始状态 1240B · 偏大
```

**判定：< 256 B = 极佳，< 1 KB = 可以，> 1 KB = 偏大（脉冲会变慢）。**

### 铁律二：历史进日志，不进 state

❌ 错误：把 100 万条记录塞进 `list`
✅ 正确：只留滑动窗口，全量数据走段文件（见 `lstore.js`）

### 铁律三：emit 描述因果，不描述调用

❌ `emit "callAudit"` —— 你在描述"调用谁"
✅ `emit "sampled"` —— 你在描述"发生了什么"

**前者耦合，后者可组合。**

---

## 六、HTTP API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/state` | 系统总览 + 服务列表 + 因果链 |
| POST | `/api/pulse` | `{service, op, args}` 触发一次脉冲 |
| POST | `/api/compile` | `{src}` 编译检查，返回诊断 + 状态预估 |
| POST | `/api/deploy` | `{src}` 编译并注册 |
| DELETE | `/api/service/:name` | 卸载（删状态箱） |
| GET | `/api/export/:name` | 导出状态箱（base64） |

### 例子

```bash
# 触发
curl -X POST http://127.0.0.1:8899/api/pulse \
  -H 'Content-Type: application/json' \
  -d '{"service":"sensor","op":"push","args":[97]}'

# 返回
{
  "ok": true,
  "trace": [
    { "service": "sensor", "op": "push", "ms": 2.1, "stateBytes": 51 },
    { "service": "audit",  "op": "sampled", "ms": 1.4, "stateBytes": 40 }
  ]
}
```

**`trace` 就是因果链的完整记录。**

---

## 七、目录

```
lang/pulsescript.js   语言实现（词法 / 语法 / 静态检查 / 解释器）
shell/kernel.js       微内核 + 聚合层（因果路由）
shell/server.js       HTTP 服务
shell/index.html      控制台界面
shell/ui.js           前端逻辑
shell/ui.css          样式
shell/state/*.box     状态箱（运行时生成，已 gitignore）
examples/*.pulse      示例服务
```

---

## 八、限制（诚实说）

| 限制 | 说明 |
|---|---|
| 无类型推断 | 类型只在 state 声明处检查，表达式里不检查 |
| 无循环 | 故意不做。PulseScript 描述单向因果，不做迭代 |
| 无字符串操作 | 需要就加内置函数，不要加操作符 |
| 无并发控制 | 单进程单线程，多写会互相覆盖 |
| 无持久化事务 | `_save` 是覆盖写，断电可能丢最后一次 |
| 因果深度上限 8 | 防止 emit 无限递归 |

**这是一个可运行的骨架，不是生产语言。** 但它证明了：**声明式 + 强制小状态 + 因果路由，是能跑起来的。**

---

## 九、为什么这样设计

### 为什么不用 C/Java/Rust？

它们假设「程序常驻内存、持有指针、管理生命周期」。
PulseScript 假设**程序根本不存在**——只在脉冲那一刻存在。
**范式不同，语言必须不同。**

### 为什么强制 state 小？

因为**状态大小直接等于唤醒延迟**。实测：

| 热状态 | 脉冲往返 |
|---|---|
| 4.3 KB | 7 ms |
| 955 KB | 101 ms |
| 14.7 MB | 1 371 ms |

**语言层面强制小，比运行时优化有效得多。**

### 为什么是 emit 而不是 call？

`call` 是同步的、有返回值的、强耦合的。
`emit` 是异步的、无返回值的、可组合的。

**你描述"发生了什么"，系统决定"谁来处理"。**
这就是 AI 时代需要的编程范式——**声明因果，而非指挥流程。**
