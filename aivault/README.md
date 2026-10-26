# aivault · AI 跑在你手机上，key 不出设备

> 挂在卤味商店仓库下面的一个子模块。
> 和 `snapshot.yml` 是同一类东西：定时跑一次、干点活、把结果写回仓库。
> **唯一的区别是：要"用脑子"的时候，它不去调云端 API，而是问你手机上的 vault。**

---

## 一、它解决什么

| 常规做法 | 问题 |
|---|---|
| key 放 GitHub Secrets | 能用，但 key 就交给 GitHub 了 |
| key 写进仓库 | 立刻泄漏 |
| **本方案** | **key 在你手机磁盘上，远程只发问题收答案** |

```
┌─────────────────────────┐
│  你的手机                │
│  .secrets/*.env         │  ← key 只在这
│  vault.js               │
│   收请求 → 调 API → 回   │
└─────────────────────────┘
          ↑ MQTT ↓
┌─────────────────────────┐
│  GitHub Actions         │
│  agent/daily.js         │  ← 只发 prompt、只收 text
└─────────────────────────┘
```

**副作用（好事）**：手机一关，AI 那步就停，任务自动降级成规则摘要，**workflow 永远不会红**。

---

## 二、不需要任何 token 的原因

这个 workflow **没有用任何 Secret**。`VAULT_CHAN` 直接写在 `aivault.yml` 里。

为什么这样安全：

| 担心 | 实际情况 |
|---|---|
| 频道名公开 = 别人能刷你额度？ | vault 端有**每小时 60 次**硬限，刷不动 |
| 别人能拿到你的 key？ | 拿不到。key 从不上网络，只在你手机磁盘 |
| 别人能发恶意 prompt？ | 能发，但会占用那 60 次名额，且全部记进 `audit.log` |
| 想换频道名？ | 改 `aivault.yml` 一行 + 手机重启 vault，提交即可 |

**真正的护栏在 vault 那端，不在仓库里。** 这是这套设计的核心取舍。

---

## 三、手机端：启动 vault

```bash
cd aivault

# 频道名必须和 .github/workflows/aivault.yml 里的一致
export VAULT_CHAN=luhuo-aivault-7f3k9x

node vault.js
```

**输出：**
```
[vault] 已加载 provider: mock, hunyuan, hunyuan3d
[vault] 就绪，监听 zhz/vault/luhuo-aivault-7f3k9x/ask
```

### 让它常驻（脱离终端）

```bash
setsid nohup env VAULT_CHAN=luhuo-aivault-7f3k9x node vault.js \
  > /tmp/vault.log 2>&1 < /dev/null &

# 确认
tail -3 /tmp/vault.log
```

> ⚠️ 在 Android 沙箱里，RikkaHub 退出会连带杀掉。要真正 7×24，得放到 Termux 或一台 VPS 上。

### 加 DeepSeek key

```bash
mkdir -p .secrets
cat > .secrets/deepseek.env <<'EOF'
DS_KEY=<你的真实 key>
EOF

# 重启 vault，--status 里会多出 deepseek
```

provider 自动从 `.secrets/*.env` 发现，支持：
- `hunyuan.env` → `hunyuan`（聊天）+ `hunyuan3d`（3D 生成）
- `deepseek.env` → `deepseek`
- `mock` → 永远可用，验证链路用

---

## 四、远程端

```bash
# 查 vault 活着吗
node aivault/agent/brain.js --status

# 问一句
VAULT_CHAN=luhuo-aivault-7f3k9x node aivault/agent/brain.js "你好"

# 基于文件回答
VAULT_CHAN=luhuo-aivault-7f3k9x node aivault/agent/brain.js --file README.md "总结要点"

# 指定 provider
VAULT_CHAN=luhuo-aivault-7f3k9x node aivault/agent/brain.js --provider deepseek "..."

# 生成摘要（workflow 跑的就是这个）
VAULT_CHAN=luhuo-aivault-7f3k9x OUT_FILE=aivault/DIGEST.md node aivault/agent/daily.js
```

---

## 五、实测

**规则模式（vault 离线）：**
```
=== 采集事实 ===
  仓库: luhuo  分支: gh-pages
  24h 提交: 0   未提交: 13
  (未设置 VAULT_CHAN，跳过 AI)
=== 已写入 /tmp/D1.md (178 字符, 模式=rule) ===
exit=0
```

**AI 模式（vault 在线）：**
```
[vault] 就绪，监听 zhz/vault/luhuo-aivault-7f3k9x/ask
=== 尝试用 vault 上的 AI 总结 ===
  ✓ AI 摘要成功 (mock, 6ms)
=== 已写入 /tmp/D2.md (347 字符, 模式=ai) ===
```

**离线降级也保证 exit=0**，所以 workflow 不会因为手机没开而变红。

---

## 六、安全设计

| 措施 | 防什么 |
|---|---|
| key 只在 `.secrets/*.env` | 不进命令行（`ps aux` 看不到）、不进 git |
| 每小时 60 次上限 | 被刷爆 |
| 输入 8000 字符上限 | prompt 撑爆上下文 |
| `VAULT_HMAC`（可选） | 想更严就设：伪造请求直接拒 |
| `audit.log` | 谁何时用多少 token |

### 想开启 HMAC（更严）

```bash
# 手机端
export VAULT_HMAC=你的随机串
node vault.js

# 远程端
VAULT_HMAC=你的随机串 node aivault/agent/brain.js "..."
```

**但 HMAC 不能进 workflow（公开仓库看得到）**，所以 Actions 场景下建议保持关闭，靠限流。

---

## 七、已知限制

| 限制 | 说明 |
|---|---|
| 依赖手机在线 | 不在线 → 降级为规则摘要 |
| MQTT 公共 broker | `broker.hivemq.com` 无 SLA，可换自建 EMQX |
| 无流式输出 | 一次请求等一次响应 |
| 单请求 60 秒超时 | 长文本可能不够 |
| Android 沙箱会杀进程 | RikkaHub 退出即死，要 7×24 需 Termux/VPS |

---

## 八、加 3D 生成（用你的混元 key）

`vault.js` 里的 `hunyuan3d` provider 已经实现了异步 submit+poll：

```bash
VAULT_CHAN=luhuo-aivault-7f3k9x \
  node aivault/agent/brain.js --provider hunyuan3d "一把发光的剑，低多边形风格"
```

vault 会提交任务、每 5 秒轮询、完成后返回资源 URL。
**key 全程在你手机上，Actions 那边只拿到一个 URL。**
