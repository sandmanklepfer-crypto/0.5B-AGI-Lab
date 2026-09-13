#!/usr/bin/env python3
"""lm_head 有效秩 (复用 gguf_inspect.GGUF) — 支持 q4_k/q6_k/f32/f16
用法: lmhead_rank2.py <model.gguf>
"""
import sys, os, struct
import numpy as np
sys.path.insert(0, '/workspace/tools')
from gguf_inspect import GGUF, TYPES as T

QK = 256

def dequant(raw, typ, n_elem):
    if typ == 0: return np.frombuffer(raw, dtype=np.float32)[:n_elem]
    if typ == 1: return np.frombuffer(raw, dtype=np.float16)[:n_elem].astype(np.float32)
    nb = n_elem // QK
    a = np.frombuffer(raw, dtype=np.uint8).reshape(nb, -1)
    l = np.arange(32); is_ = l // 16
    if typ == 12:  # q4_k: 144B
        BS = 144
        a = a[:, :BS]
        d = np.array([struct.unpack('<e', a[i, 136:138].tobytes())[0] for i in range(nb)], dtype=np.float32)
        dm = np.array([struct.unpack('<e', a[i, 138:140].tobytes())[0] for i in range(nb)], dtype=np.float32)
        sc = a[:, 128:136].astype(np.int8).astype(np.float32)
        ql = a[:, 0:128]; qh = a[:, 128:136]
        out = np.zeros((nb, QK), dtype=np.float32)
        for half in range(2):
            ql0 = ql[:, half*64:(half+1)*64]; qh0 = qh[:, half*32:(half+1)*32]
            q1 = ((ql0[:, l] & 0xF) | ((qh0[:, l] >> 0 & 3) << 4)).astype(np.float32) - 8
            q2 = ((ql0[:, l+32] & 0xF) | ((qh0[:, l] >> 2 & 3) << 4)).astype(np.float32) - 8
            q3 = ((ql0[:, l] >> 4) | ((qh0[:, l] >> 4 & 3) << 4)).astype(np.float32) - 8
            q4 = ((ql0[:, l+32] >> 4) | ((qh0[:, l] >> 6 & 3) << 4)).astype(np.float32) - 8
            b = half * 128
            out[:, b+0:b+32] = d[:, None] * dm[:, None] * sc[:, is_] * q1
            out[:, b+32:b+64] = d[:, None] * dm[:, None] * sc[:, is_+2] * q2
            out[:, b+64:b+96] = d[:, None] * dm[:, None] * sc[:, is_+4] * q3
            out[:, b+96:b+128] = d[:, None] * dm[:, None] * sc[:, is_+6] * q4
        return out.reshape(-1)
    if typ == 8:  # q8_0: 33B/block(32元素)
        BS = 33
        nb = n_elem // 32
        a = np.frombuffer(raw, dtype=np.uint8).reshape(nb, BS)
        d = np.array([struct.unpack('<e', a[i, 0:2].tobytes())[0] for i in range(nb)], dtype=np.float32)
        q = a[:, 2:34].astype(np.int8).astype(np.float32)
        return (q * d[:, None]).reshape(-1)[:n_elem]
    if typ == 14:  # q6_k: 210B
        BS = 210
        a = a[:, :BS]
        ql = a[:, 0:128]; qh = a[:, 128:192]
        sc = a[:, 192:208].astype(np.int16); sc[sc > 127] -= 256
        d = np.array([struct.unpack('<e', a[i, 208:210].tobytes())[0] for i in range(nb)], dtype=np.float32)
        out = np.zeros((nb, QK), dtype=np.float32)
        for half in range(2):
            ql0 = ql[:, half*64:(half+1)*64]; qh0 = qh[:, half*32:(half+1)*32]
            q1 = ((ql0[:, l] & 0x0F) | ((qh0[:, l] >> 0 & 0x03) << 4)).astype(np.int16) - 32
            q2 = ((ql0[:, l+32] & 0x0F) | ((qh0[:, l] >> 2 & 0x03) << 4)).astype(np.int16) - 32
            q3 = ((ql0[:, l] >> 4) | ((qh0[:, l] >> 4 & 0x03) << 4)).astype(np.int16) - 32
            q4 = ((ql0[:, l+32] >> 4) | ((qh0[:, l] >> 6 & 0x03) << 4)).astype(np.int16) - 32
            b = half * 128
            out[:, b+0:b+32] = d[:, None] * sc[:, is_] * q1
            out[:, b+32:b+64] = d[:, None] * sc[:, is_+2] * q2
            out[:, b+64:b+96] = d[:, None] * sc[:, is_+4] * q3
            out[:, b+96:b+128] = d[:, None] * sc[:, is_+6] * q4
        return out.reshape(-1)
    raise SystemExit(f'unsupported type {typ} ({T.get(typ)})')

def main():
    path = sys.argv[1]
    g = GGUF(path)
    t = next((t for t in g.tensors if t['name'] in ('output.weight', 'token_embd.weight')), None)
    if t is None:
        print('output/token_embd not found'); return
    dims = t['dims']
    ne, nv = int(dims[0]), int(dims[1])
    n_elem = ne * nv
    typ = t['type_id']
    bytes_per = 210 if typ == 14 else 144 if typ == 12 else (4 if typ == 0 else 2)
    g.f.seek(g.abs_off(t))
    raw = g.f.read((n_elem // QK) * bytes_per if typ in (12, 14) else n_elem * bytes_per)
    X = dequant(raw, typ, n_elem).reshape(nv, ne)
    print(f'{path.split("/")[-1]}: output.weight {ne}x{nv} type={T.get(typ)} ({typ})')
    cov = X.T @ X
    s = np.sqrt(np.clip(np.linalg.eigvalsh(cov), 0, None))[::-1]
    e = s**2; total = e.sum()
    for pct in [50, 90, 99]:
        k = int(np.argmax(e.cumsum()/total > pct/100)) + 1
        print(f'  有效秩@{pct}% = {k}')
    print(f'  s1={s[0]:.1f} s100/s1={s[99]/s[0]:.3f}' + (f' s1000/s1={s[999]/s[0]:.3f}' if len(s) > 999 else ''))

if __name__ == '__main__':
    main()
