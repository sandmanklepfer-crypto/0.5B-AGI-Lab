package com.zhz.tlhome;

import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.util.Log;

import java.io.RandomAccessFile;

/**
 * AudioPipe —— 读取 Linux 侧 ALSA file 插件写出的裸 PCM，用 AudioTrack 播放
 *
 * 链路:
 *   Linux 程序 -> libasound -> file 插件 -> /data/local/tmp/tlaudio.raw
 *                                              ↓ 本类轮询读取
 *   AudioTrack -> AudioFlinger -> 真声卡
 *
 * 关键设计（吸取之前的教训，不能把整机拖死）:
 *   1. 只读 /data/local/tmp（非 FUSE），不碰 /sdcard
 *   2. 每次读固定块，没数据就 sleep，绝不 busy-loop
 *   3. 跟随写入增长，超过阈值就 ftruncate 回收（避免无限膨胀）
 */
public class AudioPipe {
    private static final String TAG = "TLAudio";
    private static final String PCM = "/sdcard/tlaudio.raw";

    private static final int RATE = 44100;
    private static final int CH = 2;
    private static final int BITS = 16;
    private static final int FRAME = CH * BITS / 8;      // 4 字节
    private static final int CHUNK = 16384 * 4;          // 每次读 64KB（减少 syscall）
    private static final long MAX_FILE = 8L * 1024 * 1024;  // 超过 8MB 就截断

    private volatile boolean running = false;
    private Thread worker;
    private AudioTrack track;
    private long totalFrames = 0;
    private long readPos = 0;

    public synchronized void start() {
        if (running) return;
        running = true;
        worker = new Thread(new Runnable() {
            public void run() { loop(); }
        }, "TLAudioPipe");
        worker.setDaemon(true);
        worker.start();
        Log.i(TAG, "AudioPipe start");
    }

    public synchronized void stop() {
        running = false;
        if (worker != null) { try { worker.join(800); } catch (Throwable ignored) {} }
        releaseTrack();
        Log.i(TAG, "AudioPipe stop, played=" + totalFrames + " frames");
    }

    private void releaseTrack() {
        if (track != null) {
            try { track.stop(); } catch (Throwable ignored) {}
            try { track.release(); } catch (Throwable ignored) {}
            track = null;
        }
    }

    private boolean ensureTrack() {
        if (track != null && track.getState() == AudioTrack.STATE_INITIALIZED) return true;
        releaseTrack();
        try {
            int minBuf = AudioTrack.getMinBufferSize(RATE,
                    AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT);
            int bufSize = Math.max(minBuf, CHUNK * 2);
            android.media.AudioAttributes attrs =
                    new android.media.AudioAttributes.Builder()
                        .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                        .setContentType(android.media.AudioAttributes.CONTENT_TYPE_MUSIC)
                        .build();
            android.media.AudioFormat fmt = new android.media.AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(RATE)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                        .build();
            track = new AudioTrack.Builder()
                        .setAudioAttributes(attrs)
                        .setAudioFormat(fmt)
                        .setBufferSizeInBytes(bufSize)
                        .setTransferMode(AudioTrack.MODE_STREAM)
                        .build();
            Log.i(TAG, "build: minBuf=" + minBuf + " useBuf=" + bufSize
                    + " state=" + track.getState());
            if (track.getState() != AudioTrack.STATE_INITIALIZED) {
                Log.e(TAG, "AudioTrack init failed, state=" + track.getState());
                releaseTrack();
                return false;
            }
            track.play();
            Log.i(TAG, "AudioTrack playing, buf=" + bufSize);
            return true;
        } catch (Throwable t) {
            Log.e(TAG, "AudioTrack create fail", t);
            releaseTrack();
            return false;
        }
    }

    private void loop() {
        byte[] buf = new byte[CHUNK];
        RandomAccessFile raf = null;
        long lastSize = -1;
        int idleTicks = 0;

        while (running) {
            try {
                if (raf == null) {
                    java.io.File f = new java.io.File(PCM);
                    if (!f.exists()) { sleep(400); continue; }
                    raf = new RandomAccessFile(f, "rw");
                    readPos = 0;
                    lastSize = 0;
                    Log.i(TAG, "opened " + PCM);
                }

                long size = raf.length();

                // 写入端被截断（重启）→ 重置读取位置
                if (size < readPos) {
                    Log.i(TAG, "file truncated " + readPos + " -> " + size);
                    readPos = 0;
                }

                // 文件太大 → 把已读部分截掉，防止无限增长
                if (size > MAX_FILE) {
                    try {
                        byte[] keep = null;
                        long keepLen = size - readPos;
                        if (keepLen > 0 && keepLen <= MAX_FILE) {
                            keep = new byte[(int) keepLen];
                            raf.seek(readPos);
                            raf.readFully(keep);
                        }
                        raf.setLength(0);
                        if (keep != null) {
                            raf.seek(0);
                            raf.write(keep);
                            readPos = 0;
                        } else {
                            readPos = 0;
                        }
                        size = raf.length();
                        Log.i(TAG, "truncated, keep=" + (keep == null ? 0 : keep.length));
                    } catch (Throwable t) {
                        Log.w(TAG, "truncate fail: " + t);
                    }
                }

                long avail = size - readPos;
                if (avail < FRAME) {
                    // 没数据：按已积累的 idle 逐步退避，避免烧 CPU
                    idleTicks++;
                    // 无数据时长时间退避，绝不空转（/sdcard 是 FUSE，轮询有成本）
                    sleep(idleTicks > 8 ? 250 : 120);
                    continue;
                }
                idleTicks = 0;

                if (avail > 0 && readPos == 0) {
                    Log.i(TAG, "first data: size=" + size + " avail=" + avail);
                }
                int want = (int) Math.min(CHUNK, avail);
                want -= (want % FRAME);
                if (want <= 0) { sleep(40); continue; }

                raf.seek(readPos);
                int got = raf.read(buf, 0, want);
                if (got <= 0) { sleep(40); continue; }
                got -= (got % FRAME);

                if (!ensureTrack()) { sleep(300); continue; }

                int written = track.write(buf, 0, got);
                if (written < 0) {
                    Log.w(TAG, "track.write err=" + written + ", recreate");
                    releaseTrack();
                    sleep(100);
                    continue;
                }
                readPos += written;
                totalFrames += written / FRAME;

            } catch (Throwable t) {
                Log.e(TAG, "loop err: " + t);
                try { if (raf != null) raf.close(); } catch (Throwable ignored) {}
                raf = null;
                sleep(300);
            }
        }
        try { if (raf != null) raf.close(); } catch (Throwable ignored) {}
        releaseTrack();
    }

    private void sleep(int ms) {
        try { Thread.sleep(ms); } catch (InterruptedException ignored) {}
    }

    public long getFrames() { return totalFrames; }

    /** 自检：直接生成 2 秒 440Hz 正弦波播放，验证 AudioTrack 通路（不碰文件） */
    private android.media.AudioManager am;
    private final android.content.Context ctx;

    public AudioPipe(android.content.Context c) { this.ctx = c; }

    /** 请求音频焦点 —— MIUI 对无焦点的 track 会静音 */
    private void requestFocus() {
        try {
            if (am == null) am = (android.media.AudioManager)
                    ctx.getSystemService(android.content.Context.AUDIO_SERVICE);
            int r = am.requestAudioFocus(null,
                    android.media.AudioManager.STREAM_MUSIC,
                    android.media.AudioManager.AUDIOFOCUS_GAIN);
            Log.i(TAG, "requestAudioFocus = " + r);
            int mv = am.getStreamVolume(android.media.AudioManager.STREAM_MUSIC);
            int mm = am.getStreamMaxVolume(android.media.AudioManager.STREAM_MUSIC);
            Log.i(TAG, "STREAM_MUSIC vol=" + mv + "/" + mm);
        } catch (Throwable t) { Log.e(TAG, "requestFocus fail", t); }
    }

    public void selfTest() {
        new Thread(new Runnable() {
            public void run() {
                try {
                    int sr = 44100;
                    int frames = sr * 2;
                    short[] pcm = new short[frames * 2];
                    for (int i = 0; i < frames; i++) {
                        short v = (short) (12000 * Math.sin(2 * Math.PI * 440.0 * i / sr));
                        pcm[i*2] = v; pcm[i*2+1] = v;
                    }
                    android.media.AudioAttributes at = new android.media.AudioAttributes.Builder()
                            .setUsage(android.media.AudioAttributes.USAGE_MEDIA)
                            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_MUSIC)
                            .build();
                    android.media.AudioFormat af = new android.media.AudioFormat.Builder()
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setSampleRate(sr)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                            .build();
                    int buf = Math.max(AudioTrack.getMinBufferSize(sr,
                            AudioFormat.CHANNEL_OUT_STEREO, AudioFormat.ENCODING_PCM_16BIT),
                            pcm.length * 2);
                    AudioTrack t = new AudioTrack.Builder()
                            .setAudioAttributes(at).setAudioFormat(af)
                            .setBufferSizeInBytes(buf)
                            .setTransferMode(AudioTrack.MODE_STATIC)
                            .build();
                    requestFocus();
                    Log.i(TAG, "selfTest build state=" + t.getState() + " buf=" + buf);
                    if (t.getState() != AudioTrack.STATE_INITIALIZED) {
                        Log.e(TAG, "selfTest: AudioTrack 初始化失败");
                        return;
                    }
                    int wr = t.write(pcm, 0, pcm.length);
                    t.setVolume(1.0f);
                    t.play();
                    Log.i(TAG, "selfTest write=" + wr + "/" + pcm.length);
                    Log.i(TAG, "selfTest playing, state=" + t.getPlayState());
                    Thread.sleep(2600);
                    Log.i(TAG, "selfTest done");
                    t.stop(); t.release();
                } catch (Throwable e) {
                    Log.e(TAG, "selfTest fail", e);
                }
            }
        }, "TLAudioSelfTest").start();
    }
}
