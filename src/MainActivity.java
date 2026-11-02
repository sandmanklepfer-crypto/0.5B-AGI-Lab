package com.zhz.tlhome;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Paint;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.PowerManager;
import android.util.Log;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.SurfaceHolder;
import android.view.SurfaceView;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.ServerSocket;
import java.net.Socket;

import java.io.File;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.MappedByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.IntBuffer;

/**
 * TL Home —— 把容器(Linux)的画面当桌面。
 * 零拷贝：直接 mmap /sdcard/.tlf，读环形缓冲最新帧，画到 SurfaceView。
 */
public class MainActivity extends Activity implements SurfaceHolder.Callback {
    private static final String TAG = "TLHome";
    private static final int HDR = 64;
    private static final int NBUF = 5;

    private static final int NSLOT = 256;
    private static final int ESZ = 16;

    private SurfaceView sv;
    private Renderer renderer;
    private PowerManager.WakeLock wl;

    // ===== 真 Chromium 层（WebView，GPU 合成）=====
    private FrameLayout root;
    private WebLayer web;
    private AudioPipe audio;
    private VaRelay vaRelay;
    private GLView glView;                  // 真 GPU 渲染层
    private volatile boolean glMode = false;
    private long glPushed = 0;
    private volatile boolean webMode = false;
    private static final int CTRL_PORT = 7810;

    // ===== 视图变换：双指缩放 + 双指平移 =====
    private volatile float zoom = 1.0f;      // 1.0 = 刚好适配
    private volatile float panX = 0f;        // 平移偏移（像素）
    private volatile float panY = 0f;
    private static final float ZOOM_MIN = 0.4f;   // 允许缩小，便于把屏幕外窗口拉回来
    private static final float ZOOM_MAX = 6.0f;

    // 双指手势临时状态
    private int touchMode = 0;               // 0=无 1=单指 2=双指
    private long lastGestureLog = 0;
    private float lastSpan = 0f, lastCx = 0f, lastCy = 0f;

    private RandomAccessFile inRaf;
    private MappedByteBuffer inMap;
    private long inSeq = 0;

    // ===== 竖屏提示遮罩（照搬《天泪纪元》rotateHint）=====
    private volatile boolean ovSkip = false;    // 「先这样玩」只跳本次
    private volatile boolean ovOn = false;
    private final Rect ovBtnA = new Rect();     // 主按钮命中区
    private final Rect ovBtnC = new Rect();     // 「先这样玩」命中区
    private volatile String ovTitle = "";
    private volatile String ovSub = "";
    private volatile String ovCmd = "";
    private volatile boolean ovCmdIsPort = false;

    /**
     * 让容器执行命令。
     * 【为什么不用 socket】TLHome 跑在 untrusted_app 域，
     * socket() 直接被 SELinux 拒（实测 EPERM）。
     * 改用 /sdcard/.tlcmd 文件：TLHome 写，容器侧 watcher 读并执行。
     *   off 0:  magic "TLCM"
     *   off 4:  seq (4)
     *   off 8:  len (4)
     *   off 12: cmd (UTF-8, 最多 500 字节)
     */
    private void sendCmd(final String cmd) {
        try {
            File f = new File("/sdcard/.tlcmd");
            java.io.RandomAccessFile raf = new java.io.RandomAccessFile(f, "rw");
            if (raf.length() < 512) raf.setLength(512);
            byte[] cb = cmd.getBytes("UTF-8");
            if (cb.length > 500) cb = java.util.Arrays.copyOf(cb, 500);
            raf.seek(0);
            raf.write("TLCM".getBytes("US-ASCII"));
            cmdSeq++;
            raf.write((cmdSeq >> 24) & 0xFF);
            raf.write((cmdSeq >> 16) & 0xFF);
            raf.write((cmdSeq >> 8) & 0xFF);
            raf.write(cmdSeq & 0xFF);
            raf.write((cb.length >> 24) & 0xFF);
            raf.write((cb.length >> 16) & 0xFF);
            raf.write((cb.length >> 8) & 0xFF);
            raf.write(cb.length & 0xFF);
            raf.write(cb);
            raf.getFD().sync();
            raf.close();
            Log.i(TAG, "sendCmd(file) seq=" + cmdSeq + " : " + cmd);
        } catch (Throwable t) {
            Log.e(TAG, "sendCmd(file) fail: " + cmd, t);
        }
    }

    private int cmdSeq = 0;

    /** 目标分辨率：长边固定 1600，短边按画面比例算 */
    private int[] targetSize() {
        int pw = Math.max(1, sv.getWidth());
        int ph = Math.max(1, sv.getHeight());
        final int LONG = 1600;
        int tw, th;
        if (pw > ph) { tw = LONG; th = (int) ((long) LONG * ph / pw); }
        else         { th = LONG; tw = (int) ((long) LONG * pw / ph); }
        tw &= ~1; th &= ~1;
        if (tw < 320) tw = 320;
        if (th < 320) th = 320;
        return new int[]{tw, th};
    }

    /**
     * App 已锁定横屏，正常情况下和 Linux 横屏一致 → 不显示任何遮罩。
     * 只有首次启动 / 分辨率不符时才切一次，切完就安静。
     */
    private volatile boolean alignedOnce = false;
    private volatile String switchNote = "";

    private void updateOverlayState() {
        int rw = renderW(), rh = renderH();
        if (rw <= 0 || rh <= 0) { ovOn = false; return; }

        boolean linuxLand = rw > rh;
        // App 锁横屏，所以期望 Linux 也是横屏
        if (linuxLand) {
            ovOn = false;
            alignedOnce = true;
            return;
        }
        // Linux 是竖屏 → 切一次横屏，之后不再打扰
        if (!alignedOnce) {
            int[] t = targetSize();
            alignedOnce = true;
            switchNote = "正在切换到横屏布局";
            Log.i(TAG, "align once -> bash /root/deskup.sh " + t[0] + "x" + t[1]);
            sendCmd("bash /root/deskup.sh " + t[0] + "x" + t[1]);
            ovOn = true;
            ovTitle = switchNote;
            ovSub = "Linux " + rw + "×" + rh + "   画面 " + sv.getWidth() + "×" + sv.getHeight();
            return;
        }
        ovOn = false;
    }

    /** 画切换提示：顶部半透明条，不遮挡画面 */
    private void drawOverlay(Canvas c) {
        int w = c.getWidth(), h = c.getHeight();
        if (w <= 0 || h <= 0) return;

        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        float u = Math.min(w, h) / 720f;

        // 顶部半透明条
        float barH = 132 * u;
        p.setShader(new LinearGradient(0, 0, 0, barH, 0xF0100A24, 0x00100A24, Shader.TileMode.CLAMP));
        c.drawRect(0, 0, w, barH, p);
        p.setShader(null);

        // 转圈指示：用进度点表示
        long t = System.currentTimeMillis();
        int dots = (int) ((t / 300) % 4);
        StringBuilder sb = new StringBuilder(ovTitle);
        for (int i = 0; i < dots; i++) sb.append('.');

        p.setTextAlign(Paint.Align.CENTER);
        p.setColor(0xFFE8E8F0);
        p.setFakeBoldText(true);
        p.setTextSize(26 * u);
        c.drawText(sb.toString(), w / 2f, 46 * u, p);

        p.setFakeBoldText(false);
        p.setColor(0xFF9FB4C8);
        p.setTextSize(18 * u);
        c.drawText(ovSub, w / 2f, 84 * u, p);

        // 右下角「先这样玩」小按钮
        float bw = 200 * u, bh = 62 * u;
        float bx = w - bw - 30 * u, by = h - bh - 30 * u;
        ovBtnC.set((int) bx, (int) by, (int) (bx + bw), (int) (by + bh));
        Paint bp = new Paint(Paint.ANTI_ALIAS_FLAG);
        bp.setColor(0xCC1A2433);
        c.drawRoundRect(new RectF(ovBtnC), 18 * u, 18 * u, bp);
        p.setColor(0xFFB8C8D8);
        p.setTextSize(19 * u);
        c.drawText("先这样玩", bx + bw / 2f, by + bh / 2f + 7 * u, p);

        // 主按钮不画了（自动切换），但保留命中区给「立即切换」
        ovBtnA.set(0, 0, 0, 0);
    }

    private void openInput() {
        if (inMap != null) return;
        try {
            File f = new File("/sdcard/.tli");
            if (!f.exists()) { Log.w(TAG, "no .tli yet"); return; }
            inRaf = new RandomAccessFile(f, "rw");
            inMap = inRaf.getChannel().map(FileChannel.MapMode.READ_WRITE, 0, 64);
            inMap.order(ByteOrder.BIG_ENDIAN);
            byte[] mg = new byte[4];
            inMap.position(0); inMap.get(mg);
            Log.i(TAG, "input magic=" + new String(mg, "US-ASCII"));
        } catch (Throwable t) {
            Log.e(TAG, "openInput fail", t);
            inMap = null;
        }
    }

    // ============ 键盘：把 Android keycode 写进 .tli，由 fbi2 XTest 注入 X ============
    private int keySeq = 0;
    private final java.util.HashMap<Integer,Integer> keyMap = new java.util.HashMap<Integer,Integer>();

    /** Android KeyEvent.keyCode -> X11 keycode */
    private void initKeyMap() {
        if (keyMap.size() > 0) return;
        keyMap.put(KeyEvent.KEYCODE_ENTER, 36);
        keyMap.put(KeyEvent.KEYCODE_NUMPAD_ENTER, 104);
        keyMap.put(KeyEvent.KEYCODE_DEL, 22);          // 退格 -> BackSpace
        keyMap.put(KeyEvent.KEYCODE_FORWARD_DEL, 119);
        keyMap.put(KeyEvent.KEYCODE_TAB, 23);
        keyMap.put(KeyEvent.KEYCODE_ESCAPE, 9);
        keyMap.put(KeyEvent.KEYCODE_SPACE, 65);
        keyMap.put(KeyEvent.KEYCODE_DPAD_LEFT, 113);
        keyMap.put(KeyEvent.KEYCODE_DPAD_UP, 111);
        keyMap.put(KeyEvent.KEYCODE_DPAD_RIGHT, 114);
        keyMap.put(KeyEvent.KEYCODE_DPAD_DOWN, 116);
        keyMap.put(KeyEvent.KEYCODE_MOVE_HOME, 110);
        keyMap.put(KeyEvent.KEYCODE_MOVE_END, 115);
        keyMap.put(KeyEvent.KEYCODE_PAGE_UP, 112);
        keyMap.put(KeyEvent.KEYCODE_PAGE_DOWN, 117);
        keyMap.put(KeyEvent.KEYCODE_MINUS, 20);
        keyMap.put(KeyEvent.KEYCODE_EQUALS, 21);
        keyMap.put(KeyEvent.KEYCODE_LEFT_BRACKET, 34);
        keyMap.put(KeyEvent.KEYCODE_RIGHT_BRACKET, 35);
        keyMap.put(KeyEvent.KEYCODE_SEMICOLON, 47);
        keyMap.put(KeyEvent.KEYCODE_APOSTROPHE, 48);
        keyMap.put(KeyEvent.KEYCODE_GRAVE, 49);
        keyMap.put(KeyEvent.KEYCODE_BACKSLASH, 51);
        keyMap.put(KeyEvent.KEYCODE_COMMA, 59);
        keyMap.put(KeyEvent.KEYCODE_PERIOD, 60);
        keyMap.put(KeyEvent.KEYCODE_SLASH, 61);
        keyMap.put(KeyEvent.KEYCODE_CTRL_LEFT, 37);
        keyMap.put(KeyEvent.KEYCODE_SHIFT_LEFT, 50);
        keyMap.put(KeyEvent.KEYCODE_SHIFT_RIGHT, 62);
        keyMap.put(KeyEvent.KEYCODE_ALT_LEFT, 64);
        keyMap.put(KeyEvent.KEYCODE_META_LEFT, 133);
        keyMap.put(KeyEvent.KEYCODE_F1, 67);
        keyMap.put(KeyEvent.KEYCODE_F5, 71);
        keyMap.put(KeyEvent.KEYCODE_F11, 95);
        keyMap.put(KeyEvent.KEYCODE_F12, 96);
        // 数字 0-9
        int[] numKeys = {KeyEvent.KEYCODE_0, KeyEvent.KEYCODE_1, KeyEvent.KEYCODE_2,
                KeyEvent.KEYCODE_3, KeyEvent.KEYCODE_4, KeyEvent.KEYCODE_5,
                KeyEvent.KEYCODE_6, KeyEvent.KEYCODE_7, KeyEvent.KEYCODE_8, KeyEvent.KEYCODE_9};
        for (int i = 0; i < 10; i++) keyMap.put(numKeys[i], 19 + i);
    }

    /** 送一个键到 .tli（off36=key, off40=keyseq++） */
    private boolean sendKeyRaw(int x11code) {
        if (inMap == null) { openInput(); if (inMap == null) return false; }
        try {
            inMap.putInt(36, x11code);
            keySeq++;
            inMap.putInt(40, keySeq);
            return true;
        } catch (Throwable t) { return false; }
    }

    /** 把 Android 按键翻成 X11 keycode，按住 Shift 时自动大写/符号 */
    private boolean sendKeyEvent(KeyEvent e) {
        initKeyMap();
        int c = e.getKeyCode();
        if (c == KeyEvent.KEYCODE_VOLUME_DOWN || c == KeyEvent.KEYCODE_VOLUME_UP
                || c == KeyEvent.KEYCODE_BACK || c == KeyEvent.KEYCODE_HOME
                || c == KeyEvent.KEYCODE_POWER || c == KeyEvent.KEYCODE_MENU) return false;

        boolean shift = e.isShiftPressed();

        // 字母 A-Z -> X11 38..63
        if (c >= KeyEvent.KEYCODE_A && c <= KeyEvent.KEYCODE_Z) {
            int x = 38 + (c - KeyEvent.KEYCODE_A);
            if (shift) sendKeyRaw(50);          // Shift_L 按下
            boolean ok = sendKeyRaw(x);
            if (shift) sendKeyRaw(50);          // 抬起（同一个 code，fbi2 只发 press+release）
            return ok;
        }
        // 数字行 Shift 后的符号
        if (shift && c >= KeyEvent.KEYCODE_0 && c <= KeyEvent.KEYCODE_9) {
            int[] sym = {41, 10, 11, 12, 13, 14, 15, 16, 17, 18};  // ) ! @ # $ % ^ & * (
            sendKeyRaw(50);
            boolean ok = sendKeyRaw(sym[c - KeyEvent.KEYCODE_0]);
            sendKeyRaw(50);
            return ok;
        }
        Integer x = keyMap.get(c);
        if (x == null) return false;
        return sendKeyRaw(x);
    }

    /** 单个字符 -> X11 keycode（ASCII 范围，含 Shift 处理） */
    private void sendChar(char ch) {
        if (ch == '\n' || ch == '\r') { sendKeyRaw(36); return; }
        if (ch == '\t') { sendKeyRaw(23); return; }
        if (ch == 8 || ch == 127) { sendKeyRaw(22); return; }
        if (ch >= 'a' && ch <= 'z') { sendKeyRaw(38 + (ch - 'a')); return; }
        if (ch >= 'A' && ch <= 'Z') { sendKeyRaw(50); sendKeyRaw(38 + (ch - 'A')); sendKeyRaw(50); return; }
        if (ch >= '0' && ch <= '9') { sendKeyRaw(19 + (ch - '0')); return; }
        // 符号表：字符 -> {是否需要 shift, X11 keycode}
        String plain = " -=[]\\;'`,./";
        String shifted = " _+{}|:\"~<>?";
        int pi = plain.indexOf(ch);
        if (pi >= 0 && pi < 13) {
            int[] codes = {65, 20, 21, 34, 35, 51, 47, 48, 49, 59, 60, 61};
            int idx = pi - 1;
            if (idx >= 0 && idx < codes.length) { sendKeyRaw(codes[idx]); return; }
        }
        int si = shifted.indexOf(ch);
        if (si >= 0 && si < 12) {
            int[] scodes = {65, 20, 21, 34, 35, 51, 47, 48, 49, 59, 60, 61};
            if (si < scodes.length) { sendKeyRaw(50); sendKeyRaw(scodes[si]); sendKeyRaw(50); return; }
        }
        // 数字行 Shift 符号
        String numPlain  = "0123456789";
        String numShift  = ")!@#$%^&*(";
        int np = numPlain.indexOf(ch);
        if (np >= 0) { sendKeyRaw(19 + np); return; }
        int ns = numShift.indexOf(ch);
        if (ns >= 0) { sendKeyRaw(50); sendKeyRaw(19 + ns); sendKeyRaw(50); return; }
        // 中文等非 ASCII：写到 /sdcard/.tkb.in，由设备侧 kbpaste 用 xdotool type 注入
        flushUtf8(String.valueOf(ch));
    }

    /** 非 ASCII 文本走文件通道（XTest 只能发 keycode，发不了 Unicode） */
    private java.io.FileOutputStream kbOut;
    private int kbSeq = 0;

    private void flushUtf8(String s) {
        try {
            if (kbOut == null) {
                kbOut = new java.io.FileOutputStream("/sdcard/.tkb.in", true);
            }
            kbSeq++;
            String line = kbSeq + "\t" + s.replace("\n", " ") + "\n";
            kbOut.write(line.getBytes("UTF-8"));
            kbOut.flush();
            Log.i(TAG, "utf8 out: " + s);
        } catch (Throwable t) {
            Log.e(TAG, "flushUtf8 fail", t);
            kbOut = null;
        }
    }

    /** 混排文本：ASCII 走 XTest，非 ASCII 走文件 */
    private void sendText(String txt) {
        StringBuilder buf = new StringBuilder();
        for (int i = 0; i < txt.length(); i++) {
            char ch = txt.charAt(i);
            if (ch < 128) {
                if (buf.length() > 0) { flushUtf8(buf.toString()); buf.setLength(0); }
                sendChar(ch);
            } else {
                buf.append(ch);
            }
        }
        if (buf.length() > 0) flushUtf8(buf.toString());
    }

    /** 状态槽模式：直接覆盖 x/y/state，seq+1。不排队，永远是最新位置 */
    private void sendState(int state, int x, int y) {
        if (inMap == null) { openInput(); if (inMap == null) return; }
        try {
            inMap.putInt(24, x);
            inMap.putInt(28, y);
            inMap.putInt(32, state);
            inSeq++;
            inMap.putLong(16, inSeq);
        } catch (Throwable t) {
            Log.e(TAG, "sendState fail", t);
        }
    }

    /**
     * 关键修正：把触摸点映射到 framebuffer 坐标。
     * 画面是按 fit() 等比缩放 + 居中显示的，必须扣掉黑边再除缩放比。
     */
    private int mapX(float px, int surfW, int surfHt) {
        Rect d = computeFit(surfW, surfHt);
        if (d.width() <= 0) return 0;
        float r = (float) d.width() / renderW();
        float rel = (px - d.left) / r;
        int v = (int) (rel * 1000000 / renderW());
        return Math.max(0, Math.min(1000000, v));
    }

    private int mapY(float py, int surfW, int surfHt) {
        Rect d = computeFit(surfW, surfHt);
        if (d.height() <= 0) return 0;
        float r = (float) d.height() / renderH();
        float rel = (py - d.top) / r;
        int v = (int) (rel * 1000000 / renderH());
        return Math.max(0, Math.min(1000000, v));
    }

    /** 统一计算绘制矩形：屏幕尺寸 + zoom + pan */
    private Rect computeFit(int sw, int sh) {
        int fw = renderW(), fh = renderH();
        if (sw <= 0 || sh <= 0 || fw <= 0 || fh <= 0) return new Rect(0, 0, sw, sh);
        float r = Math.min((float) sw / fw, (float) sh / fh) * zoom;
        int w = (int) (fw * r), h = (int) (fh * r);
        int l = (sw - w) / 2 + (int) panX;
        int t = (sh - h) / 2 + (int) panY;
        return new Rect(l, t, l + w, t + h);
    }

    /** 限制 zoom/pan 范围，别让画面跑没 */
    private void clampView(int sw, int sh) {
        if (zoom < ZOOM_MIN) zoom = ZOOM_MIN;
        if (zoom > ZOOM_MAX) zoom = ZOOM_MAX;
        int fw = renderW(), fh = renderH();
        if (fw <= 0 || fh <= 0) return;
        float r = Math.min((float) sw / fw, (float) sh / fh) * zoom;
        int w = (int) (fw * r), h = (int) (fh * r);
        // zoom < 1 时画面比屏幕小，不需要平移
        float mx = Math.max(0, (w - sw) / 2f);
        float my = Math.max(0, (h - sh) / 2f);
        if (panX > mx) panX = mx;
        if (panX < -mx) panX = -mx;
        if (panY > my) panY = my;
        if (panY < -my) panY = -my;
    }

    /** 复位视图 */
    private void resetView() {
        zoom = 1.0f; panX = 0f; panY = 0f;
        Log.i(TAG, "view reset");
    }

    private int renderW() { return (renderer != null && renderer.fw > 0) ? renderer.fw : 720; }
    private int renderH() { return (renderer != null && renderer.fh > 0) ? renderer.fh : 1560; }
    private int surfH() { return sv.getHeight() > 0 ? sv.getHeight() : 2772; }


    // 触摸限流：MOVE 最多每 6ms 发一次
    private long lastMoveAt = 0;

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        // 只有「先这样玩」小按钮吃事件，其余触摸全部透传给 Linux
        if (ovOn && e.getActionMasked() == MotionEvent.ACTION_UP) {
            int ax = (int) e.getX(), ay = (int) e.getY();
            if (ovBtnC.contains(ax, ay)) {
                Log.i(TAG, "overlay: skip");
                ovSkip = true;
                ovOn = false;
                return true;
            }
        }
        int sw = sv.getWidth() > 0 ? sv.getWidth() : 1280;
        int sh = sv.getHeight() > 0 ? sv.getHeight() : 2772;
        int action = e.getActionMasked();
        int pointers = e.getPointerCount();

        // ========== 双指：缩放 + 平移（纯本地变换，不发给 Linux）==========
        if (pointers >= 2) {
            float x0 = e.getX(0), y0 = e.getY(0);
            float x1 = e.getX(1), y1 = e.getY(1);
            float cx = (x0 + x1) * 0.5f;
            float cy = (y0 + y1) * 0.5f;
            float span = (float) Math.hypot(x1 - x0, y1 - y0);

            if (touchMode != 2) {
                touchMode = 2;
                lastSpan = span;
                lastCx = cx;
                lastCy = cy;
                // 双指开始时，先告诉 Linux 抬起（避免单指的按下状态卡住）
                sendState(0, mapX(cx, sw, sh), mapY(cy, sw, sh));
            } else {
                if (lastSpan > 8f && span > 8f) {
                    float k = span / lastSpan;
                    float nz = zoom * k;
                    if (nz < ZOOM_MIN) nz = ZOOM_MIN;
                    if (nz > ZOOM_MAX) nz = ZOOM_MAX;
                    zoom = nz;
                }
                panX += cx - lastCx;
                panY += cy - lastCy;
                clampView(sw, sh);
                lastSpan = span;
                lastCx = cx;
                lastCy = cy;
                long tn = System.currentTimeMillis();
                if (tn - lastGestureLog > 150) {
                    lastGestureLog = tn;
                    Log.i(TAG, String.format("gesture: zoom=%.2f pan=(%.0f,%.0f)", zoom, panX, panY));
                }
            }
            return true;
        }

        // 双指抬起后残留的最后一根手指：忽略，直到全部离开
        if (touchMode == 2) {
            if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                touchMode = 0;
                Log.i(TAG, String.format("gesture end: zoom=%.2f pan=(%.0f,%.0f) "
                        + "dst=%s", zoom, panX, panY, computeFit(sw, sh).toShortString()));
            }
            return true;
        }

        // ========== 单指：点击 / 拖拽 → 发给 Linux ==========
        int X = mapX(e.getX(), sw, sh), Y = mapY(e.getY(), sw, sh);
        switch (action) {
            case MotionEvent.ACTION_DOWN:
                touchMode = 1;
                sendState(1, X, Y);
                lastMoveAt = System.currentTimeMillis();
                break;
            case MotionEvent.ACTION_MOVE:
                long nowm = System.currentTimeMillis();
                if (nowm - lastMoveAt >= 6) {
                    sendState(2, X, Y);
                    lastMoveAt = nowm;
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_CANCEL:
                sendState(0, X, Y);
                touchMode = 0;
                break;
        }
        return true;
    }

    /** 唤起输入法：焦点需要一个可输入的 View，这里借一个不可见的 EditText */
    private android.widget.EditText imeProxy;
    private android.view.inputmethod.InputMethodManager imm;

    private void showIme() {
        try {
            if (imeProxy == null) {
                imeProxy = new android.widget.EditText(this);
                imeProxy.setAlpha(0f);
                imeProxy.setFocusable(true);
                imeProxy.setFocusableInTouchMode(true);
                root.addView(imeProxy, new FrameLayout.LayoutParams(1, 1));
                imm = (android.view.inputmethod.InputMethodManager)
                        getSystemService(INPUT_METHOD_SERVICE);
                // IME 提交的是文字，不是按键 → 用 TextWatcher 逐字符转换
                imeProxy.addTextChangedListener(new android.text.TextWatcher() {
                    public void beforeTextChanged(CharSequence s2, int a, int b, int c) {}
                    public void onTextChanged(CharSequence s2, int a, int b, int c) {}
                    public void afterTextChanged(android.text.Editable ed) {
                        String txt = ed.toString();
                        if (txt.length() > 0) {
                            sendText(txt);
                            ed.clear();
                        }
                    }
                });
                imeProxy.setOnKeyListener(new View.OnKeyListener() {
                    public boolean onKey(View v, int c, KeyEvent ev) {
                        if (ev.getAction() == KeyEvent.ACTION_DOWN) {
                            KeyEvent e2 = ev;
                            return sendKeyEvent(e2);
                        }
                        return false;
                    }
                });
            }
            imeProxy.requestFocus();
            imm.showSoftInput(imeProxy, android.view.inputmethod.InputMethodManager.SHOW_FORCED);
            Log.i(TAG, "IME shown");
        } catch (Throwable t) { Log.e(TAG, "showIme fail", t); }
    }

    private void hideIme() {
        try {
            if (imm != null && imeProxy != null) {
                imm.hideSoftInputFromWindow(imeProxy.getWindowToken(), 0);
            }
        } catch (Throwable ignored) {}
    }

    @Override
    public boolean onGenericMotionEvent(MotionEvent e) {
        if (e.getActionMasked() == MotionEvent.ACTION_SCROLL) {
            float v = e.getAxisValue(MotionEvent.AXIS_VSCROLL);
            if (inMap != null) {
                try { inMap.putInt(44, v > 0 ? 1 : -1); } catch (Throwable ignored) {}
            }
            return true;
        }
        return super.onGenericMotionEvent(e);
    }

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        // 【关键】键盘弹出时不重排布局，画面尺寸保持不变，键盘浮在下方
        getWindow().setSoftInputMode(
                WindowManager.LayoutParams.SOFT_INPUT_ADJUST_NOTHING);
        // 【关键】把自己锁成横屏：Surface 永远是 2640x1280 左右，
        // 和 Linux 的 1600x776（同比例）完全吻合，不再有来回切换/黑边
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE);
        hideSystemUi();

        if (Build.VERSION.SDK_INT >= 23) {
            if (checkSelfPermission(android.Manifest.permission.READ_EXTERNAL_STORAGE)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{
                        android.Manifest.permission.READ_EXTERNAL_STORAGE,
                        android.Manifest.permission.WRITE_EXTERNAL_STORAGE}, 1);
            }
        }

        sv = new SurfaceView(this);
        sv.getHolder().addCallback(this);
        sv.setFocusableInTouchMode(true);
        sv.requestFocus();

        // SurfaceView 在下，WebView 层在上（按需显示）
        root = new FrameLayout(this);
        root.addView(sv, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        glView = new GLView(this);
        glView.setVisibility(View.GONE);
        root.addView(glView, new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT));
        setContentView(root);

        // Linux 音频输出：ALSA file 插件 -> /data/local/tmp/tlaudio.raw -> AudioTrack
        audio = new AudioPipe(this);
        audio.start();
        // 启动 3 秒后播一次自检音，验证 AudioTrack 通路
        root.postDelayed(new Runnable() {
            public void run() { if (audio != null) audio.selfTest(); }
        }, 3000);

        web = new WebLayer(this, root);
        web.setHook(new WebLayer.Hook() {
            public void setWebMode(boolean on) { webMode = on; }
        });
        startControl();

        // VPU 硬解：在本 App（untrusted_app 域）里起 termux-va daemon + TCP 中继
        try {
            vaRelay = new VaRelay(this);
            vaRelay.start();
        } catch (Throwable t) {
            android.util.Log.e("TLVa", "VaRelay 启动异常: " + t);
        }

        openInput();
        addKbdButton();

        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        wl = pm.newWakeLock(PowerManager.SCREEN_DIM_WAKE_LOCK, "TLHome");
    }

    /** 悬浮键盘按钮：点一下唤起 Android 输入法，再点一下收起；可拖动 */
    private android.widget.TextView kbdBtn;
    private boolean imeOn = false;

    private void addKbdButton() {
        try {
            final float dp = getResources().getDisplayMetrics().density;
            kbdBtn = new android.widget.TextView(this);
            kbdBtn.setText("\u2328");
            kbdBtn.setTextSize(22);
            kbdBtn.setTextColor(0xFFFFFFFF);
            kbdBtn.setGravity(android.view.Gravity.CENTER);
            android.graphics.drawable.GradientDrawable bg =
                    new android.graphics.drawable.GradientDrawable();
            bg.setColor(0x99000000);
            bg.setCornerRadius(14 * dp);
            bg.setStroke((int) (1 * dp), 0x66FFFFFF);
            kbdBtn.setBackground(bg);
            int S = (int) (48 * dp);
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(S, S);
            lp.gravity = android.view.Gravity.BOTTOM | android.view.Gravity.END;
            lp.rightMargin = (int) (10 * dp);
            lp.bottomMargin = (int) (10 * dp);
            kbdBtn.setLayoutParams(lp);
            kbdBtn.setAlpha(0.75f);

            kbdBtn.setOnTouchListener(new View.OnTouchListener() {
                float downRawY;
                int downLpBottom;
                long downAt;
                boolean moved;
                public boolean onTouch(View v, MotionEvent ev) {
                    FrameLayout.LayoutParams p = (FrameLayout.LayoutParams) v.getLayoutParams();
                    switch (ev.getActionMasked()) {
                        case MotionEvent.ACTION_DOWN:
                            downRawY = ev.getRawY();
                            downLpBottom = p.bottomMargin;
                            downAt = System.currentTimeMillis();
                            moved = false;
                            return true;
                        case MotionEvent.ACTION_MOVE: {
                            float dy = ev.getRawY() - downRawY;
                            if (Math.abs(dy) > 8 * dp) moved = true;
                            if (moved) {
                                p.bottomMargin = (int) (downLpBottom - dy);
                                int maxB = root.getHeight() - v.getHeight();
                                if (p.bottomMargin < 0) p.bottomMargin = 0;
                                if (maxB > 0 && p.bottomMargin > maxB) p.bottomMargin = maxB;
                                v.setLayoutParams(p);
                            }
                            return true;
                        }
                        case MotionEvent.ACTION_UP:
                        case MotionEvent.ACTION_CANCEL:
                            if (!moved && System.currentTimeMillis() - downAt < 400) {
                                toggleIme();
                            }
                            return true;
                    }
                    return false;
                }
            });
            root.addView(kbdBtn);
            Log.i(TAG, "kbd button added");
        } catch (Throwable t) { Log.e(TAG, "addKbdButton fail", t); }
    }

    private void toggleIme() {
        if (imeOn) { hideIme(); imeOn = false; }
        else { showIme(); imeOn = true; }
        if (kbdBtn != null) kbdBtn.setAlpha(imeOn ? 1.0f : 0.75f);
        Log.i(TAG, "toggleIme -> " + imeOn);
    }

    /** 容器 -> App 的控制口（TCP 127.0.0.1:7810，不用 /sdcard 轮询） */
    private void startControl() {
        Thread t = new Thread(new Runnable() {
            public void run() {
                ServerSocket ss = null;
                try {
                    ss = new ServerSocket(CTRL_PORT, 8,
                            java.net.InetAddress.getByName("127.0.0.1"));
                    Log.i(TAG, "control listening 127.0.0.1:" + CTRL_PORT);
                } catch (Exception e) {
                    Log.e(TAG, "control bind fail: " + e);
                    return;
                }
                while (true) {
                    try {
                        Socket c = ss.accept();
                        BufferedReader r = new BufferedReader(
                                new InputStreamReader(c.getInputStream(), "UTF-8"));
                        String line;
                        while ((line = r.readLine()) != null) {
                            final String cmd = line.trim();
                            if (cmd.length() == 0) continue;
                            Log.i(TAG, "CTRL " + cmd);
                            runOnUiThread(new Runnable() {
                                public void run() { handleCtrl(cmd); }
                            });
                        }
                        c.close();
                    } catch (Exception e) {
                        Log.e(TAG, "control loop: " + e);
                    }
                }
            }
        }, "TLControl");
        t.setDaemon(true);
        t.start();
    }

    private void handleCtrl(String cmd) {
        if (cmd.startsWith("web:")) {
            web.show(cmd.substring(4).trim());
        } else if (cmd.equals("term")) {
            web.show("http://127.0.0.1:7801/");
        } else if (cmd.startsWith("url:")) {
            web.show(cmd.substring(4).trim());
        } else if (cmd.equals("gl")) {
            glMode = true; glView.setVisibility(View.VISIBLE);
            Log.i(TAG, "GL mode ON");
        } else if (cmd.equals("gloff")) {
            glMode = false; glView.setVisibility(View.GONE);
            Log.i(TAG, "GL mode OFF");
        } else if (cmd.startsWith("sharp:")) {
            try { glView.sharpen = Float.parseFloat(cmd.substring(6)); } catch (Throwable t) {}
        } else if (cmd.startsWith("bright:")) {
            try { glView.brightness = Float.parseFloat(cmd.substring(7)); } catch (Throwable t) {}
        } else if (cmd.startsWith("gamma:")) {
            try { glView.gamma = Float.parseFloat(cmd.substring(6)); } catch (Throwable t) {}
        } else if (cmd.equals("audiotest")) {
            audio.selfTest();
        } else if (cmd.equals("audio") || cmd.equals("snd")) {
            audio.start();
        } else if (cmd.equals("audiooff") || cmd.equals("sndoff")) {
            audio.stop();
        } else if (cmd.equals("kbd") || cmd.equals("ime")) {
            showIme();
        } else if (cmd.equals("kbdhide") || cmd.equals("imehide")) {
            hideIme();
        } else if (cmd.equals("off") || cmd.equals("close")) {
            web.hide();
        } else if (cmd.equals("back")) {
            if (!web.goBack()) web.hide();
        }
    }

    @Override
    protected void onDestroy() {
        if (audio != null) audio.stop();
        if (web != null) web.destroy();
        super.onDestroy();
    }

    private void hideSystemUi() {
        View d = getWindow().getDecorView();
        d.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }

    @Override
    protected void onResume() {
        super.onResume();
        hideSystemUi();
        try { if (wl != null) wl.acquire(); } catch (Throwable ignored) {}
    }

    @Override
    protected void onPause() {
        super.onPause();
        try { if (wl != null && wl.isHeld()) wl.release(); } catch (Throwable ignored) {}
    }

    @Override
    public void onBackPressed() {
        // 网页模式下：返回键 = 网页后退 / 关闭网页
        if (webMode && web != null) {
            if (!web.goBack()) web.hide();
            return;
        }
        // 桌面不响应返回键
    }

    // ============ 逃生机制 1：音量下键长按 3 秒 → 回小米桌面 ============
    private long volDownAt = 0;

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_VOLUME_DOWN) {
            if (volDownAt == 0) volDownAt = System.currentTimeMillis();
            if (System.currentTimeMillis() - volDownAt > 3000) {
                Log.w(TAG, "ESCAPE: volume-down long press");
                escapeToMiui();
                return true;
            }
        }
        // 音量上键长按也做逃生（双保险）
        if (code == KeyEvent.KEYCODE_VOLUME_UP) {
            if (volUpAt == 0) volUpAt = System.currentTimeMillis();
            if (System.currentTimeMillis() - volUpAt > 3000) {
                Log.w(TAG, "ESCAPE: volume-up long press");
                escapeToMiui();
                return true;
            }
        }
        // 其余按键 -> 写进 .tli，让 Linux 里的 X 收到
        if (sendKeyEvent(e)) {
            Log.i(TAG, "KEY -> x11 code sent, keySeq=" + keySeq);
            return true;
        }
        return super.onKeyDown(code, e);
    }

    private long volUpAt = 0;

    @Override
    public boolean onKeyUp(int code, KeyEvent e) {
        if (code == KeyEvent.KEYCODE_VOLUME_DOWN) volDownAt = 0;
        if (code == KeyEvent.KEYCODE_VOLUME_UP) volUpAt = 0;
        return super.onKeyUp(code, e);
    }

    private void escapeToMiui() {
        try {
            Intent i = new Intent();
            i.setComponent(new android.content.ComponentName(
                    "com.miui.home", "com.miui.home.launcher.Launcher"));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(i);
            Log.w(TAG, "escape: launched miui home");
        } catch (Throwable t) {
            Log.e(TAG, "escape failed", t);
            try {
                Intent h = new Intent(Intent.ACTION_MAIN);
                h.addCategory(Intent.CATEGORY_HOME);
                h.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                startActivity(h);
            } catch (Throwable ignored) {}
        }
    }

    @Override
    public void surfaceCreated(SurfaceHolder h) {
        renderer = new Renderer(h);
        renderer.start();
    }

    @Override
    public void surfaceChanged(SurfaceHolder h, int f, int w, int hh) {}

    @Override
    public void surfaceDestroyed(SurfaceHolder h) {
        if (renderer != null) { renderer.stop = true; renderer = null; }
    }

    // ---------------- 渲染线程 ----------------
    private static java.lang.reflect.Method M_LOCK_HW = null;
    private static boolean mHwTried = false;

    /** 反射拿 lockHardwareCanvas（API 26+，但编译 jar 是 23） */
    private static Canvas lockBest(SurfaceHolder holder) {
        if (!mHwTried) {
            mHwTried = true;
            try {
                M_LOCK_HW = SurfaceHolder.class.getMethod("lockHardwareCanvas");
                Log.i(TAG, "lockHardwareCanvas available");
            } catch (Throwable t) {
                Log.i(TAG, "lockHardwareCanvas NOT available: " + t);
                M_LOCK_HW = null;
            }
        }
        if (M_LOCK_HW != null) {
            try {
                Object o = M_LOCK_HW.invoke(holder);
                if (o instanceof Canvas) return (Canvas) o;
            } catch (Throwable ignored) {}
        }
        try {
            return holder.lockCanvas();
        } catch (Throwable t) {
            return null;
        }
    }

    private class Renderer extends Thread {
        volatile boolean stop = false;
        private final SurfaceHolder holder;
        private MappedByteBuffer map;
        int fw = 720, fh = 1560;
        private Bitmap bmp;
        private final Paint paint = new Paint();

        Renderer(SurfaceHolder h) { this.holder = h; }

        private File findFile() {
            String[] cands = new String[]{
                    "/sdcard/fbdir/Xvfb_screen0",
                    "/storage/emulated/0/fbdir/Xvfb_screen0",
                    "/sdcard/.tlf"
            };
            for (String p : cands) {
                try {
                    File f = new File(p);
                    if (f.exists()) { Log.i(TAG, "frame file: " + p + " len=" + f.length()); return f; }
                } catch (Throwable ignored) {}
            }
            return null;
        }

        private boolean isFbdir = false;

        private boolean open() {
            try {
                File f = findFile();
                if (f == null) { Log.w(TAG, "frame file not found"); return false; }
                RandomAccessFile raf = new RandomAccessFile(f, "r");
                FileChannel ch = raf.getChannel();
                mapSize = ch.size();
                map = ch.map(FileChannel.MapMode.READ_ONLY, 0, ch.size());
                map.order(ByteOrder.BIG_ENDIAN);
                byte[] mg = new byte[4];
                map.position(0); map.get(mg);
                String magic = new String(mg, "US-ASCII");

                if ("TLFM".equals(magic)) {
                    // 老格式 .tlf
                    fw = map.getInt(8);
                    fh = map.getInt(12);
                    isFbdir = false;
                    Log.i(TAG, "TLFM " + fw + "x" + fh);
                } else {
                    // XWD 格式（Xvfb -fbdir）
                    // 【关键】header_size 字段不包含 colormap！
                    // 真实像素起点 = header_size + ncolors*12
                    // 否则画面会被环绕平移（实测偏 768 像素）
                    map.position(0);
                    int hs = map.getInt();
                    map.position(16);
                    fw = map.getInt();
                    fh = map.getInt();
                    map.position(76);            // ncolors 在第 19 个 int
                    int ncolors = map.getInt();
                    int pixOff = hs + ncolors * 12;
                    // 兜底：用文件长度反推，更可靠
                    long real = (long) mapSize - (long) fw * fh * 4;
                    if (real > 0 && real < Integer.MAX_VALUE && real >= pixOff) {
                        pixOff = (int) real;
                    }
                    HDR_FB = pixOff;
                    isFbdir = true;
                    Log.i(TAG, "XWD " + fw + "x" + fh + " hs=" + hs
                            + " ncolors=" + ncolors + " pixOff=" + pixOff);
                }
                bmp = Bitmap.createBitmap(fw, fh, Bitmap.Config.ARGB_8888);
                return true;
            } catch (Throwable t) {
                Log.e(TAG, "open fail", t);
                return false;
            }
        }

        private int HDR_FB = 160;
        private long mapSize = 0;

        /**
         * 零拷贝帧切片：返回从像素起点开始的直接内存视图。
         * MappedByteBuffer 本身就是直接内存，GL 可以直接读，
         * 省掉 byte[] 中转 + 每帧 4MB allocateDirect。
         */
        private java.nio.ByteBuffer frameSlice() {
            int need = fw * fh * 4;
            map.position(HDR_FB);
            java.nio.ByteBuffer sl = map.slice();
            if (sl.remaining() > need) sl.limit(need);
            return sl;
        }

        @Override
        public void run() {
            if (!open()) {
                drawMessage("waiting for /sdcard/fbdir/Xvfb_screen0 ...");
                return;
            }
            long lastSeq = -1;
            byte[] tmp = new byte[fw * fh * 4];
            byte[] prev = new byte[fw * fh * 4];   // 脏检测用的上一帧
            boolean[] dirtyFlags = null;           // 分块脏标记
            final int TILE = 128;                  // 块大小（像素）
            final int IDLE_MS = 20;                // 静止时轮询间隔
            final int ACTIVE_MS = 4;               // 有变化时的间隔
            byte[] prevTmp = new byte[fw * fh * 4];   // 上一帧字节
            int[] rowInt = null;                   // 脏区单行 ARGB 缓冲
            boolean firstFull = true;              // 首帧必须整帧
            boolean lastOvOn = false;
            int partialFrames = 0;                 // 连续脏区帧数
            long fullFrames = 0;                   // 整帧次数（诊断用）
            long scanNs = 0, convNs = 0, drawNs = 0;   // 分阶段耗时
            int[] pxBuf = new int[fw * fh];
            long frames = 0;
            long skipped = 0;
            long tPrev = System.currentTimeMillis();
            long lastFrameAt = System.currentTimeMillis();
            boolean warned = false;
            long lastMtime = 0;

            while (!stop) {
                try {
                    if (webMode) { Thread.sleep(150); continue; }
                    if (isFbdir) {
                        // 模式切换后 Xvfb 会重建文件 → 尺寸变了就重开
                        File ff = new File("/sdcard/fbdir/Xvfb_screen0");
                        long flen = ff.length();
                        if (flen > 0 && flen != mapSize) {
                            Log.i(TAG, "fbdir size changed " + mapSize + " -> " + flen + ", reopening");
                            map = null;
                            if (!open()) { Thread.sleep(400); continue; }
                            tmp = new byte[fw * fh * 4];
                            prevTmp = new byte[fw * fh * 4];
                            rowInt = null;
                            dirtyFlags = null;
                            lastSeq = -1;
                            continue;
                        }
                        // === fbdir 模式：字节级脏检测（不做整帧 int 转换）===
                        map.position(HDR_FB);
                        map.get(tmp);

                        long tScan0 = System.nanoTime();
                        // 快速路径：整帧字节相等 → 直接睡，连分块都不用扫
                        boolean sameFrame = java.util.Arrays.equals(tmp, prevTmp);
                        if (sameFrame && glMode) {
                            // GL 模式：帧没变也要送（首帧/缩放/平移需要重绘）
                            glView.zoom = zoom; glView.panX = panX; glView.panY = panY;
                            glView.pushFrameDirect(frameSlice(), fw, fh);   // 零拷贝
                            System.arraycopy(tmp, 0, prevTmp, 0, tmp.length);
                            glPushed++;
                            if (glPushed % 30 == 0) Log.i(TAG, "GL static push #" + glPushed);
                            Thread.sleep(IDLE_MS);
                            continue;
                        }
                        if (sameFrame) {
                            scanNs += System.nanoTime() - tScan0;
                            skipped++;
                            long nowS = System.currentTimeMillis();
                            if (nowS - tPrev > 5000) {
                                double el = (nowS - tPrev) / 1000.0;
                                double n = Math.max(1, skipped + frames);
                                Log.i(TAG, "fbdir idle: drawn=" + frames + " skipped=" + skipped
                                        + " fps=" + (frames / el)
                                        + " | poll=" + (scanNs / 1e6 / n) + "ms");
                                frames = 0; skipped = 0; tPrev = nowS;
                                scanNs = 0; convNs = 0; drawNs = 0;
                            }
                            lastFrameAt = nowS;
                            Thread.sleep(IDLE_MS);
                            continue;
                        }

                        int rowBytes = fw * 4;
                        int tilesX = (fw + TILE - 1) / TILE;
                        int tilesY = (fh + TILE - 1) / TILE;
                        int dirtyTiles = 0;
                        if (dirtyFlags == null) dirtyFlags = new boolean[tilesX * tilesY];
                        int bMinX = Integer.MAX_VALUE, bMaxX = -1;
                        int bMinY = Integer.MAX_VALUE, bMaxY = -1;

                        for (int ty = 0; ty < tilesY; ty++) {
                            int y0 = ty * TILE;
                            int y1 = Math.min(y0 + TILE, fh);
                            for (int tx = 0; tx < tilesX; tx++) {
                                int x0 = tx * TILE;
                                int x1 = Math.min(x0 + TILE, fw);
                                int nb = (x1 - x0) * 4;
                                boolean diff = false;
                                for (int y = y0; y < y1 && !diff; y++) {
                                    int o = y * rowBytes + x0 * 4;
                                    for (int b = 0; b < nb; b++) {
                                        if (tmp[o + b] != prevTmp[o + b]) { diff = true; break; }
                                    }
                                }
                                dirtyFlags[ty * tilesX + tx] = diff;
                                if (diff) {
                                    dirtyTiles++;
                                    if (x0 < bMinX) bMinX = x0;
                                    if (x1 > bMaxX) bMaxX = x1;
                                    if (y0 < bMinY) bMinY = y0;
                                    if (y1 > bMaxY) bMaxY = y1;
                                }
                            }
                        }
                        scanNs += System.nanoTime() - tScan0;

                        if (dirtyTiles == 0) {
                            // 理论上走不到（整帧不等但每块都等），保险
                            System.arraycopy(tmp, 0, prevTmp, 0, tmp.length);
                            skipped++;
                            Thread.sleep(IDLE_MS);
                            continue;
                        }

                        // 只把脏区转 ARGB 写进 bmp，并同步 prevTmp
                        int bw = bMaxX - bMinX, bh2 = bMaxY - bMinY;
                        long tCv0 = System.nanoTime();
                        if (rowInt == null || rowInt.length < bw) rowInt = new int[bw];
                        for (int y = bMinY; y < bMaxY; y++) {
                            int o = y * rowBytes + bMinX * 4;
                            for (int i = 0; i < bw; i++) {
                                int q = o + i * 4;
                                rowInt[i] = 0xFF000000
                                        | ((tmp[q + 2] & 0xFF) << 16)
                                        | ((tmp[q + 1] & 0xFF) << 8)
                                        | (tmp[q] & 0xFF);
                            }
                            bmp.setPixels(rowInt, 0, bw, bMinX, y, bw, 1);
                        }
                        // 同步脏块到 prevTmp
                        for (int ty = 0; ty < tilesY; ty++) {
                            int y0 = ty * TILE, y1 = Math.min(y0 + TILE, fh);
                            for (int tx = 0; tx < tilesX; tx++) {
                                if (!dirtyFlags[ty * tilesX + tx]) continue;
                                int x0 = tx * TILE, x1 = Math.min(x0 + TILE, fw);
                                int nb = (x1 - x0) * 4;
                                for (int y = y0; y < y1; y++) {
                                    int o = y * rowBytes + x0 * 4;
                                    System.arraycopy(tmp, o, prevTmp, o, nb);
                                }
                            }
                        }
                        convNs += System.nanoTime() - tCv0;

                        updateOverlayState();

                        // ===== GL 模式：把原始 BGRX 直接送给 GPU，跳过 Bitmap/Canvas =====
                        if (glMode) {
                            glView.zoom = zoom; glView.panX = panX; glView.panY = panY;
                            glView.pushFrameDirect(frameSlice(), fw, fh);   // 零拷贝
                            fullFrames++;
                            Thread.sleep(ACTIVE_MS);
                            continue;
                        }

                        long dirtyArea = (long) bw * bh2;
                        long fullArea = (long) fw * fh;

                        long tDr0 = System.nanoTime();
                        // 【必须整帧绘制】Surface 是多 buffer 轮转的，
                        // 只画脏区会让别的 buffer 留着旧帧 → 轮转时闪出旧光标（重影）
                        Rect dst = fit(sv.getWidth(), sv.getHeight());
                        Canvas c = lockBest(holder);
                        if (c != null) {
                            try {
                                c.drawColor(Color.BLACK);
                                c.drawBitmap(bmp, null, dst, paint);
                                if (ovOn) drawOverlay(c);
                            } finally {
                                holder.unlockCanvasAndPost(c);
                            }
                        }
                        fullFrames++;
                        drawNs += System.nanoTime() - tDr0;
                        Thread.sleep(ACTIVE_MS);

                        frames++;
                        lastFrameAt = System.currentTimeMillis();
                        long now0 = lastFrameAt;
                        if (now0 - tPrev > 5000) {
                            double el = (now0 - tPrev) / 1000.0;
                            double n = Math.max(1, frames);
                            Log.i(TAG, "fbdir render fps=" + (frames / el)
                                    + " tiles=" + dirtyTiles + "/" + (tilesX * tilesY)
                                    + " dirty=" + bw + "x" + bh2
                                    + "(" + (dirtyArea * 100 / Math.max(1, fullArea)) + "%)"
                                    + " full=" + fullFrames + " part=" + partialFrames
                                    + " | scan=" + (scanNs / 1e6 / n) + "ms"
                                    + " conv=" + (convNs / 1e6 / n) + "ms"
                                    + " draw=" + (drawNs / 1e6 / n) + "ms");
                            frames = 0; skipped = 0; fullFrames = 0;
                            scanNs = 0; convNs = 0; drawNs = 0;
                            tPrev = now0;
                        }
                        continue;
                    }

                    long seq = map.getLong(24);
                    if (seq == lastSeq) {
                        Thread.sleep(4);
                        // 保险 2：8 秒没有新帧 → 说明容器挂了 → 自动退回小米桌面
                        long idle = System.currentTimeMillis() - lastFrameAt;
                        if (idle > 8000 && !warned) {
                            warned = true;
                            Log.w(TAG, "ESCAPE: no frame for " + idle + "ms, exiting");
                            escapeToMiui();
                        }
                        continue;
                    }
                    lastSeq = seq;
                    lastFrameAt = System.currentTimeMillis();
                    warned = false;

                    // 防撕裂：连读两次 seq，确认读帧期间生产者没有覆盖本槽
                    int slot = (int) ((seq - 1) % NBUF);
                    int off = HDR + slot * fw * fh * 4;

                    // 直接批量拷进 tmp（顺序读，FUSE 页缓存命中很快）
                    map.position(off);
                    map.get(tmp);
                    long seqAfter = map.getLong(24);
                    if (seqAfter - seq >= NBUF) {
                        // 期间被覆盖了，丢掉这一帧
                        continue;
                    }


                    // BGRA -> ARGB
                    ByteBuffer.wrap(tmp).order(ByteOrder.LITTLE_ENDIAN);
                    bmp.copyPixelsFromBuffer(ByteBuffer.wrap(tmp));

                    Canvas c = holder.lockCanvas();
                    if (c != null) {
                        try {
                            c.drawColor(Color.BLACK);
                            Rect dst = fit(c.getWidth(), c.getHeight());
                            c.drawBitmap(bmp, null, dst, paint);
                            updateOverlayState();
                            if (ovOn) drawOverlay(c);
                        } finally {
                            holder.unlockCanvasAndPost(c);
                        }
                    }
                    frames++;
                    long now = System.currentTimeMillis();
                    if (now - tPrev > 5000) {
                        Log.i(TAG, "render fps=" + (frames * 1000.0 / (now - tPrev)));
                        frames = 0; tPrev = now;
                    }
                } catch (Throwable t) {
                    Log.e(TAG, "render loop", t);
                    try { Thread.sleep(200); } catch (InterruptedException ignored) {}
                }
            }
        }

        private Rect fit(int sw, int sh) {
            // 统一走 outer 的 computeFit（含 zoom / pan）
            return computeFit(sw, sh);
        }

        private void drawMessage(String msg) {
            try {
                Canvas c = holder.lockCanvas();
                if (c != null) {
                    c.drawColor(Color.BLACK);
                    Paint p = new Paint();
                    p.setColor(Color.WHITE);
                    p.setTextSize(40);
                    c.drawText(msg, 80, 300, p);
                    holder.unlockCanvasAndPost(c);
                }
            } catch (Throwable ignored) {}
        }
    }
}
