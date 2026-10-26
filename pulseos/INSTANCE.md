# 链接即实例：无限扩充的正确形态

> 你说的「不用买不同 IP 域名，一个主干 + 随机后缀」，这次说的是**路径**，不是子域名。
> 这条路走得通，而且你的卤味商店已经在用了。

---

## 一、先说清一个区别

| 你想要的 | 能不能做到 |
|---|---|
| **无穷子域名** `a.pulseos.com` `b.pulseos.com` | ❌ 做不到。GitHub Pages 没有通配 DNS |
| **无穷路径** `.../api.html#abc123` `.../api.html#def456` | ✅ **完全可行** |

**你说的是后者。** 上一次我拒绝的是子域名，这次不一样。

---

## 二、你原来的做法（我照抄的）

`luhuo/js/join.js:223`：

```js
const link = location.origin + location.pathname.replace(/[^/]*$/, '') +
  'admin.html#import=' + encodeURIComponent(b64);
```

**整个店铺配置 base64 后编进 URL hash。**

- 不需要数据库
- 不需要为每个商家部署一份
- 链接发给谁，谁就能打开自己的店
- 服务端成本 = 0

---

## 三、PulseOS 版本

新增 `instance.js`，把同样的模式用在能力清单上：

```
pulseos/api.html#<base64({
  label:      "张三的小店",
  gateway:    "https://zhang.trycloudflare.com/invoke",
  services:   ["counter", "echo"],
  allow:      ["invoke", "status"],
  clientRateLimit: 100
})>
```

### 实测三个实例

```
▸ 张三的小店
  URL 长度: 356
  ✓ 解码: gateway=https://zhang.trycloudflare.com/invoke
          services=counter,echo
          allow=invoke,status

▸ 李四的算力池
  URL 长度: 370
  ✓ 解码: gateway=https://li.trycloudflare.com/invoke
          services=全部
          allow=invoke,deploy,status,list_services

▸ 王五的演示（只读）
  URL 长度: 320
  ✓ 解码: gateway=(无，只读)
          allow=status,list_services
```

**站点文件：一份 `api.html`。**
**实例数量：无限（每个只是一个 URL 字符串）。**
**服务端成本：0。**

---

## 四、⚠️ 但必须说清：URL 里是配置，不是服务器

这是最重要的一条。

```
URL 里能装：  label / gateway 地址 / 服务白名单 / 能力白名单
URL 里装不：  一台真的服务器
```

所以：

| 场景 | 能做到吗 |
|---|---|
| 张三打开自己的链接，看到自己的菜单 | ✅ 能（纯前端） |
| 张三的链接指向张三自己的网关 | ✅ 能（URL 里写着地址） |
| 张三的链接能调通 | ⚠️ **要看张三的网关在不在线** |
| 生成 1000 个链接 | ✅ 能（0 成本） |
| 1000 个链接同时能调 | ❌ **需要 1000 个（或至少若干个）真的后端** |

**「无限扩充链接」是免费的。「无限扩充算力」不是。**

---

## 五、正确的商业形态

这才是这套模式真正的价值：

```
你（平台方）
  ├─ 提供 api.html（一份静态文件，永久免费托管）
  ├─ 提供 instance.js（编码/解码逻辑）
  └─ 提供 gateway.js（谁想跑谁自己跑）
       │
       ├─ 张三跑一份在自己电脑上 → 他的链接指向他的 Cloudflare Tunnel
       ├─ 李四跑一份在自己的 VPS 上 → 他的链接指向他的域名
       └─ 王五没有机器 → 他的链接是只读的，只能看菜单

每个用户 = 一个 URL + 一份自己的 gateway
你不需要买 IP、买域名、买服务器
```

**你提供的是「协议 + 工具」，不是「算力」。**

这跟你卤味商店的模式一模一样：
- 你不给每个商家开服务器
- 你给的是 `admin.html#import=...` 这个约定
- 商家自己决定数据放哪

---

## 六、代码

### 生成一个实例链接

```js
const I = require('./instance.js');

const url = I.makeUrl(
  'https://sandmanklepfer-crypto.github.io/0.5B-AGI-Lab/pulseos/api.html',
  {
    label: '张三的算力池',
    gateway: 'https://zhang.trycloudflare.com/invoke',
    services: ['counter', 'echo'],
    allow: ['invoke', 'status'],
    clientRateLimit: 100,
  }
);
// → 356 字节的 URL
```

### 页面里读实例

```js
const inst = PulseInstance.decode(location.hash);
// inst.label / inst.gateway / inst.services / inst.allow
```

### 页面上还有两个按钮

```
[复制此实例链接]   把当前 URL 复制走
[生成新实例]       随机 slug + 问网关地址 → 跳到新实例
```

---

## 七、能装多少东西进 URL

实测：

| 内容 | URL 长度 |
|---|---|
| 3 个字段（只读实例） | 320 字节 |
| 5 个字段 + 服务白名单 | 356 字节 |
| 7 个字段 + 能力白名单 | 370 字节 |

**浏览器 URL 上限约 2000~8000 字节（视浏览器）。**

按 370 字节算，还能塞 5 倍内容 —— 足够放：
- 更多服务名
- 自定义限速
- 甚至一小段 PulseScript 源码（如果短）

**但不要往 URL 里塞大数据。** 那违背了「控制面只传路牌」。

---

## 八、和「子域名」方案的真实对比

| | 无穷子域名 | **链接即实例** |
|---|---|---|
| 可行性 | ❌ 做不到 | ✅ 已实现 |
| 成本 | 每个域名要钱 | 0 |
| 配置在哪 | DNS 记录 | URL hash |
| 改动生效 | 等 DNS 生效 | 立刻 |
| 能否离线使用 | ❌ | ✅（文件:// 也能开） |
| 后端要求 | 必须每个都有 | 可以有也可以没有 |

**「链接即实例」不只是「退而求其次」，它在某些维度上比子域名更好。**

---

## 九、复现

```bash
# 看编码/解码
node -e "
const I=require('./instance.js');
const u=I.makeUrl('https://x/api.html',{label:'测试',gateway:null,services:['a'],allow:['status']});
console.log(u);
console.log(I.describe(I.decode(u.split('#')[1])));
"
```
