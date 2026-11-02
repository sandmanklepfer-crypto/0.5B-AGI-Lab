/* ppm2xwd.c —— 把 grim 出来的 PPM(P6) 写进 Xvfb 的 XWD 文件像素区
 *
 * XWD 布局:
 *   0    .. 159   header (160 B)
 *   160  .. 3231  colormap (256 * 12 B)
 *   3232 ..       pixels: 1440*696*4, LSBFirst, 32bpp => 内存字节 B,G,R,0
 *
 * 原地 pwrite，不改文件大小（保护 TLHome 的 mmap 不被 SIGBUS）
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

#define PIX_OFF   3232
#define W         1440
#define H         696
#define NPIX      ((size_t)W * H)

static int read_ppm_header(FILE *f, int *w, int *h) {
    char magic[3] = {0};
    if (fscanf(f, "%2s", magic) != 1) return -1;
    if (strcmp(magic, "P6") != 0) return -1;

    int vals[3], got = 0;
    int c;
    while (got < 3) {
        c = fgetc(f);
        if (c == EOF) return -1;
        if (c == '#') { while (c != '\n' && c != EOF) c = fgetc(f); continue; }
        if (c == ' ' || c == '\n' || c == '\r' || c == '\t') continue;
        ungetc(c, f);
        if (fscanf(f, "%d", &vals[got]) != 1) return -1;
        got++;
    }
    /* 头后面正好一个空白 */
    c = fgetc(f);
    if (c != ' ' && c != '\n' && c != '\r' && c != '\t') ungetc(c, f);

    *w = vals[0]; *h = vals[1];
    return vals[2];
}

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "用法: %s <in.ppm> <Xvfb_screen0>\n", argv[0]); return 2; }

    FILE *f = fopen(argv[1], "rb");
    if (!f) { fprintf(stderr, "打不开 %s: %s\n", argv[1], strerror(errno)); return 1; }

    int w = 0, h = 0;
    int maxv = read_ppm_header(f, &w, &h);
    if (maxv != 255) { fprintf(stderr, "PPM 解析失败 maxv=%d\n", maxv); return 1; }
    if (w != W || h != H) { fprintf(stderr, "尺寸不符: %dx%d (要 %dx%d)\n", w, h, W, H); return 1; }

    size_t rgb_sz = (size_t)w * h * 3;
    unsigned char *rgb = malloc(rgb_sz);
    if (!rgb) return 1;
    if (fread(rgb, 1, rgb_sz, f) != rgb_sz) { fprintf(stderr, "PPM 数据不足\n"); return 1; }
    fclose(f);

    unsigned char *out = malloc(NPIX * 4);
    if (!out) return 1;
    for (size_t i = 0; i < NPIX; i++) {
        out[i*4 + 0] = rgb[i*3 + 2];   /* B */
        out[i*4 + 1] = rgb[i*3 + 1];   /* G */
        out[i*4 + 2] = rgb[i*3 + 0];   /* R */
        out[i*4 + 3] = 0;              /* X */
    }

    int fd = open(argv[2], O_WRONLY);
    if (fd < 0) { fprintf(stderr, "打不开 %s: %s\n", argv[2], strerror(errno)); return 1; }

    size_t want = NPIX * 4, done = 0;
    while (done < want) {
        ssize_t n = pwrite(fd, out + done, want - done, PIX_OFF + (off_t)done);
        if (n <= 0) { fprintf(stderr, "pwrite 失败: %s\n", strerror(errno)); close(fd); return 1; }
        done += (size_t)n;
    }
    close(fd);
    free(rgb); free(out);
    printf("OK 写入 %zu 字节 @offset %d\n", want, PIX_OFF);
    return 0;
}
