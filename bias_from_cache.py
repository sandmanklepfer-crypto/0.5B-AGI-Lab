#!/usr/bin/env python3
"""从反量化缓存生成 bias (秒级): bias = X @ d * alpha
用法: bias_from_cache.py <X.npy> <dir.bin> <alpha> <out.bias.bin>
"""
import sys, numpy as np

def main():
    Xp, dir_p, alpha_s, out_p = sys.argv[1:5]
    alpha = float(alpha_s)
    X = np.load(Xp)                      # (n_vocab, n_embd)
    d = np.fromfile(dir_p, dtype=np.float32)
    d = d / np.linalg.norm(d)
    bias = (X @ d) * alpha
    print(f'bias: mean={bias.mean():+.4f} std={bias.std():.4f} max={bias.max():+.4f} min={bias.min():+.4f}')
    bias.astype(np.float32).tofile(out_p)
    print(f'written {out_p} ({bias.shape[0]} f32, alpha={alpha})')

if __name__ == '__main__':
    main()
