#!/usr/bin/env python3
"""mean口径分析: 从 dump_layers 输出 (每文件=一段文本的N层激活) 算有效维/adj-cos/范数剖面
用法: analyze_mean.py <glob_pattern> <n_layers> <n_embd> <tag>
"""
import sys, glob, struct
import numpy as np

def main():
    pat, n_layers, n_embd, tag = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    files = sorted(glob.glob(pat))
    print(f"[{tag}] files={len(files)} layers={n_layers} dim={n_embd}")
    if not files:
        return
    # 每层累积 900×d
    layers = []
    for l in range(n_layers):
        rows = []
        for fp in files:
            with open(fp, 'rb') as f:
                nl, ne = struct.unpack('<2i', f.read(8))
                f.seek(8 + l * ne * 4)
                rows.append(np.fromfile(f, dtype=np.float32, count=ne))
        layers.append(np.stack(rows))
    L = len(layers)
    print(f"矩阵: {layers[0].shape}", flush=True)

    # adj-cos (层间 mean 向量 cos, 每段对齐)
    cos_adj = []
    for l in range(L - 1):
        a, b = layers[l], layers[l + 1]
        c = np.mean(np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12))
        cos_adj.append(c)
    print(f"[adj-cos] 均值={np.mean(cos_adj):+.4f}", flush=True)
    print(f"[adj-cos by-layer] {['%.3f' % c for c in cos_adj]}", flush=True)

    offs = []
    for i in range(0, L, 2):
        for j in range(0, L, 2):
            if abs(i - j) >= 3:
                a, b = layers[i], layers[j]
                c = np.mean(np.sum(a * b, axis=1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1) + 1e-12))
                offs.append(abs(c))
    print(f"[off-diag|cos|] 均值={np.mean(offs):.4f}", flush=True)

    print("[eff-dim] ", end="", flush=True)
    for l in [0, 1, 2, 3, 5, 8, 12, 16, 20, 24, 30, 40, 50, 60, L - 2, L - 1]:
        if l >= L:
            continue
        M = layers[l] - layers[l].mean(0, keepdims=True)
        C = M @ M.T  # n×n
        w = np.linalg.eigvalsh(C)
        w = np.clip(w[::-1], 0, None)
        cum = np.cumsum(w) / (np.sum(w) + 1e-12)
        k50 = int(np.searchsorted(cum, 0.50) + 1)
        k90 = int(np.searchsorted(cum, 0.90) + 1)
        k99 = int(np.searchsorted(cum, 0.99) + 1)
        print(f"L{l}:{k50}/{k90}/{k99} ", end="", flush=True)
    print("", flush=True)

    norms = [np.linalg.norm(a, axis=1).mean() for a in layers]
    print(f"[norm-profile] {['%.1f' % n for n in norms]}", flush=True)
    rel = [norms[i] / max(norms[1], 1e-9) for i in range(len(norms))]
    print(f"[norm-rel(L1=1)] {['%.2f' % r for r in rel]}", flush=True)
    print("ANALYZE_DONE", flush=True)

if __name__ == "__main__":
    main()
