# 部署到 AutoDL 实例（实测可用）

> 本文记录**已经跑通**的部署方式：代码放在 AutoDL 实例上，通过 SSH 反向隧道拿到公网 HTTPS 地址，
> 微信回调能打到 `/api/pay/notify`。

---

## 一、架构

```
顾客手机 ──► https://xxx.serveousercontent.com  （公网 HTTPS）
                    │  SSH 反向隧道
                    ▼
             AutoDL 实例 :8787
                    │
                    ├─ luhuo-app     Node 支付服务（supervisord 托管）
                    └─ luhuo-tunnel  隧道守护，断了自动重连 + 自动同步回调地址
```

AutoDL 实例**在 NAT 后面，没有公网入口**，所以必须靠反向隧道把端口送出去。

---

## 二、一次性准备

```bash
# 1. 装 Node（实例墙了 GitHub，用阿里云镜像）
V=v20.18.0; F=node-$V-linux-x64
curl -o /root/$F.tar.xz https://mirrors.aliyun.com/nodejs-release/$V/$F.tar.xz
tar -xJf /root/$F.tar.xz -C /usr/local
ln -sf /usr/local/$F/bin/node /usr/local/bin/node

# 2. 传代码
scp -P <端口> luhuo-pay.tar.gz root@connect.nma1.seetacloud.com:/root/
ssh -p <端口> root@connect.nma1.seetacloud.com
mkdir -p /root/luhuo && tar xzf /root/luhuo-pay.tar.gz -C /root/luhuo
```

---

## 三、配置

```bash
cd /root/luhuo/server
cp .env.example .env
```

关键几项：

```ini
PORT=8787
MOCK=0                                     # 上线后改 0
PUBLIC_BASE_URL=https://xxx.serveo...com   # 隧道地址，由守护脚本自动写入
ADMIN_TOKEN=<随机字符串>
WXPAY_MCHID=...
WXPAY_SERIAL_NO=...
WXPAY_APIV3_KEY=...
WXPAY_PRIVATE_KEY_PATH=./cert/apiclient_key.pem
WXPAY_PUBLIC_KEY_PATH=./cert/pub_key.pem
```

> 免费/临时环境没法传证书文件时，改用环境变量传 PEM 内容：
> `WXPAY_PRIVATE_KEY_PEM` / `WXPAY_PUBLIC_KEY_PEM`

---

## 四、用 supervisord 托管（关键）

SSH 登录会话里用 `&` 起的后台进程，**登录一断就被回收**。AutoDL 没有 cron，
但装了 `supervisord`，用它托管最稳。

```bash
mkdir -p /root/supervisor
supervisord -c /root/luhuo-supervisor.ini      # 会自己 daemonize
/root/miniconda3/bin/supervisorctl -c /root/luhuo-supervisor.ini status
```

看到这样就对了：

```
luhuo-app      Running   pid 2130
luhuo-tunnel   Running   pid 2095
```

常用命令：

```bash
CTL=/root/miniconda3/bin/supervisorctl
$CTL -c /root/luhuo-supervisor.ini status
$CTL -c /root/luhuo-supervisor.ini restart luhuo-app     # 改了代码/配置后重启
$CTL -c /root/luhuo-supervisor.ini tail -f luhuo-app     # 看实时日志
```

---

## 五、隧道（不要用 localhost.run）

| 服务 | 结果 |
|---|---|
| **serveo.net** | ✅ 可用，GET/POST 都通，回调正常 |
| localhost.run | ❌ 匿名隧道几分钟就被踢，返回 `no tunnel here :(` |
| tunnel.gd | ❌ 域名解析不了 |

```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -R 80:localhost:8787 serveo.net
```

**想让地址固定下来**（回调地址不跟着变）：

```bash
ssh-keygen -t ed25519 -N '' -f /root/.ssh/id_ed25519
cat /root/.ssh/id_ed25519.pub
```

然后打开 serveo 给出的注册链接（要 Google/GitHub 登录），注册后就能用固定子域名：

```bash
ssh -i /root/.ssh/id_ed25519 -R luhuo-pay:80:localhost:8787 serveo.net
```

---

## 六、验证

```bash
# 本机
curl http://localhost:8787/api/health

# 外网（换成本地 public_url.txt 里的地址）
B=$(cat /root/public_url.txt)
curl $B/api/health

# 完整下单链路
curl -X POST $B/api/orders/create -H 'Content-Type: application/json' \
  -d '{"name":"测试","phone":"13900001111","address":"中山路 99 号","items":[{"id":"p_jizhua","qty":2}]}'
```

---

## 七、⚠️ 为什么不建议长期这么用

| 问题 | 说明 |
|---|---|
| **按 GPU 计费** | AutoDL 是算力实例，24 小时开着当支付服务器非常浪费 |
| **隧道地址会变** | 免费 serveo 匿名隧道每次重连换地址，回调地址得跟着改 |
| **随时可能关机** | 平台会回收/重启实例，支付服务中断 |
| **域名不能备案** | `*.serveousercontent.com` 备案不了，将来加 H5/小程序支付不行 |

**结论：这套只适合现在这样"先把流程跑通、验证代码没问题"。**
真要收钱，还是用一台便宜的国内云服务器（¥38~99/年），
按 `server/README.md` 的「六、部署到服务器」做，`STORAGE=local` 不用改。
