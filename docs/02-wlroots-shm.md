# 第二道墙：给 wlroots 加一条 SHM 输出路径

## 一、症状

Wayland socket 通了之后，合成器还是起不来：

```
renderer.buffer_caps = 0x2      (DMABUF)
allocator.caps       = 0x5      (DATA_PTR | SHM)
交集 = 0

renderer and allocator buffer capabilities don't match
```

## 二、根因

`wlroots/render/gles2/renderer.c`:

```c
static uint32_t gles2_get_render_buffer_caps(struct wlr_renderer *renderer) {
    return WLR_BUFFER_CAP_DMABUF;   // ← 只给 DMABUF
}
```

而 `get_or_create_buffer()` 里没有任何 SHM 分支：

```c
static struct wlr_gles2_buffer *get_or_create_buffer(...) {
    // 尝试 DMABUF
    ...
    goto error_buffer;   // ← SHM 走到这直接失败
}
```

**问题在于**：上游假设「既然你用 GLES2，就一定有 DMABUF」。
这个假设在正常 Linux 上成立（有 DRM render node），
**但在 Android 上，`/dev/dri/renderD128` 打不开，GLES2 只能拿到 SHM。**

## 三、四处改动

### 1. `include/render/gles2.h`

结构体加字段：

```c
struct wlr_gles2_buffer {
    ...
    bool is_shm;              // 是否是 SHM 路径
    GLuint shm_tex;           // 承载 SHM 数据的纹理
    void *shm_data;           // SHM 内存
    void *readback;           // glReadPixels 目标
    uint32_t shm_format;      // DRM fourcc
    size_t shm_stride;
};
```

### 2. `render/gles2/renderer.c` — 返回两个 cap

```c
static uint32_t gles2_get_render_buffer_caps(struct wlr_renderer *renderer) {
    return WLR_BUFFER_CAP_DMABUF | WLR_BUFFER_CAP_SHM;   // ← 加 SHM
}
```

### 3. `render/gles2/renderer.c` — SHM 分支

核心是**用纹理 + FBO 当作渲染目标**，不用 dmabuf：

```c
shm_path:
    buf->is_shm = true;
    buf->shm_format = ...;
    buf->shm_stride = ...;
    glGenTextures(1, &buf->shm_tex);
    glBindTexture(GL_TEXTURE_2D, buf->shm_tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                 GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    // 建 FBO 挂上去
    glGenFramebuffers(1, &buf->shm_fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, buf->shm_fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                           GL_TEXTURE_2D, buf->shm_tex, 0);
```

### 4. `render/gles2/pass.c` — 提交时读回

```c
void render_pass_submit(struct wlr_render_pass *render_pass) {
    ...
    if (buffer->is_shm) {
        glBindFramebuffer(GL_FRAMEBUFFER, buffer->shm_fbo);
        glReadPixels(0, 0, width, height, GL_RGBA, GL_UNSIGNED_BYTE,
                     buffer->readback);

        /* ★ 垂直翻转：GL 原点在左下，SHM 图像原点在左上 */
        for (int y = 0; y < height; y++) {
            memcpy(
                (char *)buffer->shm_data + y * buffer->shm_stride,
                (char *)buffer->readback + (height - 1 - y) * width * 4,
                width * 4
            );
        }
    }
    ...
}
```

**垂直翻转是必须的**。忘了这一步，画面会上下颠倒 —— 但不会报错，
所以你会盯着一个倒过来的桌面怀疑人生。

## 四、编译时的 4 个坑

### 坑 1：GLES2 头缺符号

```
error: 'GL_BGRA' undeclared
error: 'GL_RGBA8' undeclared
error: 'GL_PACK_ROW_LENGTH' undeclared
```

这些是桌面 GL 的常量，GLES2 头里没有。用等价值替代：

```c
#define GL_BGRA_EXT 0x80E1
/* GL_BGRA → GL_RGBA */
/* GL_RGBA8 → GL_RGBA */
```

### 坑 2：`-Dsession=disabled` 缺符号

```
undefined reference to `wlr_libinput_get_device_handle'
```

必须 `-Dsession=auto -Dbackends=auto`。

### 坑 3：`-Dxwayland=disabled` 缺 23 个符号

写桩文件 `types/tl_stubs.c`，**每个桩必须带完整原型**，
否则 `-Werror=missing-prototypes` 直接失败。

**但注意**：如果你后来又要开 xwayland，必须把这个桩文件删掉，
否则会 `multiple definition`（我们踩过这个）。

### 坑 4：缺依赖时精确定位

```bash
readelf --dyn-syms -W sway          | awk '$7=="UND" && $8 ~ /^wlr_/ {print $8}' | sort -u > need.txt
readelf --dyn-syms -W libwlroots.so | awk '$7!="UND" {print $8}' | sort -u > have.txt
comm -23 need.txt have.txt
```

这比看编译日志快十倍。

## 五、要装的 13 个 xcb dev 包

`-Dxwayland=enabled` 需要一堆 pkg-config 模块，缺一个就 configure 失败：

```bash
libxcb-icccm4-dev      libxcb-ewmh-dev        libxcb-xfixes0-dev
libxcb-util-dev        libxcb-image0-dev      libxcb-keysyms1-dev
libxcb-render-util0-dev libxcb-composite0-dev libxcb-shm0-dev
libxcb-render0-dev     libxcb-shape0-dev      libxcb-sync-dev
libxcb-dri3-dev        libxcb-present-dev     libxcb-xinput-dev
libxcb-randr0-dev      libxcb-glx0-dev        libxcb-res0-dev
libxcb-xinerama0-dev   libxcb-xkb-dev         libxcb-cursor-dev
libxcb-xtest0-dev      xwayland(提供 .pc)      hwdata(DRM 后端)
```

**注意 `xcb-xfixes.pc` 依赖 `xcb-shape`**，而 `xcb-composite.pc` 依赖 `xcb-xfixes` ——
装漏一个会导致 `Could not generate cflags`，报错信息完全不提缺的是哪个包。

## 六、编译命令

```bash
meson setup build --buildtype=release -Dexamples=false \
  -Dxwayland=enabled -Dsession=auto -Dbackends=auto -Drenderers=gles2
ninja -C build
```

## 七、验证

```
EGL driver name: zink
GL renderer: zink Vulkan 1.4(Adreno (TM) 825 (MESA_TURNIP))
Created SHM GL FBO for buffer 1440x696 (stride 5760)
Running compositor on wayland display 'wayland-2'
```

**像素级验证**（这才是真验证，不是「看起来对了」）：

```bash
swaybg -c '#1a1626' &                    # 纯色
grim /tmp/shot.png                       # 截图
python3 -c "
from PIL import Image
im = Image.open('/tmp/shot.png')
px = list(im.getdata())
target = (0x1a, 0x16, 0x26)
ok = sum(1 for p in px if p[:3] == target)
print(f'{ok}/{len(px)} pixels match')
"
# 1002240/1002240 pixels match
```

**1,002,240 个像素全部精确匹配。**
