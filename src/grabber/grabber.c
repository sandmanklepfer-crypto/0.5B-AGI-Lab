/* grabber.c —— 常驻 wlr-screencopy 抓帧器
 *
 * 相比 grim 每帧重启：
 *   - 只连一次 wayland
 *   - 循环 capture，直接转 BGRX 写 Xvfb_screen0
 *   - 不经过 PPM 文件中转（省 3MB 写 + 3MB 读）
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <time.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <wayland-client.h>
#include "wlr-screencopy-client.h"

#define OUT_W 1440
#define OUT_H 696
#define PIX_OFF 3232
#define NPIX ((size_t)OUT_W * OUT_H)

static struct wl_display *dpy;
static struct wl_shm *shm;
static struct wl_output *output;
static struct zwlr_screencopy_manager_v1 *scm;

/* shm 池：复用，不每帧重建 */
struct pool {
    int fd;
    size_t size;
    void *data;
    struct wl_shm_pool *wlpool;
    uint32_t stride;
    uint32_t fmt;
    uint32_t h;
};
static struct pool g_pool = { -1, 0, NULL, NULL };

static int g_done = 0, g_failed = 0;
static int g_got_buffer = 0;          /* 收到 buffer 事件 */
static uint32_t g_fmt = 0, g_stride = 0, g_h = 0;
static unsigned char *g_bgrx = NULL;   /* 转换后缓冲 */
static int g_buf_fd = -1;
static long g_frames = 0;

static void reg_global(void *d, struct wl_registry *r, uint32_t name,
                       const char *iface, uint32_t ver) {
    (void)d; (void)ver;
    if (!strcmp(iface, "wl_shm"))
        shm = wl_registry_bind(r, name, &wl_shm_interface, 1);
    else if (!strcmp(iface, "wl_output") && !output)
        output = wl_registry_bind(r, name, &wl_output_interface, 1);
    else if (!strcmp(iface, "zwlr_screencopy_manager_v1"))
        scm = wl_registry_bind(r, name, &zwlr_screencopy_manager_v1_interface, 1);
}
static void reg_rm(void *d, struct wl_registry *r, uint32_t n){(void)d;(void)r;(void)n;}
static const struct wl_registry_listener regl = { reg_global, reg_rm };

static int pool_init(size_t size) {
    if (g_pool.data && g_pool.size >= size) return 0;
    if (g_pool.data) { munmap(g_pool.data, g_pool.size); g_pool.data = NULL; }
    if (g_pool.wlpool) { wl_shm_pool_destroy(g_pool.wlpool); g_pool.wlpool = NULL; }
    if (g_pool.fd >= 0) { close(g_pool.fd); g_pool.fd = -1; }

    g_pool.fd = memfd_create("grabframe", MFD_CLOEXEC);
    if (g_pool.fd < 0) { perror("memfd_create"); return -1; }
    if (ftruncate(g_pool.fd, (off_t)size) < 0) { perror("ftruncate"); return -1; }
    g_pool.data = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, g_pool.fd, 0);
    if (g_pool.data == MAP_FAILED) { perror("mmap"); g_pool.data = NULL; return -1; }
    g_pool.size = size;
    g_pool.wlpool = wl_shm_create_pool(shm, g_pool.fd, (int32_t)size);
    if (!g_pool.wlpool) { fprintf(stderr, "wl_shm_create_pool 失败\n"); return -1; }
    return 0;
}

static void frame_buffer(void *data, struct zwlr_screencopy_frame_v1 *f,
                         uint32_t format, uint32_t w, uint32_t h, uint32_t stride) {
    (void)f; (void)data;
    if (w != OUT_W || h != OUT_H) {
        fprintf(stderr, "尺寸不符: %ux%u\n", w, h);
        g_failed = 1; return;
    }
    g_fmt = format; g_stride = stride; g_h = h;
    if (pool_init((size_t)stride * h) != 0) { g_failed = 1; return; }
    g_got_buffer = 1;
    fprintf(stderr, "[grab] buffer evt: fmt=0x%x stride=%u %ux%u (frame %ld)\n",
            format, stride, w, h, g_frames);
}

static void frame_flags(void *d, struct zwlr_screencopy_frame_v1 *f, uint32_t fl) {
    (void)d; (void)f; (void)fl;
}

static void frame_ready(void *d, struct zwlr_screencopy_frame_v1 *f,
                        uint32_t sec_hi, uint32_t sec_lo, uint32_t nsec) {
    (void)d; (void)f; (void)sec_hi; (void)sec_lo; (void)nsec;
    g_done = 1;
}

static void frame_failed(void *d, struct zwlr_screencopy_frame_v1 *f) {
    (void)d; (void)f; g_failed = 1;
}

static void frame_damage(void *d, struct zwlr_screencopy_frame_v1 *f,
                         int32_t x, int32_t y, int32_t w, int32_t h) {
    (void)d; (void)f; (void)x; (void)y; (void)w; (void)h;
}

static void frame_linux_dmabuf(void *d, struct zwlr_screencopy_frame_v1 *f,
                               uint32_t fmt, uint32_t w, uint32_t h) {
    (void)d; (void)f; (void)fmt; (void)w; (void)h;
}

static void frame_buffer_done(void *d, struct zwlr_screencopy_frame_v1 *f) {
    (void)d; (void)f;
}

static const struct zwlr_screencopy_frame_v1_listener frame_listener = {
    .buffer = frame_buffer,
    .flags = frame_flags,
    .ready = frame_ready,
    .failed = frame_failed,
    .damage = frame_damage,
    .linux_dmabuf = frame_linux_dmabuf,
    .buffer_done = frame_buffer_done,
};

/* PPM 输出（调试用） */
static int save_ppm(const char *path) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fprintf(f, "P6\n%d %d\n255\n", OUT_W, OUT_H);
    unsigned char *src = g_pool.data;
    size_t stride = g_pool.stride;
    for (int y = 0; y < OUT_H; y++) {
        unsigned char *row = src + (size_t)y * stride;
        for (int x = 0; x < OUT_W; x++) {
            fputc(row[x*4+2], f); fputc(row[x*4+1], f); fputc(row[x*4+0], f);
        }
    }
    fclose(f);
    return 0;
}

int main(int argc, char **argv) {
    int secs = (argc > 1) ? atoi(argv[1]) : 0;   // 0 = 无限
    const char *out = (argc > 2) ? argv[2] : "/sdcard/fbdir/Xvfb_screen0";
    int save_dbg = (argc > 3);

    setvbuf(stderr, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);

    dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "连不上 wayland\n"); return 1; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &regl, NULL);
    wl_display_roundtrip(dpy);
    wl_display_roundtrip(dpy);
    if (!shm || !scm) { fprintf(stderr, "缺 wl_shm 或 screencopy_manager\n"); return 1; }
    if (!output) { fprintf(stderr, "缺 wl_output\n"); return 1; }

    g_bgrx = malloc(NPIX * 4);
    if (!g_bgrx) return 1;
    g_buf_fd = open(out, O_WRONLY);
    if (g_buf_fd < 0) { fprintf(stderr, "打不开 %s: %s\n", out, strerror(errno)); return 1; }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    double last_report = 0;

    for (;;) {
        g_done = g_failed = 0;
        g_got_buffer = 0;

        struct zwlr_screencopy_frame_v1 *fr =
            zwlr_screencopy_manager_v1_capture_output(scm, 0, output);
        zwlr_screencopy_frame_v1_add_listener(fr, &frame_listener, NULL);

        // 等 buffer 事件（拿到 stride/format）
        while (!g_failed && !g_got_buffer) {
            if (wl_display_dispatch(dpy) < 0) { fprintf(stderr, "dispatch 失败\n"); return 1; }
        }
        if (g_failed) { zwlr_screencopy_frame_v1_destroy(fr); usleep(50000); continue; }

        struct wl_shm_pool *pool = wl_shm_create_pool(shm, g_pool.fd, (int32_t)g_pool.size);
        struct wl_buffer *wb = wl_shm_pool_create_buffer(pool, 0,
            OUT_W, OUT_H, (int32_t)g_stride, g_fmt);
        wl_shm_pool_destroy(pool);
        zwlr_screencopy_frame_v1_copy(fr, wb);

        while (!g_done && !g_failed) {
            if (wl_display_dispatch(dpy) < 0) { fprintf(stderr, "dispatch 失败\n"); return 1; }
        }
        wl_buffer_destroy(wb);
        zwlr_screencopy_frame_v1_destroy(fr);

        if (g_failed) { usleep(50000); continue; }

        // 转 BGRX（XWD 布局）
        unsigned char *src = g_pool.data;
        size_t stride = g_stride;
        size_t rowbytes = (size_t)OUT_W * 4;
        int need_swap = (g_fmt == WL_SHM_FORMAT_XBGR8888 ||
                         g_fmt == WL_SHM_FORMAT_ABGR8888 ||
                         g_fmt == WL_SHM_FORMAT_RGBX8888 ||
                         g_fmt == WL_SHM_FORMAT_RGBA8888);

        if (!need_swap && stride == rowbytes) {
            // XRGB8888/ARGB8888 小端：内存本来就是 B,G,R,X —— 整块拷，最快
            memcpy(g_bgrx, src, rowbytes * OUT_H);
        } else {
            for (int y = 0; y < OUT_H; y++) {
                unsigned char *s = src + (size_t)y * stride;
                unsigned char *d = g_bgrx + (size_t)y * rowbytes;
                if (need_swap) {
                    for (int x = 0; x < OUT_W; x++) {
                        d[x*4+0] = s[x*4+2];   // B <- R
                        d[x*4+1] = s[x*4+1];   // G
                        d[x*4+2] = s[x*4+0];   // R <- B
                        d[x*4+3] = 0;
                    }
                } else {
                    memcpy(d, s, rowbytes);
                }
            }
        }

        // 写 XWD 像素区
        size_t want = NPIX * 4, done = 0;
        while (done < want) {
            ssize_t n = pwrite(g_buf_fd, g_bgrx + done, want - done,
                               PIX_OFF + (off_t)done);
            if (n <= 0) break;
            done += (size_t)n;
        }

        if (save_dbg && (g_frames % 50 == 0)) save_ppm("/tmp/dbg.ppm");

        g_frames++;
        clock_gettime(CLOCK_MONOTONIC, &t1);
        double el = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
        if (el - last_report >= 5.0) {
            printf("fps=%.1f  total=%ld\n", g_frames / el, g_frames);
            fflush(stdout);
            last_report = el;
        }
        if (secs > 0 && el >= secs) break;
    }
    printf("完成 %ld 帧 / %.1f 秒 = %.1f fps\n", g_frames, 
           (double)((t1.tv_sec-t0.tv_sec)+(t1.tv_nsec-t0.tv_nsec)/1e9),
           g_frames / ((t1.tv_sec-t0.tv_sec)+(t1.tv_nsec-t0.tv_nsec)/1e9));
    return 0;
}
