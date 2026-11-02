# 第一道墙：SELinux 为什么拦 bind()

## 一、先看事实

```bash
$ ls -l /dev/dri/renderD128
crw-rw-rw- 1 root gpu  226, 128 /dev/dri/renderD128     # 权限是 666
$ python3 -c "open('/dev/dri/renderD128','rb')"
PermissionError: [Errno 13] Permission denied            # 还是拒绝
```

**权限位是 666，所有人可读写，但打开失败。**

这不是 Unix 权限问题。这是 SELinux 在 `open` 之后、返回 fd 之前拦下来的。

## 二、确认是 SELinux

```bash
$ id
uid=2000(shell) gid=2000(shell) groups=... context=u:r:shell:s0

$ getenforce
Enforcing
```

看审计日志（需要 root 才能读 `dmesg`，非 root 环境看不到，但可以看 logcat）：

```bash
$ logcat -d | grep avc
avc: denied { create } for scontext=u:r:shell:s0 \
    tcontext=u:object_r:system_file:s0 tclass=sock_file
```

**`tclass=sock_file`，`denied { create }`** —— 这就是 wayland `bind()` 失败的直接原因。

## 三、抽象 socket 为什么能过

Unix domain socket 有两种：

| 类型 | `sun_path[0]` | 是否落地成文件 | SELinux 标签 |
|---|---|---|---|
| 文件 socket | `'.'` 或 `'/'` | ✅ 是，有 inode | `sock_file`，受严格管控 |
| **抽象 socket** | `'\0'` | ❌ 否，只在内核 socket 表里 | 无文件标签，**策略通常不拦** |

抽象 socket 的名字存在内核的 socket 命名空间里，**不产生任何文件系统对象**。
所以：

- 不需要目录写权限
- 不会被 `sock_file` 策略拦
- `ls` 看不到，但 `ss` / `/proc/net/unix` 能看到

这正好是绕过 `sock_file` 限制的完美通道。

## 四、翻译算法必须两边一致

Wayland 的流程是：

```
服务端: bind("/run/user/1000/wayland-0")   → 变成 @TLWL:xxxxxxxx
客户端: connect("/run/user/1000/wayland-0") → 必须变成同一个 @TLWL:xxxxxxxx
```

两边用的是同一个 `fakesock.so`，所以只要**哈希函数一模一样**就能对上。

用 FNV-1a 而不是 MD5/SHA，原因很简单：**32 位、无依赖、编译进 .so 只要 6 行**。

```c
static unsigned int fnv1a(const char *s) {
    unsigned int h = 2166136261u;
    while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; }
    return h;
}
```

格式化成 8 位十六进制：

```c
snprintf(out.sun_path + 1, sizeof(out.sun_path) - 1, "TLWL:%08x", fnv1a(path));
```

**注意 `sun_path + 1`**：抽象 socket 的名字从 `sun_path[1]` 开始，`sun_path[0]` 必须是 `\0`。

## 五、踩过的坑

### 坑 1：`sizeof(out)` 而不是真实长度

```c
/* ❌ 错 */
return real_bind(fd, (struct sockaddr *)&out, sizeof(out));

/* ✅ 对 */
return real_bind(fd, (struct sockaddr *)&out,
                 offsetof(struct sockaddr_un, sun_path) + 1 + strlen(name));
```

传 `sizeof(out)` 会把 `sun_path` 后面一堆 `\0` 也算进名字里，
结果就是 `bind` 成功但 `connect` 找不到——因为名字尾部多了 90 个零字节。

**这个 bug 会让现象看起来像「服务端起来了，客户端连不上」，非常难查。**

### 坑 2：`strace` 看不到抽象名

`strace -e bind` 输出的是：

```
bind(3, {sa_family=AF_UNIX, sun_path=@TLWL:dffa372e}, 110) = 0
```

`@` 就是 `\0` 的显示形式。看到 `@` 才是对的，看到路径就是没劫持到。

### 坑 3：`LD_PRELOAD` 污染 bionic

Android 的 `/system/bin/*` 是 bionic 链接的，你的 `.so` 如果是 glibc 编译的：

```
CANNOT link executable 'sleep': library "libc.so.6" not found
```

**只在启动合成器那一条命令上挂 `LD_PRELOAD`**，或者用 wrapper 脚本隔离：

```sh
#!/bin/sh
LD_PRELOAD=/path/fakesock.so /usr/bin/sway "$@"
```

别 `export`。

## 六、验证清单

```bash
# 1. 抽象 socket 存在吗
grep "@" /proc/net/unix | sed 's/.*@/@/' | sort -u | grep TLWL

# 2. 服务端日志有输出吗
#    Running compositor on wayland display 'wayland-1'

# 3. 客户端能连吗
WAYLAND_DISPLAY=wayland-1 /usr/bin/weston-info    # 或者任何 wl 客户端

# 4. 如果 1 通过 3 失败 → 一定是哈希算法或 sockaddr 长度不一致
```
