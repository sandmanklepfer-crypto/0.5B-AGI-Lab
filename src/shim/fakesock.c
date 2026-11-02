/* fakesock.c —— Wayland socket 劫持层
 *
 * 目的：SELinux 拒绝在 shell 域创建文件系统 unix socket，
 *      但放行抽象 socket。这里把 wayland 的文件 socket 透明翻译成抽象 socket。
 *
 * 拦截：
 *   bind()    unix 文件路径 → 抽象命名空间（sun_path[0] = '\0'）
 *   connect() 同上，算法一致保证能连上
 *   listen()  不动
 *
 * 抽象名算法：前缀 "TLWL:" + FNV1a(路径) 的十六进制
 *   bind 和 connect 用同一算法，所以能对上。
 *
 * 编译：gcc -O2 -fPIC -shared -o fakesock.so fakesock.c -ldl
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <dlfcn.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <stdarg.h>

#define PREFIX "TLWL:"

__attribute__((constructor))
static void fakesock_init(void) {
    fprintf(stderr, "[fakesock] *** .so 已加载 pid=%d ***\n", getpid());
    const char *d = getenv("FAKESOCK_DEBUG");
    const char *r = getenv("FAKESOCK_DRM");
    fprintf(stderr, "[fakesock] DEBUG=%s DRM=%s\n", d?d:"(unset)", r?r:"(unset)");
}

static int g_debug = -1;

static void dbg(const char *fmt, ...) {
    if (g_debug < 0) {
        const char *e = getenv("FAKESOCK_DEBUG");
        g_debug = (e && *e == '1') ? 1 : 0;
    }
    if (!g_debug) return;
    va_list ap; va_start(ap, fmt);
    fprintf(stderr, "[fakesock] ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
}

/* FNV-1a 32bit */
static unsigned int fnv1a(const char *s) {
    unsigned int h = 2166136261u;
    while (*s) { h ^= (unsigned char)*s++; h *= 16777619u; }
    return h;
}

/* 把文件路径的 sockaddr_un 改写成抽象 socket */
static int to_abstract(const struct sockaddr_un *in, struct sockaddr_un *out,
                       socklen_t *outlen, const char *what) {
    if (in->sun_path[0] == '\0') {
        /* 已经是抽象 socket，不动 */
        return 0;
    }
    /* 只处理 unix 路径 socket */
    memset(out, 0, sizeof(*out));
    out->sun_family = AF_UNIX;
    snprintf(out->sun_path + 1, sizeof(out->sun_path) - 1,
             PREFIX "%08x", fnv1a(in->sun_path));
    *outlen = (socklen_t)(offsetof(struct sockaddr_un, sun_path) + 1 + strlen(out->sun_path + 1));
    dbg("%s: %s -> @%s", what, in->sun_path, out->sun_path + 1);
    return 1;
}

int bind(int fd, const struct sockaddr *addr, socklen_t len) {
    static int (*real)(int, const struct sockaddr *, socklen_t) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "bind");

    if (addr && addr->sa_family == AF_UNIX && len >= (socklen_t)sizeof(sa_family_t)) {
        const struct sockaddr_un *un = (const struct sockaddr_un *)addr;
        struct sockaddr_un na; socklen_t nl;
        if (to_abstract(un, &na, &nl, "bind")) {
            int r = real(fd, (const struct sockaddr *)&na, nl);
            dbg("bind -> rc=%d errno=%d", r, r ? errno : 0);
            return r;
        }
    }
    return real(fd, addr, len);
}

/* ---- shm_open 劫持：Android 没有可写 /dev/shm，改走 memfd_create ---- */
#include <sys/mman.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/syscall.h>

#ifndef MFD_CLOEXEC
#define MFD_CLOEXEC 0x0001U
#endif

int shm_open(const char *name, int oflag, mode_t mode) {
    static int (*real)(const char *, int, mode_t) = NULL;
    /* 先试真的 shm_open */
    if (!real) real = dlsym(RTLD_NEXT, "shm_open");
    if (real) {
        int fd = real(name, oflag, mode);
        if (fd >= 0) { dbg("shm_open(%s) real OK fd=%d", name, fd); return fd; }
    }
    /* 失败：用 memfd 代替（匿名共享内存，fd 语义完全一致） */
    int fd = (int)syscall(SYS_memfd_create, "tlshm", oflag & O_CLOEXEC ? MFD_CLOEXEC : 0);
    if (fd < 0) { dbg("memfd_create FAIL errno=%d", errno); return -1; }
    dbg("shm_open(%s) -> memfd fd=%d", name, fd);
    return fd;
}

int shm_unlink(const char *name) {
    static int (*real)(const char *) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "shm_unlink");
    if (real) { int r = real(name); if (r == 0) return 0; }
    return 0;   /* memfd 无需 unlink */
}


/* ============================================================
 *  DRM 劫持：让 wlroots 以为自己拿到了 /dev/dri/renderD128
 *  （这套代码在 vatcp.so 里已验证能让 libva-drm 接受假 fd）
 * ============================================================ */
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>

struct drm_version {
    int version_major, version_minor, version_patchlevel;
    size_t name_len; char *name;
    size_t date_len; char *date;
    size_t desc_len; char *desc;
};
struct drm_get_cap { unsigned long long capability, value; };
struct drm_unique { size_t unique_len; char *unique; };

#define DRM_IOCTL_VERSION        0xC0406400UL
#define DRM_IOCTL_GET_CAP        0xC010640CUL
#define DRM_IOCTL_GET_UNIQUE     0x80086401UL
#define DRM_IOCTL_SET_CLIENT_CAP 0x4010640DUL

static int g_fake_drm[512];
static void mark_drm(int fd) { if (fd >= 0 && fd < 512) g_fake_drm[fd] = 1; }
static int is_drm(int fd)    { return fd >= 0 && fd < 512 && g_fake_drm[fd]; }
static int is_dri_path(const char *p) {
    return p && strncmp(p, "/dev/dri/", 9) == 0;
}

static int g_open_drm = -1;
static int fake_drm_enabled(void) {
    if (g_open_drm < 0) {
        const char *e = getenv("FAKESOCK_DRM");
        g_open_drm = (!e || *e != '0') ? 1 : 0;   /* 默认开启 */
    }
    return g_open_drm;
}

int open(const char *path, int flags, ...) {
    static int (*real)(const char *, int, ...) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "open");
    va_list ap; va_start(ap, flags); mode_t m = va_arg(ap, mode_t); va_end(ap);
    if (getenv("FAKESOCK_LOGALL") && path && (strstr(path,"dri") || strstr(path,"sys/dev")))
        fprintf(stderr, "[fakesock] open(%s)\n", path);

    if (fake_drm_enabled() && is_dri_path(path)) {
        int fd = real("/dev/null", O_RDWR);
        if (fd >= 0) { mark_drm(fd); dbg("假DRM: %s -> /dev/null fd=%d", path, fd); return fd; }
    }
    return real(path, flags, m);
}

int open64(const char *path, int flags, ...) {
    static int (*real)(const char *, int, ...) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "open64");
    va_list ap; va_start(ap, flags); mode_t m = va_arg(ap, mode_t); va_end(ap);
    if (getenv("FAKESOCK_LOGALL") && path && (strstr(path,"dri") || strstr(path,"sys/dev")))
        fprintf(stderr, "[fakesock] open64(%s)\n", path);

    if (fake_drm_enabled() && is_dri_path(path)) {
        int fd = real("/dev/null", O_RDWR);
        if (fd >= 0) { mark_drm(fd); dbg("假DRM(open64): %s -> fd=%d", path, fd); return fd; }
    }
    return real(path, flags, m);
}

int __open64_2(const char *path, int flags) { return open64(path, flags); }

int openat(int dfd, const char *path, int flags, ...) {
    static int (*real)(int, const char *, int, ...) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "openat");
    va_list ap; va_start(ap, flags); mode_t m = va_arg(ap, mode_t); va_end(ap);
    if (fake_drm_enabled() && is_dri_path(path)) {
        int fd = real(AT_FDCWD, "/dev/null", O_RDWR);
        if (fd >= 0) { mark_drm(fd); dbg("假DRM(openat): %s -> fd=%d", path, fd); return fd; }
    }
    return real(dfd, path, flags, m);
}

int fstat(int fd, struct stat *st) {
    static int (*real)(int, struct stat *) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "fstat");
    int r = real(fd, st);
    if (r == 0 && is_drm(fd)) {
        st->st_rdev = makedev(226, 128);
        st->st_mode = (st->st_mode & ~S_IFMT) | S_IFCHR;
    }
    return r;
}


/* ---- 覆盖 libdrm 的设备枚举：直接返回一个假 render node ----
 * wlroots 0.17 的 open_drm_render_node() 调 drmGetDevices2()
 * 这里骗它：有 1 个 render node，路径 /dev/dri/renderD128
 */
#define DRM_NODE_PRIMARY 0
#define DRM_NODE_CONTROL 1
#define DRM_NODE_RENDER  2
#define DRM_BUS_VIRTUAL  5

struct _tl_drmDevice {
    char **nodes;
    int available_nodes;
    int bustype;
    union {
        struct { int pci_domain, pci_bus, pci_device, pci_func; } pci;
        struct { int type; } usb;
        struct { int type; } platform;
        struct { int type; } host1x;
        struct { int type; } virtual;
    } businfo;
    void *formats;
    int num_formats;
};
typedef struct _tl_drmDevice tl_drmDevice;
typedef tl_drmDevice *tl_drmDevicePtr;

int drmGetDevices2(unsigned int flags, tl_drmDevicePtr devices[], int max_devices) {
    (void)flags;
    fprintf(stderr, "[fakesock] drmGetDevices2(devices=%p max=%d) -> 1 fake\n",
            (void*)devices, max_devices);
    if (devices == NULL || max_devices <= 0) return 1;

    /* 用 malloc 分配，这样 libdrm 的 free 路径也能安全释放 */
    tl_drmDevice *d = calloc(1, sizeof(tl_drmDevice));
    if (!d) return -1;
    d->nodes = calloc(3, sizeof(char *));
    if (!d->nodes) { free(d); return -1; }
    d->nodes[0] = NULL;
    d->nodes[1] = NULL;
    d->nodes[2] = strdup("/dev/dri/renderD128");
    d->available_nodes = (1 << DRM_NODE_RENDER);
    d->bustype = DRM_BUS_VIRTUAL;
    d->formats = NULL;
    d->num_formats = 0;
    devices[0] = d;
    return 1;
}

int drmGetDevices(tl_drmDevicePtr devices[], int max_devices) {
    return drmGetDevices2(0, devices, max_devices);
}


/* ---- 覆盖 drmGetDevice2(fd, ...)：libdrm 检查假 fd 时返回 EINVAL ----
 * wlroots egl.c 用它来获取 dev_t，用于匹配 EGLDevice
 */
int drmGetDevice2(int fd, unsigned int flags, tl_drmDevicePtr *device) {
    (void)flags;
    fprintf(stderr, "[fakesock] drmGetDevice2(fd=%d) -> fake device\n", fd);
    if (!device) return -1;
    tl_drmDevice *d = calloc(1, sizeof(tl_drmDevice));
    if (!d) return -1;
    d->nodes = calloc(3, sizeof(char *));
    if (!d->nodes) { free(d); return -1; }
    d->nodes[0] = NULL;
    d->nodes[1] = NULL;
    d->nodes[2] = strdup("/dev/dri/renderD128");
    d->available_nodes = (1 << DRM_NODE_RENDER);
    d->bustype = DRM_BUS_VIRTUAL;
    *device = d;
    return 0;
}

int drmGetDevice(int fd, tl_drmDevicePtr *device) {
    return drmGetDevice2(fd, 0, device);
}

/* wlroots 用它拿 "primary" 设备名；给个 render 名字即可 */
int drmGetPrimaryDeviceNameFromFd(int fd, char **name) {
    fprintf(stderr, "[fakesock] drmGetPrimaryDeviceNameFromFd(fd=%d)\n", fd);
    if (!name) return -1;
    *name = strdup("/dev/dri/renderD128");
    return 0;
}

/* 有时 libdrm 用这个 */
int drmGetRenderDeviceNameFromFd(int fd, char **name) {
    fprintf(stderr, "[fakesock] drmGetRenderDeviceNameFromFd(fd=%d)\n", fd);
    if (!name) return -1;
    *name = strdup("/dev/dri/renderD128");
    return 0;
}

void drmFreeDevice(tl_drmDevicePtr *device) {
    if (!device || !*device) return;
    tl_drmDevice *d = *device;
    if (d->nodes) {
        for (int i = 0; i < 3; i++) free(d->nodes[i]);
        free(d->nodes);
    }
    free(d);
    *device = NULL;
}

void drmFreeDevices(tl_drmDevicePtr devices[], int count) {
    if (!devices) return;
    for (int i = 0; i < count; i++) {
        if (devices[i]) {
            tl_drmDevice *d = devices[i];
            if (d->nodes) {
                for (int j = 0; j < 3; j++) free(d->nodes[j]);
                free(d->nodes);
            }
            free(d);
            devices[i] = NULL;
        }
    }
}

/* libdrm 靠这个判断节点类型；直接返回 RENDER */
int drmGetNodeTypeFromFd(int fd) {
    dbg("drmGetNodeTypeFromFd(%d) -> 2(RENDER)", fd);
    return 2;
}

int ioctl(int fd, unsigned long req, ...) {
    static int (*real)(int, unsigned long, ...) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "ioctl");
    va_list ap; va_start(ap, req); void *arg = va_arg(ap, void *); va_end(ap);

    if (is_drm(fd)) {
        if (req == DRM_IOCTL_VERSION && arg) {
            struct drm_version *v = arg;
            static char nm[] = "kgsl";
            static char dt[] = "20260101";
            static char ds[] = "TL fake drm for wlroots";
            size_t nl = strlen(nm), dl = strlen(dt), sl = strlen(ds);
            if (v->name && v->name_len >= nl) memcpy(v->name, nm, nl);
            if (v->date && v->date_len >= dl) memcpy(v->date, dt, dl);
            if (v->desc && v->desc_len >= sl) memcpy(v->desc, ds, sl);
            v->name_len = nl; v->date_len = dl; v->desc_len = sl;
            v->version_major = 1; v->version_minor = 0; v->version_patchlevel = 0;
            return 0;
        }
        if (req == DRM_IOCTL_GET_UNIQUE && arg) {
            struct drm_unique *u = arg;
            static char uq[] = "fake:bus=0";
            if (u->unique && u->unique_len >= sizeof(uq)) memcpy(u->unique, uq, sizeof(uq));
            u->unique_len = sizeof(uq);
            return 0;
        }
        if (req == DRM_IOCTL_GET_CAP && arg) {
            ((struct drm_get_cap *)arg)->value = 0;
            return 0;
        }
        if (req == DRM_IOCTL_SET_CLIENT_CAP) return 0;
        if (fake_drm_enabled()) {
            dbg("ioctl(fd=%d req=0x%lx) 假fd->返回0", fd, req);
            return 0;
        }
        dbg("ioctl(fd=%d req=0x%lx) 未拦截，交给内核", fd, req);
    }
    return real(fd, req, arg);
}


/* ---- 路径重定向：/usr/libexec/xxx -> $TL_ROOT/usr/libexec/xxx ----
 * weston 用绝对路径 exec 子进程，原生运行时找不到容器内文件
 */
static const char *g_tlroot = NULL;
static char g_pathbuf[1024];

static const char *map_path(const char *p) {
    if (!p) return p;
    if (g_tlroot == NULL) g_tlroot = getenv("TL_ROOT");
    if (!g_tlroot || !*g_tlroot) return p;
    if (strncmp(p, g_tlroot, strlen(g_tlroot)) == 0) return p;
    /* 只重定向这几个前缀 */
    if (strncmp(p, "/usr/libexec/", 13) == 0 ||
        strncmp(p, "/usr/lib/weston/", 16) == 0 ||
        strncmp(p, "/usr/bin/", 9) == 0 ||
        strncmp(p, "/usr/share/", 11) == 0) {
        snprintf(g_pathbuf, sizeof g_pathbuf, "%s%s", g_tlroot, p);
        return g_pathbuf;
    }
    return p;
}

int execv(const char *path, char *const argv[]) {
    static int (*real)(const char *, char *const []) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "execv");
    const char *np = map_path(path);
    if (np != path) fprintf(stderr, "[fakesock] execv: %s -> %s\n", path, np);
    return real(np, argv);
}

int execve(const char *path, char *const argv[], char *const envp[]) {
    static int (*real)(const char *, char *const [], char *const []) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "execve");
    const char *np = map_path(path);
    if (np != path) fprintf(stderr, "[fakesock] execve: %s -> %s\n", path, np);
    return real(np, argv, envp);
}

int execvp(const char *file, char *const argv[]) {
    static int (*real)(const char *, char *const []) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "execvp");
    const char *np = map_path(file);
    if (np != file) fprintf(stderr, "[fakesock] execvp: %s -> %s\n", file, np);
    return real(np, argv);
}


#include <spawn.h>
extern char **environ;

int posix_spawn(pid_t *pid, const char *path,
                const posix_spawn_file_actions_t *fa,
                const posix_spawnattr_t *attr,
                char *const argv[], char *const envp[]) {
    static int (*real)(pid_t*, const char*, const posix_spawn_file_actions_t*,
                       const posix_spawnattr_t*, char *const[], char *const[]) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "posix_spawn");
    const char *np = map_path(path);
    if (np != path) fprintf(stderr, "[fakesock] posix_spawn: %s -> %s\n", path, np);
    return real(pid, np, fa, attr, argv, envp);
}

int posix_spawnp(pid_t *pid, const char *file,
                 const posix_spawn_file_actions_t *fa,
                 const posix_spawnattr_t *attr,
                 char *const argv[], char *const envp[]) {
    static int (*real)(pid_t*, const char*, const posix_spawn_file_actions_t*,
                       const posix_spawnattr_t*, char *const[], char *const[]) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "posix_spawnp");
    const char *np = map_path(file);
    if (np != file) fprintf(stderr, "[fakesock] posix_spawnp: %s -> %s\n", file, np);
    return real(pid, np, fa, attr, argv, envp);
}

int execvpe(const char *file, char *const argv[], char *const envp[]) {
    static int (*real)(const char *, char *const [], char *const []) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "execvpe");
    const char *np = map_path(file);
    if (np != file) fprintf(stderr, "[fakesock] execvpe: %s -> %s\n", file, np);
    return real(np, argv, envp);
}

int execl(const char *path, const char *arg0, ...) {
    static int (*real)(const char *, const char *, ...) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "execl");
    const char *np = map_path(path);

    /* execl 是变参，必须收集所有参数再转给 execv */
    va_list ap, ap2;
    va_start(ap, arg0);
    va_copy(ap2, ap);
    int argc = 1;
    while (va_arg(ap, char *) != NULL) argc++;
    va_end(ap);

    char **argv = (char **)calloc((size_t)argc + 1, sizeof(char *));
    if (!argv) { va_end(ap2); return -1; }
    argv[0] = (char *)arg0;
    for (int i = 1; i < argc; i++) argv[i] = va_arg(ap2, char *);
    argv[argc] = NULL;
    va_end(ap2);

    if (np != path) fprintf(stderr, "[fakesock] execl: %s -> %s\n", path, np);
    extern char **environ;
    int r = execve(np, argv, environ);
    free(argv);
    return r;
}


/* ============================================================
 *  ★ 核心：把 wlroots 的 EGL 初始化改走 SURFACELESS 平台
 *  原实现 gbm_create_device(drm_fd) 需要真 DRM，这里完全跳过
 * ============================================================ */
typedef void *EGLDisplay_t;
typedef void *EGLContext_t;
typedef void *EGLConfig_t;

#define EGL_NO_DISPLAY_   ((void*)0)
#define EGL_NO_CONTEXT_   ((void*)0)
#define EGL_NO_CONFIG_    ((void*)0)
#define EGL_DEFAULT_DISPLAY_ ((void*)0)
#define EGL_PLATFORM_SURFACELESS_MESA_ 0x31DD
#define EGL_OPENGL_ES_API_ 0x30A0
#define EGL_NONE_ 0x3038
#define EGL_CONTEXT_CLIENT_VERSION_ 0x3098

struct wlr_egl;

static uint32_t tl_get_render_caps(void *r) {
    (void)r;
    return 0x4;   /* WLR_BUFFER_CAP_SHM */
}

struct wlr_egl *wlr_egl_create_with_drm_fd(int drm_fd) {
    static struct wlr_egl *(*real_ctx)(EGLDisplay_t, EGLContext_t) = NULL;
    if (!real_ctx) real_ctx = dlsym(RTLD_NEXT, "wlr_egl_create_with_context");

    fprintf(stderr, "[fakesock] *** wlr_egl_create_with_drm_fd(%d) 被劫持 -> surfaceless ***\n", drm_fd);

    void *h = dlopen("libEGL.so.1", RTLD_NOW | RTLD_GLOBAL);
    if (!h) h = dlopen("/usr/lib/aarch64-linux-gnu/libEGL.so.1", RTLD_NOW | RTLD_GLOBAL);
    if (!h) { fprintf(stderr, "[fakesock] dlopen libEGL 失败\n"); return NULL; }

    EGLDisplay_t (*pGetPd)(unsigned int, void *, const int *) =
        (void*)dlsym(h, "eglGetPlatformDisplay");
    int (*pInit)(EGLDisplay_t, int *, int *) = (void*)dlsym(h, "eglInitialize");
    int (*pBindApi)(unsigned int) = (void*)dlsym(h, "eglBindAPI");
    EGLContext_t (*pCreateCtx)(EGLDisplay_t, EGLConfig_t, EGLContext_t, const int *) =
        (void*)dlsym(h, "eglCreateContext");
    int (*pGetError)(void) = (void*)dlsym(h, "eglGetError");

    if (!pGetPd) {
        void *(*pGetProc)(const char*) = (void*)dlsym(h, "eglGetProcAddress");
        if (pGetProc) pGetPd = (void*)pGetProc("eglGetPlatformDisplayEXT");
    }
    if (!pGetPd || !pInit) { fprintf(stderr, "[fakesock] 缺 EGL 函数\n"); return NULL; }

    EGLDisplay_t dpy = pGetPd(EGL_PLATFORM_SURFACELESS_MESA_, EGL_DEFAULT_DISPLAY_, NULL);
    if (!dpy) { fprintf(stderr, "[fakesock] eglGetPlatformDisplay 返回 nil\n"); return NULL; }

    int maj = 0, min = 0;
    if (!pInit(dpy, &maj, &min)) {
        fprintf(stderr, "[fakesock] eglInitialize 失败 err=0x%x\n", pGetError ? pGetError() : 0);
        return NULL;
    }
    fprintf(stderr, "[fakesock] EGL surfaceless %d.%d\n", maj, min);
    pBindApi(EGL_OPENGL_ES_API_);

    int ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION_, 2, EGL_NONE_ };
    EGLContext_t ctx = pCreateCtx(dpy, EGL_NO_CONFIG_, EGL_NO_CONTEXT_, ctx_attr);
    if (!ctx) {
        fprintf(stderr, "[fakesock] eglCreateContext 失败 err=0x%x\n", pGetError ? pGetError() : 0);
        return NULL;
    }
    fprintf(stderr, "[fakesock] GLES2 context 创建成功，交给 wlroots\n");

    if (!real_ctx) { fprintf(stderr, "[fakesock] 找不到 wlr_egl_create_with_context\n"); return NULL; }
    struct wlr_egl *r = real_ctx(dpy, ctx);
    fprintf(stderr, "[fakesock] wlr_egl = %p\n", (void*)r);
    return r;
}


/* ============================================================
 *  ★★ 真正生效的劫持：wlr_renderer_autocreate()
 *  sway 调用它（跨库，走 PLT，可被 LD_PRELOAD 覆盖）
 *  我们完全跳过 DRM/GBM，走 EGL_PLATFORM_SURFACELESS_MESA
 * ============================================================ */
static void *g_egl_h = NULL;
static void *egl_sym(const char *n) {
    if (!g_egl_h) {
        g_egl_h = dlopen("libEGL.so.1", RTLD_NOW | RTLD_GLOBAL);
        if (!g_egl_h) g_egl_h = dlopen("/usr/lib/aarch64-linux-gnu/libEGL.so.1", RTLD_NOW|RTLD_GLOBAL);
    }
    return g_egl_h ? dlsym(g_egl_h, n) : NULL;
}

struct wlr_renderer *wlr_renderer_autocreate(void *backend) {
    (void)backend;
    fprintf(stderr, "[fakesock] *** wlr_renderer_autocreate 劫持生效，走 surfaceless ***\n");

    /* 1) surfaceless EGL display */
    EGLDisplay_t (*pGetPd)(unsigned int, void *, const int *) =
        egl_sym("eglGetPlatformDisplay");
    if (!pGetPd) {
        void *(*pGP)(const char*) = egl_sym("eglGetProcAddress");
        if (pGP) pGetPd = (void*)pGP("eglGetPlatformDisplayEXT");
    }
    int (*pInit)(EGLDisplay_t, int*, int*) = egl_sym("eglInitialize");
    int (*pBind)(unsigned int) = egl_sym("eglBindAPI");
    EGLContext_t (*pCtx)(EGLDisplay_t, EGLConfig_t, EGLContext_t, const int*) = egl_sym("eglCreateContext");
    int (*pErr)(void) = egl_sym("eglGetError");
    if (!pGetPd || !pInit || !pCtx) { fprintf(stderr, "[fakesock] EGL 符号缺失\n"); return NULL; }

    EGLDisplay_t dpy = pGetPd(EGL_PLATFORM_SURFACELESS_MESA_, EGL_DEFAULT_DISPLAY_, NULL);
    if (!dpy) { fprintf(stderr, "[fakesock] surfaceless display = nil\n"); return NULL; }
    int maj=0, min=0;
    if (!pInit(dpy, &maj, &min)) {
        fprintf(stderr, "[fakesock] eglInitialize 失败 0x%x\n", pErr?pErr():0); return NULL;
    }
    fprintf(stderr, "[fakesock] EGL %d.%d surfaceless OK\n", maj, min);
    if (pBind) pBind(EGL_OPENGL_ES_API_);
    int ca[] = { EGL_CONTEXT_CLIENT_VERSION_, 2, EGL_NONE_ };
    EGLContext_t ctx = pCtx(dpy, EGL_NO_CONFIG_, EGL_NO_CONTEXT_, ca);
    if (!ctx) { fprintf(stderr, "[fakesock] eglCreateContext 失败 0x%x\n", pErr?pErr():0); return NULL; }
    fprintf(stderr, "[fakesock] GLES2 context OK\n");

    /* 2) 包装成 wlr_egl */
    struct wlr_egl *(*pEglCtx)(EGLDisplay_t, EGLContext_t) =
        dlsym(RTLD_NEXT, "wlr_egl_create_with_context");
    if (!pEglCtx) { fprintf(stderr, "[fakesock] 无 wlr_egl_create_with_context\n"); return NULL; }
    struct wlr_egl *egl = pEglCtx(dpy, ctx);
    if (!egl) { fprintf(stderr, "[fakesock] wlr_egl = NULL\n"); return NULL; }
    fprintf(stderr, "[fakesock] wlr_egl=%p\n", (void*)egl);

    /* 3) 造 GLES2 renderer */
    struct wlr_renderer *(*pRend)(struct wlr_egl *) =
        dlsym(RTLD_NEXT, "wlr_gles2_renderer_create");
    if (!pRend) { fprintf(stderr, "[fakesock] 无 wlr_gles2_renderer_create\n"); return NULL; }
    struct wlr_renderer *r = pRend(egl);
    fprintf(stderr, "[fakesock] *** renderer = %p ***\n", (void*)r);

    /* 按真实结构定位：renderer->impl (offset 32)，impl->get_render_buffer_caps (offset 112) */
    if (r) {
        void *impl = *(void **)((char *)r + 32);
        fprintf(stderr, "[fakesock] renderer=%p impl=%p\n", (void*)r, impl);
        if (impl) {
            uint32_t (*pCaps)(void *) = *(uint32_t (**)(void *))((char *)impl + 112);
            fprintf(stderr, "[fakesock] get_render_buffer_caps fn=%p\n", (void*)pCaps);
            if (pCaps) {
                uint32_t c = pCaps(r);
                fprintf(stderr, "[fakesock] renderer.buffer_caps 原值 = 0x%x\n", c);
                /* mprotect 后替换函数指针，强制返回 SHM */
                long pg = sysconf(_SC_PAGESIZE);
                uintptr_t base = (uintptr_t)((char *)impl + 112) & ~(uintptr_t)(pg - 1);
                if (mprotect((void *)base, (size_t)pg, PROT_READ|PROT_WRITE) == 0) {
                    *(void **)((char *)impl + 112) = (void *)tl_get_render_caps;
                    mprotect((void *)base, (size_t)pg, PROT_READ);
                    fprintf(stderr, "[fakesock] ★ 已替换 get_render_buffer_caps -> 返回 0x4(SHM) ★\n");
                } else {
                    fprintf(stderr, "[fakesock] mprotect 失败 errno=%d\n", errno);
                }
            }
        }
    }
    return r;
}


/* ★ 强制用 shm allocator，绕开 gbm/DRM */
struct wlr_allocator *wlr_allocator_autocreate(void *backend, void *renderer) {
    (void)backend;
    fprintf(stderr, "[fakesock] *** wlr_allocator_autocreate 劫持 -> shm ***\n");
    struct wlr_allocator *(*pShm)(void) = dlsym(RTLD_NEXT, "wlr_shm_allocator_create");
    if (!pShm) { fprintf(stderr, "[fakesock] 无 wlr_shm_allocator_create\n"); return NULL; }
    struct wlr_allocator *a = pShm();
    fprintf(stderr, "[fakesock] shm allocator = %p\n", (void*)a);
    if (a) {
        uint32_t *w = (uint32_t *)a;
        /* offset 8 = u32[2] = buffer_caps */
        fprintf(stderr, "[fakesock] allocator.caps = 0x%x (不改)\n", w[2]);
    }
    return a;
}

int connect(int fd, const struct sockaddr *addr, socklen_t len) {
    static int (*real)(int, const struct sockaddr *, socklen_t) = NULL;
    if (!real) real = dlsym(RTLD_NEXT, "connect");

    if (addr && addr->sa_family == AF_UNIX && len >= (socklen_t)sizeof(sa_family_t)) {
        const struct sockaddr_un *un = (const struct sockaddr_un *)addr;
        struct sockaddr_un na; socklen_t nl;
        if (to_abstract(un, &na, &nl, "connect")) {
            int r = real(fd, (const struct sockaddr *)&na, nl);
            dbg("connect -> rc=%d errno=%d", r, r ? errno : 0);
            return r;
        }
    }
    return real(fd, addr, len);
}
