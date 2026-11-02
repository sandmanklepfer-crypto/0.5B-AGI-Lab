/* tliin.c —— TL 输入注入器（原生版，替换 fbi2）
 *
 * 改进点：
 *   1. 用 pread() 直接读文件（不用 mmap，绕过 MappedByteBuffer 未 force 的问题）
 *   2. DISPLAY 显式 :20（走抽象 socket）
 *   3. seq/keyseq 判重，单调递增
 *   4. 6ms 轮询
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

typedef struct _XDisplay Display;
typedef int Bool;
extern Display *XOpenDisplay(const char *);
extern int XFlush(Display *);
extern int XSync(Display *, int);
extern int XDisplayWidth(Display *, int);
extern int XDisplayHeight(Display *, int);
extern Bool XTestQueryExtension(Display*,int*,int*,int*,int*);
extern int XTestFakeMotionEvent(Display*,int,int,int,unsigned long);
extern int XTestFakeButtonEvent(Display*,unsigned int,Bool,unsigned long);
extern int XTestFakeKeyEvent(Display*,unsigned int,Bool,unsigned long);

struct _XPrivDisplay {
    void *ext_data; void *private1; int fd; int private2;
    int proto_major, proto_minor; int vendor;
    void *private3,*private4,*private5; int private6; void *private7;
    int byte_order, bitmap_unit, bitmap_pad, bitmap_bit_order;
    int nformats; void *pixmap_format;
    int private8, release; void *private9,*private10;
    int qlen, last_request_read; unsigned long request;
    void *private11,*private12,*private13,*private14;
    unsigned int max_request_size; void *db; void *private15;
    int display_name; int default_screen; int nscreens; void *screens;
};

#define TLI "/sdcard/.tli"

static uint32_t be32(const unsigned char *p){
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static uint64_t be64(const unsigned char *p){
    return ((uint64_t)be32(p)<<32)|be32(p+4);
}

int main(int argc, char **argv){
    const char *tli = (argc>1)? argv[1] : TLI;
    const char *dpy = getenv("DISPLAY");
    if (!dpy || !*dpy) dpy = ":20";

    Display *d = XOpenDisplay(dpy);
    if (!d) { fprintf(stderr,"tliin: 无法打开 %s\n", dpy); return 1; }
    int ev=0,er=0,mj=0,mn=0;
    if (!XTestQueryExtension(d,&ev,&er,&mj,&mn)) {
        fprintf(stderr,"tliin: 无 XTEST\n"); return 1;
    }
    int scr = ((struct _XPrivDisplay*)d)->default_screen;
    int W = XDisplayWidth(d, scr), H = XDisplayHeight(d, scr);
    fprintf(stderr,"tliin: %s  %dx%d  tli=%s  XTEST %d.%d\n", dpy, W, H, tli, mj, mn);

    int fd = open(tli, O_RDONLY);
    if (fd < 0) { fprintf(stderr,"tliin: open %s: %s\n", tli, strerror(errno)); return 1; }

    unsigned char b[64];
    uint64_t lastSeq = 0; int lastKey = 0, lastScroll = 0, btn = 0, first = 1;

    for(;;){
        ssize_t n = pread(fd, b, 64, 0);      /* ★ pread 直接读，绕过页缓存不一致 */
        if (n != 64) { usleep(50000); continue; }
        if (memcmp(b,"TLI2",4)!=0) { usleep(50000); continue; }

        uint64_t seq = be64(b+16);
        int32_t rx = (int32_t)be32(b+24), ry = (int32_t)be32(b+28);
        int32_t st = (int32_t)be32(b+32);
        int32_t key = (int32_t)be32(b+36);
        int32_t ksq = (int32_t)be32(b+40);
        int32_t scr2 = (int32_t)be32(b+44);

        if (first) {
            lastSeq=seq; lastKey=ksq; lastScroll=scr2; first=0;
            fprintf(stderr,"tliin: 基准 seq=%llu kseq=%d\n",(unsigned long long)seq,ksq);
            continue;
        }

        int did = 0;
        if (seq != lastSeq) {
            int px = (int)((int64_t)rx * W / 1000000);
            int py = (int)((int64_t)ry * H / 1000000);
            if(px<0)px=0; if(px>=W)px=W-1;
            if(py<0)py=0; if(py>=H)py=H-1;
            XTestFakeMotionEvent(d, scr, px, py, 0);
            if (st==1 && !btn) { XTestFakeButtonEvent(d,1,1,0); btn=1; }
            else if (st==0 && btn) { XTestFakeButtonEvent(d,1,0,0); btn=0; }
            lastSeq = seq; did = 1;
        }
        if (ksq != lastKey && key>0 && key<256) {
            XTestFakeKeyEvent(d,(unsigned)key,1,0);
            XTestFakeKeyEvent(d,(unsigned)key,0,0);
            lastKey = ksq; did = 1;
        }
        if (scr2 != lastScroll) {
            int bt = (scr2>lastScroll)?4:5;
            int c = scr2-lastScroll; if(c<0)c=-c; if(c>10)c=10;
            for(int i=0;i<c;i++){ XTestFakeButtonEvent(d,bt,1,0); XTestFakeButtonEvent(d,bt,0,0); }
            lastScroll = scr2; did = 1;
        }
        if (did) XFlush(d);
        usleep(6000);
    }
    return 0;
}
