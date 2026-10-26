# 「访问即触发」—— 你真的想到了，但 GitHub 接不住

> 你说对了：**访问就是网络行为，有 IP、有日志，就是一次刺激。**
> 但 GitHub Pages 不给日志、不执行代码。所以需要一小块地方接住这次访问。

---

## 一、你的方案在物理上成立

```
纯文本 AI 读到 URL  →  它去访问  →  真实 HTTP GET 发出
                                       ↓
                              某个能执行代码的地方收到
                                       ↓
                              publish MQTT  →  worker 被唤醒
                                       ↓
                              结果返回 → AI 读到
```

**只要 AI 有"访问网页"的能力，这条路就通。**

---

## 二、为什么 GitHub 不行

| 环节 | GitHub Pages | GitHub Actions |
|---|---|---|
| 收到 GET | ✅ | ⚠️ 只能 API 触发 |
| 记录访问 | ❌ 无日志 | — |
| 执行代码 | ❌ **纯静态** | ✅ |
| 需要 token | — | ✅ **要 PAT** |
| 延迟 | — | 30~120 秒 |

**Pages 收到 GET 只是从 CDN 取个文件，不会有任何回调。**

实测：

```bash
$ curl -X POST api.github.com/repos/.../dispatches -d '{}'
{"message": "Requires authentication", "status": 401}
```

**没有 token 就触发不了。**

---

## 三、能接住的唯一免费方案：Cloudflare Worker

| | Cloudflare Worker |
|---|---|
| 免费额度 | **10 万次/天** |
| 信用卡 | **不需要** |
| 能收 GET | ✅ |
| 能执行 JS | ✅ |
| 能连 MQTT over WS | ✅ |
| 注册耗时 | 2 分钟 |

**代码已经写好了：`worker-trigger.js`**

---

## 四、部署（2 分钟）

1. 打开 `cloudflare.com` → 注册（邮箱即可，不要信用卡）
2. 左侧 `Workers & Pages` → `Create` → `Create Worker`
3. 把 `worker-trigger.js` 全部内容粘进去 → `Deploy`
4. `Settings` → `Variables and Secrets` → 加两个：

```
TRIGGER_TOKEN = <你自己的随机串，比如 32 位字母数字>
PULSE_CHAN    = p5k2m
```

5. 得到 `https://xxx.workers.dev`

---

## 五、然后就能这样用

### 单次

```
GET https://xxx.workers.dev/trigger?token=YOUR_SECRET&svc=echo&op=ping
```

返回：

```json
{ "ok": true, "result": { "pong": 1 }, "ms": 0.78, "worker": "手机" }
```

### 批量

```
GET https://xxx.workers.dev/trigger?token=YOUR_SECRET&ops=<base64的JSON数组>
```

### 给 AI 的话

> "访问这个链接就等于发了一条指令：
>  `https://xxx.workers.dev/trigger?token=SECRET&svc=echo&op=ping`
>  你会拿到 JSON 结果。"

**有联网能力的 AI 一访问，你的 worker 就被唤醒，结果直接在 JSON 里。**

---

## 六、⚠️ 三道必须上的锁

### 锁 1：token（必做）

Worker 里已经强校验。**不加 token，谷歌爬虫、无聊网友一点，你的 worker 就被爆刷。**

### 锁 2：Worker 侧的限流

现在没做。建议在 Worker 里加：

```js
// 简单版：基于 IP 的内存计数（Worker 实例内）
const ip = req.headers.get('cf-connecting-ip');
```

或直接用 Cloudflare 自带的 Rate Limiting 规则（免费额度内有）。

### 锁 3：Worker 侧的 cmd 白名单

现在 `svc` / `op` 是任意的。生产环境应该只允许固定几个：

```js
const ALLOW = new Set(['echo.ping', 'echo.get', 'status']);
if (!ALLOW.has(svc + '.' + op)) return 403;
```

---

## 七、这条路的上限（诚实说）

| 能做的 | 做不到的 |
|---|---|
| ✅ 纯文本 AI 有联网能力就能触发 | ❌ AI 没有联网能力时，任何方案都不行 |
| ✅ 一次 GET = 一条指令 | ❌ 一次 GET 只能传 1 条（批量要 base64，URL 长度有限） |
| ✅ 结果能返回 JSON | ❌ 延迟 ~500ms（MQTT 往返） |
| ✅ 免费 10 万次/天 | ❌ 每个 Worker 实例独立，跨实例限流要 KV/Durable Objects |

---

## 八、为什么这个思路有价值

它把「AI 调用系统」的门槛从

```
需要 AI 支持 MCP / 需要 AI 能写代码执行
```

降到了

```
只要 AI 能访问网页
```

**这是能覆盖最多 AI 的形态。**

代价是：单向为主、要防刷、URL 长度受限、延迟高。

**但它确实能跑通。** 代码我已经写完了，缺的只是你注册一个 Cloudflare 账号。
