# 天泪纪元 · 联机版（RPG 开放世界）

把原来的《天泪纪元：学院篇》改成**多人联机 RPG**：

- 🗺️ **开放大地图**：3600×2000，四个分区（学院大门 / 学院庭院 / 图书回廊 / 地下走廊），相机跟随，不再是"死板的大厅"。
- 👹 **小怪分布在地图上**：不同区域各有刷新点，会巡游、会追击。多人可以打同一只怪。
- ⚔️ **Boss 变成"锚点"**：原来的 4 个 Boss 关卡入口 → 变成地图上的发光锚点，**走进去自动触发**原来的 Boss 战；打赢/撤退回到原地。
- 👥 **多人实时联机**：探索、交互、世界频道聊天、玩家间 **PVP 对战**。
- 🧩 **保留原玩法**：角色、技能、遗物、剧情、Boss 战全部沿用，只换了"世界"这一层。

## 联机原理（不需要服务器）

联机走**公共 MQTT（WebSocket）**实时通道 —— 免注册、免 Token：

- 客户端连公共 broker（`broker.emqx.io` 等，见 `js/mqtt.js`）
- 每 ~200ms 广播自身位置/血条；世界怪物由房主（先到者）模拟并广播
- 同一「频道」的人就能互相看到、实时同步

所以**直接部署到 GitHub Pages 就能联机**，手机、电脑只要联网就行。

> 想更私密/可自建：`server/` 目录里带了两个零依赖后端（Node / Deno Deploy），
> 用于将来做"服务器权威"的强同步。**不含任何密钥**，敏感值走环境变量。

## 目录

```
index.html js/ css/ assets/     ← 游戏前端（纯静态，可直接 GitHub Pages）
server/node/server.js           ← 可选：自建联机后端（Node，零依赖）
server/deno/server.ts           ← 可选：Deno Deploy 版后端
tools/tldbg.js                  ← 命令行调试台（走 MQTT 发命令给游戏）
tools/tldbg_cdp.js              ← 命令行调试台（走 adb 直连 WebView，需插线/同机）
build_apk.sh                    ← 把 web/ 打进 APK 并签名（复用原壳）
```

## 玩

- **GitHub Pages**：网页打开 `index.html` 即可（推荐横屏）。
- **安卓**：用 `build_apk.sh` 生成 APK（需要原壳 `tianlei_base.apk` 和本地签名）。

## 命令行调试

游戏内置了调试命令通道（画面无任何调试图标）。

```bash
# 方式一：走 MQTT（手机电脑都行）
node tools/tldbg.js state
node tools/tldbg.js tp 1200 1050      # 传送到锚点
node tools/tldbg.js spawn golem 3     # 附近刷 3 只怪
node tools/tldbg.js help

# 方式二：走 adb 直连 WebView（开发机同一台设备）
node tools/tldbg_cdp.js --shot
```

## 安全

- 仓库内**不含任何密钥/令牌**；签名文件、构建产物、APK 均已被 `.gitignore` 排除。
- 公共 broker 上的联机数据是公开的，请勿发送敏感信息。
