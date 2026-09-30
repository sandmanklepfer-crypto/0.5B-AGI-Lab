# 卤味小店 · 微信支付服务器

给「卤味小店」网页接上**真正的微信支付**：顾客扫码付钱 → 微信服务器回调 → 自动标记已付款并通知你。

---

## 一、为什么需要这台服务器？

你原来的网页挂在 GitHub Pages 上，它是**纯静态**的：只能放 HTML/JS/CSS，不能跑代码。

微信支付的工作方式是：

```
顾客扫码付款
      ↓
微信支付服务器 ──POST──▶  你的回调地址 /api/pay/notify
      ↓                        （必须公网、必须 HTTPS）
   钱到账                  你的服务器验签 → 标记订单已付 → 通知老板
```

**微信是主动来"敲"你服务器的**，GitHub Pages 接不住这一下。所以必须有一台能常驻运行、有公网 HTTPS 地址的服务器。

> 好消息：你这台服务器**很便宜**，一台 2 核 2G 的云服务器（约 ¥60~100/年，学生机更便宜）就绰绰有余；甚至家里的树莓派 + 内网穿透也行。

---

## 二、这套代码做了什么

```
server/
├── index.js            启动入口：API + 托管网页
├── app.js              路由：下单、生成支付码、查状态、微信回调
├── lib/
│   ├── config.js       读配置（环境变量 / .env / config.json）
│   ├── wxpay.js        微信支付 v3 签名、下单、查单、关单、回调验签解密
│   ├── store.js        订单存储（JSON 文件，原子写入）
│   ├── notify.js       付款成功后通知老板（webhook / 邮箱）
│   └── http.js         零依赖 HTTP 小工具
├── vendor/qrcode.js    生成支付二维码（已内置，不用 npm）
└── test/smoke.js       21 项冒烟测试
```

**零依赖**：`package.json` 里没有任何第三方包，不用 `npm install`，只要装了 Node 18+ 就能跑。

它同时会把整个卤味网页（`index.html`、`pay.html`、`css/`、`js/`、`img/`、`data/`）一起托管出去——所以**只要部署这一台服务器，网页和支付就都齐了**，GitHub Pages 可以继续留着当备份。

---

## 三、三步跑起来（先本地看效果）

```bash
cd luhuo/server
cp .env.example .env

# 打开 .env，把最后一行的 MOCK=0 改成 MOCK=1（演示模式）
node index.js
```

然后浏览器打开 `http://localhost:8787`：

1. 选卤味 → 去结算 → 提交订单
2. 自动跳到收银台 `pay.html`
3. 点页面上的 **「🧪 演示模式：模拟支付成功」**
4. 页面变成「支付成功」，你终端里会打印出收到的订单

这条链路和真实微信支付**完全一样**，只是付款那一步被模拟了。跑通它，就说明代码没问题。

跑测试：

```bash
node test/smoke.js     # 21 项全过
```

---

## 四、上真实支付要准备什么

### 4.1 硬件/域名

| 需要 | 说明 | 大概成本 |
|---|---|---|
| 云服务器 | 1 核 1G 就够，Ubuntu/Debian | ¥60~100/年（学生机更便宜） |
| 域名 | 必须**备案**（微信支付回调要求域名已备案） | ¥30/年 |
| HTTPS 证书 | Let's Encrypt 免费，一条命令搞定 | 免费 |

> ⚠️ 微信支付回调**不接受 IP 地址、不接受 http**，必须是 `https://` 的**已备案域名**。

### 4.2 微信支付商户号（这是最麻烦的一步）

**个人（没有营业执照）目前无法申请微信支付商户号**，这是硬性规定。你需要：

1. **营业执照**（个体工商户执照就能办，很多地方网上 1~3 天办好）
2. 申请**微信支付商户号**：<https://pay.weixin.qq.com> → 注册 → 提交执照、法人身份证、门店照片
3. 审核通过后，在商户平台拿到这几样东西：

| 名称 | 在哪拿 | 填到 .env 的 |
|---|---|---|
| 商户号 mchid | 商户平台首页 | `WXPAY_MCHID` |
| 商户 API 证书序列号 | 账户中心 → API 安全 | `WXPAY_SERIAL_NO` |
| 商户 API 私钥 `apiclient_key.pem` | 账户中心 → API 安全 → 申请证书 | `cert/apiclient_key.pem` |
| APIv3 密钥（32 位） | 账户中心 → API 安全 → 设置 APIv3 密钥 | `WXPAY_APIV3_KEY` |
| 微信支付公钥 `pub_key.pem` | 账户中心 → API 安全 → 微信支付公钥 | `cert/pub_key.pem` |
| AppID | 关联的公众号/小程序 | `WXPAY_APPID` |

> 只做「Native 扫码支付」的话，**不需要**公众号，用「微信支付商户号绑定的 AppID」即可。
> 没有小程序也没关系，可以在商户平台申请一个「AppID（商户号）」直接用。

### 4.3 目录结构

```
server/
├── .env                       ← 你的配置（别提交到 GitHub）
└── cert/
    ├── apiclient_key.pem      ← 商户私钥
    └── pub_key.pem            ← 微信支付公钥
```

```bash
mkdir -p cert
# 把两个 pem 文件放进去
chmod 600 cert/*.pem
```

---

## 五、配置 `.env`

```ini
# 对外地址（必须和你的域名一致，末尾不带斜杠）
PUBLIC_BASE_URL=https://pay.example.com
PORT=8787
ADMIN_TOKEN=换成一串随机字符

# 微信支付
WXPAY_MCHID=1900000000
WXPAY_APPID=wx0000000000000000
WXPAY_SERIAL_NO=你的证书序列号
WXPAY_APIV3_KEY=你的32位APIv3密钥
WXPAY_PRIVATE_KEY_PATH=./cert/apiclient_key.pem
WXPAY_PUBLIC_KEY_PATH=./cert/pub_key.pem

# 演示模式：上线后必须是 0
MOCK=0
```

改完重启，看启动日志：

```
🍲 卤味小店 · 支付服务器已启动
   模式：LIVE（真实微信支付 v3）
   回调：https://pay.example.com/api/pay/notify
   商户号：1****0   私钥：已加载   APIv3Key：已配置
```

看到 `模式：LIVE` 和 `私钥：已加载` 就对了。

---

## 六、部署到服务器

```bash
# 1. 把整个 luhuo 目录传上去
scp -r luhuo/ root@你的服务器:/opt/luhuo/

# 2. 服务器上安装 Node 18+
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 3. 配置
cd /opt/luhuo/server
cp .env.example .env && nano .env      # 填真实值
mkdir -p cert && nano cert/apiclient_key.pem   # 粘贴私钥

# 4. 先手动跑一下试试
node index.js
# 另开一个终端：
curl https://pay.example.com/api/health
```

没问题后设置**开机自启 + 崩溃自动重启**：

```bash
sudo cp deploy/luhuo-pay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now luhuo-pay
sudo journalctl -u luhuo-pay -f      # 看日志
```

配 HTTPS（域名要先解析到这台服务器）：

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo cp deploy/nginx.conf.example /etc/nginx/conf.d/luhuo-pay.conf
sudo nano /etc/nginx/conf.d/luhuo-pay.conf     # 改域名
sudo certbot --nginx -d pay.example.com
```

---

## 七、不想花钱？免费托管方案

可以白嫖，但我必须先把 **4 个坑** 跟你说清楚，不然你会在顾客面前翻车。

### 7.1 免费服务器的 4 个坑

| 坑 | 会发生什么 | 怎么解决 |
|---|---|---|
| **① 冷启动/休眠** | 免费实例 15 分钟没人访问就睡。顾客扫码时页面转圈 **50 秒**，微信回调还可能超时 | 用免费监控每 5~10 分钟访问一次保活（我已备好 GitHub Action） |
| **② 磁盘是临时的** | 容器一重启，**订单记录全清空** | 把订单存进 GitHub 仓库（`STORAGE=github`，已实现，重启不丢） |
| **③ 境外节点绕路** | 服务器在新加坡/美国，微信回调要跨国，偶尔慢或失败 | 微信会自动重试约 15 次、持续 24 小时，基本都能补上。但**要追求稳，就得用国内服务器** |
| **④ 免费额度说没就没** | 平台随时改政策/回收额度 | 别把大额生意全押上去，留个收款码兜底 |

> ⚠️ **还有一条硬规定**：微信支付要求回调域名是 **HTTPS**。免费平台给的 `*.onrender.com`、`*.vercel.app` 这类域名能生成 https，**但无法备案**。
> 实测「Native 扫码支付」用未备案域名基本能通；但以后你想加 **H5 支付 / 小程序支付**，就必须备案 → 必须国内服务器。

### 7.2 三个方案，按推荐度排

#### 🥇 方案 A：Oracle Cloud 永久免费服务器（最推荐）

真的免费、**不休眠、有持久盘、能跑我现在的代码一行不改**，还能自己备案不了但速度可以。

- 免费额度：ARM 4 核 24G 内存 + 200G 硬盘，**永久免费**
- 地区选 **Japan / Seoul / Singapore**（离国内近）
- 需要一张信用卡做验证（**不扣费**，只是验证身份）
- 注册有点折腾，抢不到 ARM 就先选 AMD 的 1 核 1G，也够用

拿到机器后，直接照上面的 **「六、部署到服务器」** 做就行，`STORAGE=local` 不用改。

#### 🥈 方案 B：国内云 1 核 2G（严格说不免费，但最稳）

阿里云/腾讯云的新用户特惠、学生机，**¥38~99 / 年**。

**为什么我建议你认真考虑这个：**
- ✅ 唯一能**备案**的选择（微信支付最稳、以后能加 H5/小程序支付）
- ✅ 微信回调**同城直达**，几十毫秒，不用跨国
- ✅ 有持久盘，订单不会丢，不用折腾 GitHub 存储

说白了，一年几十块钱换"心里踏实"，比省那点钱值。

#### 🥉 方案 C：免费容器平台（已经给你配好）

| 平台 | 免费额度 | 休眠 | 备注 |
|---|---|---|---|
| **Koyeb** | 1 个 nano 实例 | 不休眠 | 目前对国内相对友好 |
| **Zeabur** | 有限免费额度 | 会 | 国内开发者常用 |
| **Render** | 1 个 web service | **15 分钟休眠** | 必须配保活 |
| Fly.io | 已改按量计费 | — | 不再是纯免费 |

**这些平台我都已经适配好了**，仓库里现成的文件：

```
Dockerfile              ← 所有平台通用，直接构建就行
render.yaml             ← Render 一键蓝图部署
.dockerignore           ← 已排除 .env / cert，绝不会泄露密钥
.github/workflows/keepalive.yml   ← 免费保活
```

**部署步骤（以 Render 为例）：**

1. 把仓库推到 GitHub（你已经有仓库了）
2. Render 控制台 → **New → Blueprint** → 选你的仓库
3. 它会读到 `render.yaml` 自动建好服务
4. 在 Render 面板里填环境变量（`PUBLIC_BASE_URL`、`ADMIN_TOKEN`、微信那几项）
5. **微信的两个 pem 证书文件**：免费平台没法传文件，所以改用「环境变量传内容」👇

```bash
# 把私钥内容整个塞进环境变量（保留换行）
WXPAY_PRIVATE_KEY_PEM="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBg...
-----END PRIVATE KEY-----"

WXPAY_PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkq...
-----END PUBLIC KEY-----"
```

6. 保活：仓库 → Settings → Secrets → Actions → 新建 `PAY_URL`，值为你的服务地址
   （`keepalive.yml` 每 10 分钟自动访问一次）

**关于订单不丢（方案 C 必看）：**

免费实例的磁盘重启就清空，所以把订单存到你的 GitHub 仓库里：

```ini
STORAGE=github
GH_TOKEN=ghp_xxxx          # 建议单独建一个只给 Contents 读写权限的 token
GH_OWNER=你的用户名
GH_REPO=你的仓库
GH_BRANCH=main
GH_FILE=server-orders/orders.json
```

这样订单会写进仓库里的一个文件，**容器重启、重新部署都不会丢**。
（已经过 8 项离线测试：含 sha 冲突自动重试、多实例并发写不丢单）

### 7.3 我的建议

```
只是想先看看能不能跑通  →  方案 C（免费，跟着 7.2 配就行）
准备真收钱了            →  方案 B（¥38~99/年，能备案，最稳）
一分钱不想花又要稳定    →  方案 A（Oracle 永久免费，代码不用改）
```

---

## 八、在后台开启在线支付

1. 打开你的后台 `admin.html` → **店铺设置**
2. 找到 **「微信在线支付（真正的支付 + 自动回调）」**
3. 勾选 **启用微信在线支付**
4. **支付服务器地址** 填 `https://pay.example.com`（末尾不要斜杠）
5. 点 **测试支付服务器连接**，看到绿色 ✅ 就对了
6. 点右上角 **💾 保存并发布**

之后顾客结算页的付款方式里就会出现 **「微信在线支付（推荐）」**，下单后自动跳转收银台，付完钱微信直接回调你的服务器。

---

## 九、付款成功后你怎么收到通知

三种方式，任选或叠加：

| 方式 | 怎么配 |
|---|---|
| **邮箱**（推荐，最省事） | 后台「订单设置」填邮箱，付款成功自动发一封「【已付款】」邮件给你 |
| **终端日志** | 服务器上 `journalctl -u luhuo-pay -f`，每笔付款都打印详情 |
| **机器人 webhook** | `.env` 里配 `MERCHANT_WEBHOOK`，可接企业微信/飞书/钉钉机器人 |

查全部订单（需要你在 `.env` 里设的 `ADMIN_TOKEN`）：

```bash
curl -H "Authorization: Bearer 你的ADMIN_TOKEN" \
     https://pay.example.com/api/admin/orders | python3 -m json.tool
```

---

## 十、接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查，后台用它测连接 |
| POST | `/api/orders/create` | 下单（金额由服务端按 `data/*.json` 重算，前端改不了价） |
| GET | `/api/orders/:no` | 查订单详情 |
| POST | `/api/pay/prepay` | 生成微信支付码（Native 下单） |
| GET | `/api/pay/status` | 轮询支付状态（顺带主动向微信查单兜底） |
| POST | `/api/pay/notify` | **微信支付回调入口**（验签 + AES-GCM 解密） |
| GET | `/api/admin/orders` | 老板查所有订单（需 `ADMIN_TOKEN`） |
| GET | `/api/qr.svg?text=` | 生成任意二维码（支付码渲染用） |
| POST | `/api/pay/mock` | 仅演示模式：手动标记已付 |

---

## 十一、安全设计（已经做好的）

- ✅ **金额服务端重算**：前端传的 `total` 一律忽略，按 `data/products.json` 的价格重新算，改价无效
- ✅ **回调验签**：用微信支付公钥验证 `Wechatpay-Signature`，伪造的回调返回 401
- ✅ **回调解密**：AES-256-GCM 解密，校验 authTag
- ✅ **防重放**：回调时间戳超过 5 分钟直接拒绝
- ✅ **金额二次核对**：回调里的实付金额和订单金额不一致会标记 `AMOUNT_MISMATCH` 并告警
- ✅ **幂等**：同一订单重复回调只处理一次
- ✅ **库存/起送/手机号校验**：服务端全部复查
- ✅ **目录保护**：`/server/`、`/.git/`、`/.env` 一律 403
- ✅ **订单号不可猜**：`LH` + 时间 + 4 位随机，且查单要精确匹配

---

## 十二、常见问题

**Q：回调一直收不到？**
1. `curl https://你的域名/api/health` 通不通
2. `.env` 里 `PUBLIC_BASE_URL` 和实际域名是否一致（回调地址是按它拼的）
3. 服务器安全组/防火墙有没有放行 443
4. 商户平台 → 产品中心 → 开发配置 → 支付回调有没有填对
5. `journalctl -u luhuo-pay -f` 看有没有 `[notify]` 日志

**Q：报「签名验证失败」？**
- `WXPAY_SERIAL_NO` 和 `cert/apiclient_key.pem` 必须是一对（同一个证书）
- 私钥文件要完整的 `-----BEGIN PRIVATE KEY-----` 到 `-----END PRIVATE KEY-----`

**Q：报「回调验签失败」？**
- `cert/pub_key.pem` 是不是「微信支付公钥」（不是商户自己的证书，也不是平台证书）
- 如果只下载了「平台证书」，改用 `WXPAY_PLATFORM_CERT_PATH=./cert/platform_cert.pem`

**Q：顾客付了钱但订单还是待支付？**
- 系统在顾客轮询状态时会主动向微信**查单兜底**，一般 2~3 秒内会补上

**Q：能不用营业执照吗？**
- 不能。微信支付商户号必须营业执照。没有执照的话只能继续用收款码，或者用第三方聚合支付通道——但那些通道（比如你现在这张银联码背后的 `jsmjushoumi.com`）属于"二清"，**钱先到第三方再到你**，有资金风险和随时被封的风险，我不建议把大额生意押在上面。

---

## 十三、关于你上传的那张银联聚合码

我解了一下二维码内容：

```
https://uni.jsmjushoumi.com/paySyt?data=O1VaeFJvc2ZT
```

这是**第三方聚合支付的固定收款码**（静态码）：
- 它只是一个固定链接，**没有金额、没有订单号**
- 顾客扫它 = 打开那个平台的页面自己填金额付款
- 平台**不会**把结果回调给你的网页（因为你在那边根本没有账号 API）
- 而且它是"二清"：钱先进 `jsmjushoumi` 的账，再结算给你，平台跑路/被查你就拿不到钱

所以它能做的只有一件事：**当成一张收款码图片展示**（我已经放进 `img/pay-unionpay.png` 并接进了付款方式"聚合码扫码"）。

要"真正的支付 + 自动回调"，只有**直连微信支付官方**这一条正路，也就是这套代码。

---

## 直播模块

### 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/live/config` | 直播配置（公开，前端用） |
| POST | `/api/live/ping` | 心跳，用于统计在线人数 |
| GET | `/api/live/chat?since=` | 拉取聊天（轮询，比 SSE 适合隧道场景） |
| POST | `/api/live/chat` | 发送聊天 |
| GET | `/api/admin/live` | 读直播设置（需 ADMIN_TOKEN） |
| POST | `/api/admin/live` | 改直播设置（需 ADMIN_TOKEN） |
| DELETE | `/api/admin/live/chat` | 清空聊天（需 ADMIN_TOKEN） |

### 页面

| 页面 | 用途 |
|---|---|
| `live.html` | 直播间（顾客端）：播放器 + 商品 + 聊天 |
| `live-admin.html` | 开播控制台（商家端）：开关直播、填流地址、看聊天 |

### 播放格式

| 格式 | 兼容性 | 延迟 |
|---|---|---|
| **HLS (.m3u8)** | 全平台（含 iOS） | 5~15 秒 |
| FLV (.flv) | 安卓/PC，**iOS 不支持** | 1~3 秒 |
| embed | 嵌第三方直播间 | 取决于平台 |

### 聊天安全

- 同一 IP 两条消息最短间隔 2 秒
- 单条最长 200 字符，控制字符会被清掉
- 禁止发链接
- 支持屏蔽词（后台可配）
- 消息内存环形缓冲，最多留 300 条

### 降级行为

GitHub Pages 上没有后端时：
- 视频照常播放（读静态 `data/live.json`）
- 聊天区自动换成「联系商家」提示
- 在线人数显示 0

### 部署

自建推流（SRS / nginx-rtmp）见 **[deploy/rtmp.md](deploy/rtmp.md)**。
