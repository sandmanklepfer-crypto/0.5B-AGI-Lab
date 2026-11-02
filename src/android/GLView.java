package com.zhz.tlhome;

import android.content.Context;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.util.Log;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;

import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;

/**
 * GLView —— 真 GPU 渲染层
 *
 * 旧方案: SurfaceView + lockHardwareCanvas + drawBitmap
 *         → GPU 只做最终合成，缩放靠 Canvas，无法做后处理
 * 新方案: GLSurfaceView + 持久纹理 + 片元着色器
 *         → GPU 做纹理上传 / 缩放过滤 / 锐化 / 色彩校正
 *
 * 着色器承担的实算工作（这就是 GPU 在"算图"，不只是贴图）:
 *   1. 双线性缩放（放大不糊）
 *   2. 3x3 unsharp mask 锐化（小字更清楚）
 *   3. gamma / 亮度 / 对比度校正（解决 Linux 画面偏暗）
 */
public class GLView extends GLSurfaceView {
    private static final String TAG = "TLGL";

    public volatile float zoom = 1.0f;
    public volatile float panX = 0f, panY = 0f;

    public volatile float brightness = 1.0f;
    public volatile float contrast   = 1.0f;
    public volatile float sharpen    = 0.35f;
    public volatile float gamma      = 1.0f;

    private final GLRenderer renderer;

    public GLView(Context c) {
        super(c);
        setEGLContextClientVersion(2);
        setEGLConfigChooser(8, 8, 8, 8, 0, 0);
        renderer = new GLRenderer();
        renderer.view = this;
        setRenderer(renderer);
        setRenderMode(GLSurfaceView.RENDERMODE_CONTINUOUSLY);
        Log.i(TAG, "GLView created");
    }

    /** 送一帧（RGBA8888，w*h*4 字节） */
    public void pushFrame(byte[] rgba, int w, int h) {
        renderer.pushFrame(rgba, w, h);
    }

    /**
     * 零拷贝送帧：直接传直接内存（MappedByteBuffer 切片）。
     * 不需要 byte[] 中转，也不用每帧分配 4MB。
     * 调用方负责保证 buf 从像素起点开始，且至少能读到 w*h*4 字节。
     */
    public void pushFrameDirect(java.nio.ByteBuffer buf, int w, int h) {
        renderer.pushFrameDirect(buf, w, h);
    }

    // ---------------------------------------------------------------
    private static final String VS =
        "attribute vec2 aPos;\n" +
        "uniform mat4 uMVP;\n" +
        "varying vec2 vUV;\n" +
        "void main(){\n" +
        "  vUV = vec2((aPos.x+1.0)*0.5, 1.0-(aPos.y+1.0)*0.5);\n" +
        "  gl_Position = uMVP * vec4(aPos, 0.0, 1.0);\n" +
        "}\n";

    private static final String FS =
        "precision mediump float;\n" +
        "varying vec2 vUV;\n" +
        "uniform sampler2D uTex;\n" +
        "uniform vec2  uTexel;\n" +
        "uniform float uBright;\n" +
        "uniform float uContrast;\n" +
        "uniform float uSharpen;\n" +
        "uniform float uGamma;\n" +
        "void main(){\n" +
        "  vec3 c = texture2D(uTex, vUV).bgr;\n" +   // fbdir 是 BGRX，交换 R/B
        "  if (uSharpen > 0.001) {\n" +
        "    vec3 n = texture2D(uTex, vUV + vec2( uTexel.x, 0.0)).bgr\n" +
        "           + texture2D(uTex, vUV + vec2(-uTexel.x, 0.0)).bgr\n" +
        "           + texture2D(uTex, vUV + vec2(0.0,  uTexel.y)).bgr\n" +
        "           + texture2D(uTex, vUV + vec2(0.0, -uTexel.y)).rgb;\n" +
        "    n *= 0.25;\n" +
        "    c = c + (c - n) * uSharpen * 2.0;\n" +
        "  }\n" +
        "  c = (c - 0.5) * uContrast + 0.5;\n" +
        "  c = c * uBright;\n" +
        "  c = pow(max(c, 0.0), vec3(1.0/max(0.1, uGamma)));\n" +
        "  gl_FragColor = vec4(clamp(c, 0.0, 1.0), 1.0);\n" +
        "}\n";

    // ---------------------------------------------------------------
    private static class GLRenderer implements GLSurfaceView.Renderer {
        GLView view;

        int prog, tex, aPos, uMVP, uTex, uTexel, uBright, uContrast, uSharpen, uGamma;
        FloatBuffer quad;
        int srcW = 1440, srcH = 696;

        private byte[] back, front;
        private int backW, backH, frontW, frontH;
        private volatile boolean dirty = false;
        private int texW = 0, texH = 0;

        // 零拷贝路径：直接持有直接内存切片
        private java.nio.ByteBuffer backBuf, frontBuf;
        private int backBufW, backBufH, frontBufW, frontBufH;
        private volatile boolean bufDirty = false;
        private java.nio.ByteBuffer reuseBuf;   // byte[] 路径复用，避免每帧 allocateDirect

        synchronized void pushFrame(byte[] rgba, int w, int h) {
            back = rgba; backW = w; backH = h; dirty = true;
        }

        synchronized void pushFrameDirect(java.nio.ByteBuffer buf, int w, int h) {
            backBuf = buf; backBufW = w; backBufH = h; bufDirty = true;
        }

        private int load(int type, String src) {
            int s = GLES20.glCreateShader(type);
            GLES20.glShaderSource(s, src);
            GLES20.glCompileShader(s);
            int[] ok = new int[1];
            GLES20.glGetShaderiv(s, GLES20.GL_COMPILE_STATUS, ok, 0);
            if (ok[0] == 0) {
                Log.e(TAG, "shader fail: " + GLES20.glGetShaderInfoLog(s));
                GLES20.glDeleteShader(s);
                return 0;
            }
            return s;
        }

        public void onSurfaceCreated(GL10 unused, EGLConfig cfg) {
            Log.i(TAG, "=== GPU 上下文建立 ===");
            Log.i(TAG, "  GL_VENDOR   = " + GLES20.glGetString(GLES20.GL_VENDOR));
            Log.i(TAG, "  GL_RENDERER = " + GLES20.glGetString(GLES20.GL_RENDERER));
            Log.i(TAG, "  GL_VERSION  = " + GLES20.glGetString(GLES20.GL_VERSION));

            int vs = load(GLES20.GL_VERTEX_SHADER, VS);
            int fs = load(GLES20.GL_FRAGMENT_SHADER, FS);
            prog = GLES20.glCreateProgram();
            GLES20.glAttachShader(prog, vs);
            GLES20.glAttachShader(prog, fs);
            GLES20.glLinkProgram(prog);
            int[] ok = new int[1];
            GLES20.glGetProgramiv(prog, GLES20.GL_LINK_STATUS, ok, 0);
            if (ok[0] == 0) Log.e(TAG, "link fail: " + GLES20.glGetProgramInfoLog(prog));

            aPos      = GLES20.glGetAttribLocation(prog, "aPos");
            uMVP      = GLES20.glGetUniformLocation(prog, "uMVP");
            uTex      = GLES20.glGetUniformLocation(prog, "uTex");
            uTexel    = GLES20.glGetUniformLocation(prog, "uTexel");
            uBright   = GLES20.glGetUniformLocation(prog, "uBright");
            uContrast = GLES20.glGetUniformLocation(prog, "uContrast");
            uSharpen  = GLES20.glGetUniformLocation(prog, "uSharpen");
            uGamma    = GLES20.glGetUniformLocation(prog, "uGamma");

            float[] q = { -1f,-1f,  1f,-1f,  -1f,1f,  1f,1f };
            quad = ByteBuffer.allocateDirect(q.length * 4)
                    .order(ByteOrder.nativeOrder()).asFloatBuffer();
            quad.put(q).position(0);

            int[] t = new int[1];
            GLES20.glGenTextures(1, t, 0);
            tex = t[0];
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex);
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR);
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR);
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE);
            GLES20.glTexParameteri(GLES20.GL_TEXTURE_2D, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE);
            Log.i(TAG, "GL init done, tex=" + tex + " aPos=" + aPos);
        }

        public void onSurfaceChanged(GL10 unused, int w, int h) {
            GLES20.glViewport(0, 0, w, h);
            Log.i(TAG, "surface " + w + "x" + h);
        }

        public void onDrawFrame(GL10 unused) {
            GLES20.glClearColor(0.02f, 0.025f, 0.035f, 1f);
            GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);

            synchronized (this) {
                if (bufDirty && backBuf != null) {
                    frontBuf = backBuf; frontBufW = backBufW; frontBufH = backBufH;
                    backBuf = null; bufDirty = false;
                    uploadTextureDirect(frontBuf, frontBufW, frontBufH);
                } else if (dirty && back != null) {
                    front = back; frontW = backW; frontH = backH;
                    back = null; dirty = false;
                    frontBuf = null;
                    uploadTexture();
                }
            }
            if (front == null && frontBuf == null) return;

            GLView v = view;
            float z  = v != null ? v.zoom : 1f;
            float px = v != null ? v.panX : 0f;
            float py = v != null ? v.panY : 0f;

            GLES20.glUseProgram(prog);
            GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex);
            GLES20.glUniform1i(uTex, 0);
            GLES20.glUniform2f(uTexel, 1f / Math.max(1, texW), 1f / Math.max(1, texH));

            if (v != null) {
                GLES20.glUniform1f(uBright,   v.brightness);
                GLES20.glUniform1f(uContrast, v.contrast);
                GLES20.glUniform1f(uSharpen,  v.sharpen);
                GLES20.glUniform1f(uGamma,    v.gamma);
            }

            float s = 1f / Math.max(0.05f, z);
            float tx = px * 2f / Math.max(1, frontW) * s;
            float ty = -py * 2f / Math.max(1, frontH) * s;
            float[] mvp = {
                s, 0, 0, 0,
                0, s, 0, 0,
                0, 0, 1, 0,
                tx, ty, 0, 1
            };
            GLES20.glUniformMatrix4fv(uMVP, 1, false, mvp, 0);

            GLES20.glEnableVertexAttribArray(aPos);
            GLES20.glVertexAttribPointer(aPos, 2, GLES20.GL_FLOAT, false, 0, quad);
            GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);
            GLES20.glDisableVertexAttribArray(aPos);
        }

        /** 公共上传：data 必须从像素起点开始 */
        private void uploadBuffer(ByteBuffer data, int w, int h) {
            if (data == null || w <= 0 || h <= 0) return;
            GLES20.glBindTexture(GLES20.GL_TEXTURE_2D, tex);
            if (texW != w || texH != h) {
                GLES20.glTexImage2D(GLES20.GL_TEXTURE_2D, 0, GLES20.GL_RGBA,
                        w, h, 0, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, data);
                texW = w; texH = h;
                Log.i(TAG, "tex alloc " + w + "x" + h);
            } else {
                GLES20.glTexSubImage2D(GLES20.GL_TEXTURE_2D, 0, 0, 0,
                        w, h, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, data);
            }
        }

        /** 零拷贝：MappedByteBuffer 切片直接送 GPU，不经过 byte[] */
        private void uploadTextureDirect(ByteBuffer buf, int w, int h) {
            if (buf == null) return;
            uploadBuffer(buf, w, h);
        }

        /** byte[] 路径：复用 direct buffer，避免每帧 4MB allocateDirect */
        private void uploadTexture() {
            if (front == null || frontW <= 0 || frontH <= 0) return;
            if (reuseBuf == null || reuseBuf.capacity() < front.length) {
                reuseBuf = ByteBuffer.allocateDirect(front.length)
                        .order(ByteOrder.nativeOrder());
                Log.i(TAG, "reuseBuf alloc " + front.length);
            }
            reuseBuf.clear();
            reuseBuf.put(front);
            reuseBuf.position(0);
            uploadBuffer(reuseBuf, frontW, frontH);
        }
    }
}
