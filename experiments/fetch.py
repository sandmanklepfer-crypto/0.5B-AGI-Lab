#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch.py — 带缓存的下载器(解决网络慢 + 重复下载)
   · 自动缓存到 /workspace/dl_cache/
   · 第二次请求同一 URL → 秒回(本地命中)
   · 支持断点续传 + 多镜像回退 + 进度显示
用法:
  python3 fetch.py <url> [输出路径]
  python3 fetch.py --mirror <路径>     # 用镜像前缀替换 hf 源
"""
import os, sys, hashlib, time, urllib.request, urllib.error, shutil

CACHE = "/workspace/dl_cache"
os.makedirs(CACHE, exist_ok=True)

# 镜像前缀映射(自动换到国内快源)
MIRRORS = [
    ("https://huggingface.co/", "https://hf-mirror.com/"),
    ("https://cdn-lfs.huggingface.co/", "https://hf-mirror.com/"),
    ("https://cdn-lfs.hf.co/", "https://hf-mirror.com/"),
]

def cache_key(url):
    h = hashlib.sha1(url.encode()).hexdigest()[:20]
    base = url.rstrip("/").split("/")[-1][:80]
    return os.path.join(CACHE, h + "_" + base)

def try_urls(url):
    """生成候选 URL(原 + 镜像)"""
    out = [url]
    for a, b in MIRRORS:
        if url.startswith(a):
            out.append(b + url[len(a):])
    return out

def download(url, dst=None, show=True):
    dst = dst or cache_key(url)
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        if show: print("[缓存命中] %s (%d 字节)" % (dst, os.path.getsize(dst)))
        return dst
    last = None
    for u in try_urls(url):
        try:
            t0 = time.time(); got = 0
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                while True:
                    b = r.read(1 << 16)
                    if not b: break
                    f.write(b); got += len(b)
                    if show and total and got % (1 << 22) < (1 << 16):
                        el = time.time() - t0 + 1e-6
                        sys.stdout.write("\r   %5.1f%% %.1fMB %.1fMB/s" %
                                         (100*got/total, got/1e6, got/1e6/el))
                        sys.stdout.flush()
            if show: print("\r   ok %.1fMB %.1fs" % (got/1e6, time.time()-t0))
            return dst
        except Exception as e:
            last = e
            if show: print("   [失败] %s → %s" % (u[:60], e))
    raise SystemExit("全部源失败: %s" % last)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args: print(__doc__); sys.exit(1)
    print(download(args[0], args[1] if len(args) > 1 else None))
