#!/usr/bin/env python3
"""build_unlock_3b.py — 3B 固化无限制版
output.bias = -10 × (output.weight @ d_reject_3b)   (同 0.5B qwen_unlocked 配方)
output.weight 是 q6_K (2048, 151936), 反量化公式照抄 ggml-quants.c
产出: /workspace/qwen3b_unlocked.gguf
"""
import sys, struct, os
import numpy as np
sys.path.insert(0, '/workspace/tools')
from gguf_inspect import GGUF

MODEL  = '/workspace/qwen2.5-coder-3b-instruct-q4_k_m.gguf'
DIR    = '/workspace/align2/d_reject_3b.bin'
OUT    = '/workspace/qwen3b_unlocked.gguf'
STRENGTH = 10.0
QK = 256
BLOCK = 210   # block_q6_K 字节数

def dequant_q6k_block(raw: bytes, dvec: np.ndarray) -> float:
    """一块 256 值 × dvec(256) 的点积 (照 ggml dequantize_row_q6_K)"""
    ql = np.frombuffer(raw[:128], np.uint8)
    qh = np.frombuffer(raw[128:192], np.uint8)
    sc = np.frombuffer(raw[192:208], np.int8)
    d  = np.frombuffer(raw[208:210], np.float16)[0].astype(np.float32)
    acc = 0.0
    # 两个 128 半
    for half in range(2):
        ql_h = ql[half*64:(half+1)*64]
        qh_h = qh[half*32:(half+1)*32]
        sc_h = sc[half*8:(half+1)*8]
        base = half * 128
        for l in range(32):
            is_ = l // 16
            q1 = ((ql_h[l+0] & 0xF) | (((qh_h[l] >> 0) & 3) << 4)) - 32
            q2 = ((ql_h[l+32] & 0xF) | (((qh_h[l] >> 2) & 3) << 4)) - 32
            q3 = ((ql_h[l+0] >> 4) | (((qh_h[l] >> 4) & 3) << 4)) - 32
            q4 = ((ql_h[l+32] >> 4) | (((qh_h[l] >> 6) & 3) << 4)) - 32
            acc += d * sc_h[is_+0] * q1 * dvec[base + l]
            acc += d * sc_h[is_+2] * q2 * dvec[base + l + 32]
            acc += d * sc_h[is_+4] * q3 * dvec[base + l + 64]
            acc += d * sc_h[is_+6] * q4 * dvec[base + l + 96]
    return acc

def main():
    d = np.fromfile(DIR, np.float32)
    assert d.shape[0] == 2048, f'dim {d.shape[0]} != 2048'
    d = d / (np.linalg.norm(d) + 1e-9)

    g = GGUF(MODEL)
    t = [t for t in g.tensors if t['name'] == 'output.weight'][0]
    dims = t['dims']   # (2048, 151936)
    n_rows, n_cols = dims
    assert t['type'] == 'q6_k', f'type {t["type"]}'
    n_blk = n_rows // QK   # 8 块/列

    g.f.seek(g.abs_off(t))
    total_bytes = n_cols * n_blk * BLOCK
    raw = g.f.read(total_bytes)
    print(f'[load] output.weight {dims} q6_k, {total_bytes/1e6:.0f}MB')

    # 逐列: 8 块反量化点积 (151936 列)
    res = np.zeros(n_cols, np.float32)
    col_bytes = n_blk * BLOCK
    for col in range(n_cols):
        base = col * col_bytes
        s = 0.0
        for b in range(n_blk):
            s += dequant_q6k_block(raw[base + b*BLOCK : base + (b+1)*BLOCK],
                                   d[b*QK:(b+1)*QK])
        res[col] = s
        if col % 20000 == 0:
            print(f'  [{col}/{n_cols}]', flush=True)

    # bias = -STRENGTH × W·d
    bias = -STRENGTH * res
    print(f'[bias] W·d: mean={res.mean():.4f} std={res.std():.4f} '
          f'max={res.max():.3f} min={res.min():.3f}')

    # top/bottom tokens
    toks = dict(g.kv)['tokenizer.ggml.tokens']
    idx = np.argsort(res)[::-1]
    print('[被推开 top5] (拒绝方向推高的词):')
    for i in idx[:5]:
        print(f'   {res[i]:+.3f}  {toks[i]!r}')
    print('[被压低 bottom5] (拒绝方向压低的词):')
    for i in idx[-5:]:
        print(f'   {res[i]:+.3f}  {toks[i]!r}')

    # 写 bias 数据 + extend_gguf
    bias.astype(np.float32).tofile('/tmp/bias3b.bin')
    import subprocess
    r = subprocess.run(['python3', '/workspace/tools/extend_gguf.py',
                        MODEL, OUT, 'output.bias', '/tmp/bias3b.bin', 'f32'],
                       capture_output=True, text=True)
    print('[extend_gguf]', r.stdout.strip()[-200:] if r.stdout else r.stderr[-200:])
    print(f'[done] {OUT}')

if __name__ == '__main__':
    main()
