#!/usr/bin/env python3
"""一次性反量化 output.weight → npy 缓存 (之后任意方向出 bias 都是秒级)
用法: dequant_cache.py <model.gguf> <out.npy>
"""
import struct, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gguf_inspect import GGUF

QK = 256
BS = 210

def dequant_q6k(arr, n_elem):
    nb = n_elem // QK
    a = np.frombuffer(arr, dtype=np.uint8).reshape(nb, BS)
    ql = a[:, 0:128]
    qh = a[:, 128:192]
    sc = a[:, 192:208].astype(np.int16)
    sc[sc > 127] -= 256
    d = np.array([struct.unpack('<e', a[i, 208:210].tobytes())[0] for i in range(nb)], dtype=np.float32)
    out = np.zeros((nb, QK), dtype=np.float32)
    l = np.arange(32)
    is_ = l // 16
    for half in range(2):
        ql0 = ql[:, half*64:(half+1)*64]
        qh0 = qh[:, half*32:(half+1)*32]
        q1 = ((ql0[:, l] & 0x0F) | ((qh0[:, l] >> 0 & 0x03) << 4)).astype(np.int16) - 32
        q2 = ((ql0[:, l+32] & 0x0F) | ((qh0[:, l] >> 2 & 0x03) << 4)).astype(np.int16) - 32
        q3 = ((ql0[:, l] >> 4) | ((qh0[:, l] >> 4 & 0x03) << 4)).astype(np.int16) - 32
        q4 = ((ql0[:, l+32] >> 4) | ((qh0[:, l] >> 6 & 0x03) << 4)).astype(np.int16) - 32
        s1 = sc[:, is_]; s2 = sc[:, is_ + 2]; s3 = sc[:, is_ + 4]; s4 = sc[:, is_ + 6]
        base = half * 128
        out[:, base+0:base+32] = d[:, None] * s1 * q1
        out[:, base+32:base+64] = d[:, None] * s2 * q2
        out[:, base+64:base+96] = d[:, None] * s3 * q3
        out[:, base+96:base+128] = d[:, None] * s4 * q4
    return out.reshape(-1)

def main():
    model_path, out_npy = sys.argv[1:3]
    g = GGUF(model_path)
    t = None
    for t in g.tensors:
        if t['name'] == 'output.weight':
            break
    dims = t['dims']
    n_embd, n_vocab = int(dims[0]), int(dims[1])
    n_elem = n_embd * n_vocab
    g.f.seek(g.abs_off(t))
    raw = g.f.read((n_elem // QK) * BS)
    X = dequant_q6k(raw, n_elem).reshape(n_vocab, n_embd)
    np.save(out_npy, X)
    print(f'cached {out_npy}: X {X.shape} ({X.nbytes/1e9:.2f} GB)')

if __name__ == '__main__':
    main()
