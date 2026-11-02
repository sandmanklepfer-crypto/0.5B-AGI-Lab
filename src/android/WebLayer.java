package com.zhz.tlhome;

import android.app.Activity;
import android.graphics.Color;
import android.os.Build;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

/**
 * WebLayer —— 真 Chromium 层（跑在 untrusted_app 域，走 GPU 合成）
 * 用途一：浏览器（B站/视频/网页版 QQ/微信，全都能跑）
 * 用途二：终端（xterm.js + WebGL 渲染器，文字是真 GPU 画的）
 *
 * 不是 PIL 画皮肤。这里是安卓原生 WebView 组件。
 */
public class WebLayer {
    private static final String TAG = "TLWeb";

    private final Activity act;
    private final FrameLayout root;
    private WebView wv;
    private View closeBtn;
    private volatile boolean showing = false;

    public WebLayer(Activity a, FrameLayout root) {
        this.act = a;
        this.root = root;
    }

    public boolean isShowing() { return showing; }

    private void build() {
        if (wv != null) return;
        wv = new WebView(act);
        WebSettings s = wv.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(true);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        if (Build.VERSION.SDK_INT >= 21) {
            s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }
        wv.setBackgroundColor(Color.parseColor("#0a0d12"));
        wv.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, String url) {
                v.loadUrl(normalize(url));
                return true;
            }
            @Override
            public void onPageFinished(WebView v, String url) {
                Log.i(TAG, "loaded " + url);
            }
        });
        wv.setWebChromeClient(new WebChromeClient());
        // 硬件加速（真 GPU）
        wv.setLayerType(View.LAYER_TYPE_HARDWARE, null);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        root.addView(wv, lp);

        // 左上角关闭热区（48dp 方形，半透明）
        closeBtn = new View(act);
        int sz = (int) (48 * act.getResources().getDisplayMetrics().density);
        FrameLayout.LayoutParams cl = new FrameLayout.LayoutParams(sz, sz);
        cl.gravity = Gravity.TOP | Gravity.LEFT;
        cl.leftMargin = 4;
        cl.topMargin = 4;
        closeBtn.setBackgroundColor(Color.argb(60, 255, 80, 80));
        closeBtn.setOnClickListener(new View.OnClickListener() {
            public void onClick(View v) { hide(); }
        });
        root.addView(closeBtn, cl);
        closeBtn.setVisibility(View.GONE);
    }

    /** 显示一个网址 */
    public void show(final String url) {
        act.runOnUiThread(new Runnable() {
            public void run() {
                build();
                wv.setVisibility(View.VISIBLE);
                closeBtn.setVisibility(View.VISIBLE);
                showing = true;
                String u = url;
                if (u == null || u.length() == 0) u = "https://www.bing.com";
                if (!u.startsWith("http") && !u.startsWith("file")) {
                    if (u.startsWith("term")) u = "http://127.0.0.1:7801/";
                    else if (u.startsWith("btop")) u = "http://127.0.0.1:7801/?c=btop";
                    else u = "http://" + u;
                }
                Log.i(TAG, "load " + u);
                wv.loadUrl(u);
                if (mainHook != null) mainHook.setWebMode(true);
            }
        });
    }

    public void hide() {
        act.runOnUiThread(new Runnable() {
            public void run() {
                if (wv != null) wv.setVisibility(View.GONE);
                if (closeBtn != null) closeBtn.setVisibility(View.GONE);
                showing = false;
                if (mainHook != null) mainHook.setWebMode(false);
            }
        });
    }

    /** 把 App 私有 scheme 转成能开的 https（B站/知乎/微博都会跳自己的 scheme） */
    public static String normalize(String url) {
        if (url == null) return "about:blank";
        String u = url.trim();
        if (u.startsWith("http://") || u.startsWith("https://") || u.startsWith("file://")
                || u.startsWith("about:") || u.startsWith("data:")) return u;
        if (u.startsWith("bilibili://")) {
            String p = u.substring(11);
            p = p.replaceFirst("^video/", "video/");
            return "https://www.bilibili.com/" + p;
        }
        if (u.startsWith("zhihu://")) return "https://www.zhihu.com/" + u.substring(8);
        if (u.startsWith("sinaweibo://")) return "https://m.weibo.cn/";
        if (u.startsWith("taobao://")) return "https://m.taobao.com/";
        if (u.startsWith("intent://")) {
            int i = u.indexOf("scheme=");
            if (i > 0) {
                String rest = u.substring(i + 7);
                int j = rest.indexOf(';');
                String sch = j > 0 ? rest.substring(0, j) : rest;
                return sch + "://";
            }
            return "about:blank";
        }
        int k = u.indexOf("://");
        if (k > 0) {
            String rest = u.substring(k + 3);
            if (rest.startsWith("www.") || rest.contains(".")) return "https://" + rest;
        }
        return "about:blank";
    }

    public boolean goBack() {
        if (wv != null && wv.canGoBack()) { wv.goBack(); return true; }
        return false;
    }

    public void destroy() {
        if (wv != null) { root.removeView(wv); wv.destroy(); wv = null; }
    }

    // 回调给 MainActivity（暂停 framebuffer 渲染，省 CPU）
    public interface Hook { void setWebMode(boolean on); }
    private Hook mainHook;
    public void setHook(Hook h) { mainHook = h; }
}
