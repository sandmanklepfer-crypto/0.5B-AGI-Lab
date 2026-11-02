# 把画面送上屏：从 5.7 fps 到 28.8 fps

## 一、最初的笨办法

```bash
grim /tmp/shot.png        # 102 / 110 / 119 ms
ppm2xwd shot.png out.xwd  # 56 / 75 / 62 ms
```

合计约 **175ms/帧 = 5.7 fps**。桌面动一下要等两秒，像在看幻灯片。

**根本原因不是转换慢，是每次都要重新建立 wl_display 连接、
重新 bind shm、重新协商格式。** 每次截图都是一次完整握手。

## 二、改成常驻客户端

写一个长连的 `wlr-screencopy` 客户端：**一次连接，持续出帧**。

```
grabber: fps=28.8  total=144
grabber: fps=28.2  total=283
grabber: fps=28.8  total=434
```

**4.7 倍提升，硬件没换，只换架构。**

## 三、四个必须踩的坑

### 坑 1：格式是 DRM fourcc，不是 wl_shm 枚举

监听 `frame.buffer` 事件拿到的 `format` 字段是 **DRM fourcc**：

```
fmt=0x34324241
```

这不是乱码，是 `DRM_FORMAT_ABGR8888`（ASCII `'AB24'` 的字节序反写）。

**写死 `WL_SHM_FORMAT_XRGB8888` 的后果：**

```
error 1: invalid buffer format
```

因为 wl_shm 的枚举值和 DRM fourcc **完全不是一个命名空间**。

正确做法：直接用 compositor 广播过来的 fourcc 值，别自己猜。

### 坑 2：`capture_output` 的 output 参数不能传 NULL

```c
/* ❌ 错 */
zwlr_screencopy_manager_v1_capture_output(manager, 0, NULL);

/* ✅ 对 */
zwlr_screencopy_manager_v1_capture_output(manager, 0, output);
```

传 NULL 会得到：

```
error marshalling arguments (signature nio)
```

这个报错看不出根因。必须先用 `wl_registry` bind 一个 `wl_output` 对象，
再把它的 id 传进去。

### 坑 3：必须先等 `frame.buffer` 事件

时序不能错：

```
capture_output()
    ↓
[等 frame.buffer 事件]     ← 必须等这一步
    ↓
拿到 fd / stride / format
    ↓
建 wl_buffer
    ↓
mmap → 拿到像素
```

提前建 `wl_buffer` 会拿到无效参数。

### 坑 4：日志全丢 → `setvbuf`

重定向到文件时，`stderr` 默认是全缓冲。进程被杀 →

```c
setvbuf(stderr, NULL, _IONBF, 0);   // 一行救回所有调试信息
```

## 四、每帧新建 pool 但复用底层 memfd

`wl_shm_pool` 本身很轻，但 `shm_open` + `memfd_create` 是系统调用。
**复用底层 fd，只重建 pool 对象**：

```c
/* 第一次：建 memfd */
if (shm_fd < 0) {
    shm_fd = memfd_create("grab", MFD_CLOEXEC);
    ftruncate(shm_fd, size);
}

/* 每帧：只重建 pool */
struct wl_shm_pool *pool = wl_shm_create_pool(shm, shm_fd, size);
struct wl_buffer *buf = wl_shm_pool_create_buffer(pool, 0, w, h, stride, fmt);
wl_shm_pool_destroy(pool);
```

## 五、像素格式转换

| 来源格式 | 内存序 | XWD 需要 | 怎么转 |
|---|---|---|---|
| `DRM_FORMAT_ABGR8888` | R,G,B,A | B,G,R,X | **要 swap** |
| `DRM_FORMAT_XRGB8888` | B,G,R,X | B,G,R,X | **整块 memcpy** |

所以优先协商 `XRGB8888`，能省掉每帧一次全屏 swap。

## 六、编译

```bash
wayland-scanner client-header \
  /usr/share/wlr-protocols/unstable/wlr-screencopy-unstable-v1.xml \
  wlr-screencopy-client.h
wayland-scanner private-code \
  /usr/share/wlr-protocols/unstable/wlr-screencopy-unstable-v1.xml \
  wlr-screencopy-code.c

gcc -O2 -o grabber grabber.c wlr-screencopy-code.c \
    -lwayland-client -lrt
```

## 七、用法

```bash
LD_PRELOAD=/path/fakesock.so \
XDG_RUNTIME_DIR=/tmp/xdg \
WAYLAND_DISPLAY=wayland-1 \
./grabber 0 /sdcard/fbdir/Xvfb_screen0
```

输出是 XWD 格式，Android 侧 `TLHome` 直接 mmap 读：

```
offset 0    .. 159     header
offset 160  .. 3231    colormap (256 × 12)
offset 3232 ..         pixels: 1440×696×4, LSBFirst 32bpp, B,G,R,X
```

## 八、为什么不用 `wlr-export-dmabuf`

因为 Android 上没有 DRM render node，拿不到 dmabuf fd。
`wlr-screencopy` 走 SHM，配合第一章的 `shm_open → memfd_create` 劫持，
是**唯一可行的路径**。

这也是为什么必须先打 wlroots 的 SHM 补丁（见 `02-wlroots-shm.md`）——
两个问题是同一条链上的前后环。
