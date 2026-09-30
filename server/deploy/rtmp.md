# 直播部署（自建推流）

> ⚠️ 先说结论：**直播很吃带宽**。1080p 约需 3~6 Mbps 上行，100 人同时看约需 150 Mbps。
> AutoDL 那种实例（通过 SSH 隧道）**做不了直播**——实测隧道只有 25KB/s，视频至少要 500KB/s。
> 要自建，必须有**真实公网带宽**的服务器；人多了直接买云直播更划算。

---

## 一、三种做法，按省事程度排

| 方式 | 要什么 | 优缺点 |
|---|---|---|
| **① 第三方嵌入** | 无 | 最省事。抖音/视频号/B站开播 → 拿分享链接 → 后台选「第三方嵌入」贴进去。缺点：平台水印、观众可能被引走 |
| **② 云直播** | 阿里云/腾讯云账号 | 稳定不卡，按量付费（几块钱一场）。拿到 m3u8 地址填进后台即可 |
| **③ 自建 SRS** | 有公网带宽的服务器 | 无广告、观众不出站。但要自己扛带宽和运维 |

---

## 二、自建：用 SRS（推荐）

### 1. 装 SRS

```bash
docker run -d --name srs \
  -p 1935:1935 -p 8080:8080 -p 1985:1985 \
  ossrs/srs:5
```

| 端口 | 用途 |
|---|---|
| 1935 | RTMP 推流 |
| 8080 | HTTP-FLV / HLS 播放 |
| 1985 | 管理 API |

### 2. 推流

手机装个「直播助手」类 App，或用 ffmpeg：

```bash
ffmpeg -re -i 视频源 \
  -c:v libx264 -preset veryfast -tune zerolatency \
  -b:v 1500k -maxrate 1500k -bufsize 3000k -g 50 \
  -c:a aac -b:a 96k -ar 44100 \
  -f flv rtmp://你的服务器IP/live/stream
```

> `-g 50` 是关键：关键帧间隔小，观众进来才快。
> `-tune zerolatency` 降延迟。

### 3. 拿到播放地址

| 格式 | 地址 | 说明 |
|---|---|---|
| **HLS** | `http://你的服务器:8080/live/stream.m3u8` | 兼容性最好，iPhone 能播，延迟 5~15 秒 |
| HTTP-FLV | `http://你的服务器:8080/live/stream.flv` | 延迟 1~3 秒，但 **iOS 播不了** |

**建议填 HLS**（后台默认就是）。

### 4. 配 HTTPS（必须）

微信里打开 http 页面会有安全警告，而且很多浏览器禁止 http 页面加载音视频。

```bash
# 用 nginx 反代 + Let's Encrypt
sudo certbot --nginx -d live.example.com
```

nginx 配置参考：

```nginx
server {
    listen 443 ssl http2;
    server_name live.example.com;

    ssl_certificate     /etc/letsencrypt/live/live.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/live.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        # HLS 要关缓冲，否则会攒一堆才发
        proxy_buffering off;
    }
}
```

最后播放地址就变成 `https://live.example.com/live/stream.m3u8`。

---

## 三、带宽怎么算

```
所需带宽(Mbps) ≈ 码率(Mbps) × 同时观看人数
```

| 码率 | 画质 | 10 人 | 50 人 | 100 人 |
|---|---|---|---|---|
| 1.5 Mbps | 720p | 15 Mbps | 75 Mbps | 150 Mbps |
| 3 Mbps | 1080p | 30 Mbps | 150 Mbps | 300 Mbps |

**普通云服务器一般给 1~5 Mbps 带宽** → 只够几个人看。

**超过 10 个人看，就别自建了**，直接用云直播：
- 阿里云视频直播 / 腾讯云直播
- 按流量计费，1 小时 1080p 大约几块钱
- 有全球 CDN，不卡

---

## 四、后台怎么操作

1. 打开 `https://你的直播服务器/live-admin.html`
2. 输入 `ADMIN_TOKEN`
3. 视频源选 **HLS**，把 `.m3u8` 地址填进去
4. 打开左上角**直播开关**
5. 点保存

顾客端就会出现：

- 首页右下角多一个红色 **📺 直播中** 悬浮按钮
- 点进去是直播间：视频 + 商品列表 + 聊天
- 页脚也会出现「📺 直播中」入口

---

## 五、常见问题

**Q：HLS 延迟太高（十几秒），能降吗？**
A：SRS 里把 HLS 切片改短：

```
hls_fragment     1;    # 默认 10 秒
hls_window       6;
```
代价是卡顿率上升。想要低延迟就用 WebRTC（SRS 也支持，但配置更麻烦）。

**Q：iPhone 看不了？**
A：检查是不是用了 FLV。iOS 只支持 HLS，后台视频源要选 HLS。

**Q：观众说很卡？**
A：带宽不够。降码率（`-b:v 800k`）或改用云直播。

**Q：能录播回看吗？**
A：SRS 支持 DVR，配置 `dvr { enabled on; dvr_plan session; }` 即可。当前前端没做回看入口。

**Q：聊天需要服务器吗？**
A：需要。GitHub Pages 上没有后端，聊天区会自动降级成「联系商家」的提示，视频照常能看。
