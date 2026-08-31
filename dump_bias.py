#!/usr/bin/env python3
"""权重手术: 方向 → lm_head bias (q6_k 反量化 + W@d)
用法: dump_bias.py <model.gguf> <dir.bin> <alpha> <out.bias.bin>
"""
import struct, sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gguf_inspect import GGUF

QK = 256
BS = 210  # q6_k block bytes

def dequant_q6k(arr, n_elem):
    """arr: raw bytes -> float32 array (n_elem,)"""
    nb = n_elem // QK
    a = np.frombuffer(arr, dtype=np.uint8).reshape(nb, BS)
    ql = a[:, 0:128]          # (nb,128)
    qh = a[:, 128:192]        # (nb,64)
    sc = a[:, 192:208].astype(np.int16)
    sc[sc > 127] -= 256       # int8
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
        s1 = sc[:, is_]        # q1 scale: is+0
        s2 = sc[:, is_ + 2]
        s3 = sc[:, is_ + 4]
        s4 = sc[:, is_ + 6]
        base = half * 128
        out[:, base+0:base+32] = d[:, None] * s1 * q1
        out[:, base+32:base+64] = d[:, None] * s2 * q2
        out[:, base+64:base+96] = d[:, None] * s3 * q3
        out[:, base+96:base+128] = d[:, None] * s4 * q4
    return out.reshape(-1)

def main():
    model_path, dir_path, alpha_s, out_path = sys.argv[1:5]
    alpha = float(alpha_s)

    g = GGUF(model_path)
    t = None
    for t in g.tensors:
        if t['name'] == 'output.weight':
            break
    if t is None or t['name'] != 'output.weight':
        print('output.weight not found'); sys.exit(1)
    dims = t['dims']  # (5120, 152064)
    n_embd, n_vocab = int(dims[0]), int(dims[1])
    n_elem = n_embd * n_vocab
    print(f'output.weight: {n_embd}x{n_vocab} type={t["type"]} off={t["offset"]}')

    g.f.seek(g.abs_off(t))
    raw = g.f.read((n_elem // QK) * BS)
    print(f'raw {len(raw)} bytes')
    X = dequant_q6k(raw, n_elem).reshape(n_vocab, n_embd)
    print(f'dequant OK: X {X.shape}, mem {X.nbytes/1e9:.1f} GB')

    d = np.fromfile(dir_path, dtype=np.float32)
    assert d.shape[0] == n_embd, f'dir dim {d.shape[0]} != {n_embd}'
    d = d / np.linalg.norm(d)
    print(f'direction {dir_path}: |d|=1')

    bias = (X @ d) * alpha
    print(f'bias: mean={bias.mean():+.4f} std={bias.std():.4f} max={bias.max():+.4f} min={bias.min():+.4f}')

    # top tokens (需要 tokenizer)
    try:
        toks = None
        for k, v in g.kv:
            if k == 'tokenizer.ggml.tokens':
                toks = v
                break
        if toks:
            idx = np.argsort(bias)[::-1][:12]
            print('--- top bias tokens ---')
            for i in idx:
                print(f'  {int(i):7d} {bias[i]:+.4f} {toks[i]!r}')
    except Exception as e:
        print(f'(token print skip: {e})')

    bias.astype(np.float32).tofile(out_path)
    print(f'bias written: {out_path} ({bias.shape[0]} x f32, alpha={alpha})')

if __name__ == '__main__':
    main()
