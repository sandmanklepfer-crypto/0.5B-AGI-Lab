package com.zhz.tlhome;

import android.content.Context;
import android.net.LocalSocket;
import android.net.LocalSocketAddress;
import android.util.Log;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;

/**
 * VaRelay —— 让 shell 域用上 VPU 硬解的"合法外衣"
 *
 * 问题：termux-va daemon 必须以 untrusted_app 域跑（要 binder 到 MediaCodec），
 *      而 Linux 侧在 shell 域，跨域连 unix socket 被 DAC(0700) + SELinux MCS 双拒。
 * 方案：本类活在 App 进程里，天然 untrusted_app：
 *    1) 从 /sdcard/tva 复制 termux-va 到私有目录并 chmod 700
 *    2) 用私有目录做 socket dir 起 daemon（untrusted_app 建 socket 允许）
 *    3) 127.0.0.1:7820 开 TCP，纯字节转发到那个 unix socket
 * Linux 侧用 vatcp.so 把 connect("/…/termux-va.sock") 偷换成 TCP:7820，
 * 并把握手 xfer 改成 0(inline)，从而不需要跨域传 memfd。
 */
public class VaRelay {
    private static final String TAG = "TLVa";
    public static final int TCP_PORT = 7820;

    private final Context ctx;
    private Process proc;
    private volatile boolean running = false;

    public VaRelay(Context c) { this.ctx = c; }

    public String sockPath() {
        return new File(sockDir(), "termux-va.sock").getAbsolutePath();
    }

    private File sockDir() { return new File(ctx.getFilesDir(), "tva"); }

    private boolean installDaemon() {
        File dst = new File(ctx.getFilesDir(), "termux-va");
        if (dst.exists() && dst.length() > 30000) { setExec(dst); return true; }

        File src = new File("/sdcard/tva/termux-va");
        if (!src.exists()) { Log.e(TAG, "缺 /sdcard/tva/termux-va"); return false; }
        try {
            InputStream in = new FileInputStream(src);
            FileOutputStream out = new FileOutputStream(dst);
            byte[] b = new byte[65536];
            int n;
            while ((n = in.read(b)) > 0) out.write(b, 0, n);
            out.close(); in.close();
            setExec(dst);
            Log.i(TAG, "复制 daemon 成功: " + dst.length() + " 字节");
            return dst.length() > 30000;
        } catch (Exception e) {
            Log.e(TAG, "复制失败: " + e);
            return false;
        }
    }

    private void setExec(File f) {
        try {
            Runtime.getRuntime().exec(new String[]{"chmod", "700", f.getAbsolutePath()}).waitFor();
        } catch (Exception ignored) { }
        f.setExecutable(true, true);
    }

    private boolean startDaemon() {
        try {
            File dir = sockDir();
            if (!dir.exists()) dir.mkdirs();
            File bin = new File(ctx.getFilesDir(), "termux-va");
            if (!bin.exists()) return false;

            // 关键：清掉上一个 App 实例遗留的孤儿 daemon 和旧 socket。
            // 否则新 daemon bind 失败退出，旧 daemon（session 已泄漏满 8 个）继续服务，
            // 所有新连接都被 "concurrent session limit 8 reached" 拒绝。
            try {
                Process k = new ProcessBuilder("sh", "-c",
                        "pkill -f termux-va; sleep 1; rm -f " + sockPath()).start();
                k.waitFor();
                Log.i(TAG, "已清理旧 daemon 与 socket");
            } catch (Exception e) {
                Log.w(TAG, "清理旧 daemon 失败: " + e);
            }

            ProcessBuilder pb = new ProcessBuilder(bin.getAbsolutePath());
            pb.environment().put("TERMUX_VA_SOCKET_DIR", dir.getAbsolutePath());
            pb.environment().put("TMPDIR", ctx.getCacheDir().getAbsolutePath());
            pb.directory(ctx.getFilesDir());
            pb.redirectErrorStream(true);
            proc = pb.start();

            final InputStream is = proc.getInputStream();
            new Thread(new Runnable() {
                public void run() {
                    byte[] b = new byte[1024];
                    try {
                        int n;
                        while ((n = is.read(b)) > 0) {
                            String s = new String(b, 0, n).trim();
                            if (s.length() > 0) Log.i(TAG, "daemon: " + s);
                        }
                    } catch (Exception ignored) { }
                }
            }, "va-daemon-log").start();

            File sock = new File(sockPath());
            for (int i = 0; i < 120; i++) {
                if (sock.exists()) { Log.i(TAG, "socket 就绪: " + sockPath()); return true; }
                Thread.sleep(100);
            }
            Log.e(TAG, "socket 未出现（daemon 可能失败）");
            return false;
        } catch (Exception e) {
            Log.e(TAG, "起 daemon 失败: " + e);
            return false;
        }
    }

    public void start() {
        if (running) return;
        running = true;
        new Thread(new Runnable() {
            public void run() {
                if (!installDaemon()) return;
                if (!startDaemon()) return;
                try {
                    ServerSocket ss = new ServerSocket(TCP_PORT, 8,
                            InetAddress.getByName("127.0.0.1"));
                    Log.i(TAG, "TCP 中继 127.0.0.1:" + TCP_PORT + " -> " + sockPath());
                    while (running) {
                        final Socket cli = ss.accept();
                        new Thread(new Runnable() {
                            public void run() { bridge(cli); }
                        }, "va-bridge").start();
                    }
                } catch (Exception e) {
                    Log.e(TAG, "TCP 服务失败: " + e);
                }
            }
        }, "va-relay").start();
    }

    /** 一条 TCP <-> 一条 unix socket，纯字节双向泵 */
    private void bridge(Socket cli) {
        LocalSocket ls = new LocalSocket();
        try {
            ls.connect(new LocalSocketAddress(sockPath(),
                    LocalSocketAddress.Namespace.FILESYSTEM));

            final InputStream uin = ls.getInputStream();
            final OutputStream uout = ls.getOutputStream();
            final InputStream cin = cli.getInputStream();
            final OutputStream cout = cli.getOutputStream();
            Log.i(TAG, "桥接建立: " + cli.getRemoteSocketAddress());

            Thread t = new Thread(new Runnable() {
                public void run() {
                    byte[] b = new byte[65536];
                    try {
                        int n;
                        while ((n = cin.read(b)) > 0) { uout.write(b, 0, n); uout.flush(); }
                    } catch (Exception ignored) { }
                    // TCP 半关闭：只关 unix 的写端，别整个关掉。
                    // 协议里客户端会 shutdown(SHUT_WR) 表示 EOS，daemon 还要继续回帧。
                    try { ls.shutdownOutput(); } catch (Exception ignored) { }
                }
            }, "va-tcp2unix");
            t.start();

            byte[] b = new byte[65536];
            int n;
            while ((n = uin.read(b)) > 0) { cout.write(b, 0, n); cout.flush(); }
            t.join(2000);
            Log.i(TAG, "桥接结束");
        } catch (Exception e) {
            Log.e(TAG, "bridge: " + e);
        } finally {
            try { ls.close(); } catch (Exception ignored) { }
            try { cli.close(); } catch (Exception ignored) { }
        }
    }

    public void stop() {
        running = false;
        if (proc != null) { proc.destroy(); proc = null; }
    }
}
