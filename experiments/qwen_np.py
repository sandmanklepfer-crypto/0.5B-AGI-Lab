#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qwen_np.py — 纯numpy Qwen2 多层前向(从gguf按需加载)"""
import numpy as np, sys, time
sys.path.insert(0, '/workspace')
from say import read_meta
from gguf.quants import dequantize

GG = '/workspace/w.gguf'
D, H, KV, HD = 896, 14, 2, 64
THETA = 1000000.0
EPS = 1e-6
Q = {0:(1,4),1:(1,2),2:(32,18),3:(32,20),6:(32,22),7:(32,24),8:(32,34),9:(32,36),
     10:(256,84),11:(256,110),12:(256,144),13:(256,176),14:(256,210),15:(256,292)}
_M = None

def meta():
    global _M
    if _M is None:
        _M = read_meta(GG)
    return _M

def load(name, rows=None):
    K, tens, data0 = meta()
    t = [x for x in tens if x[0] == name][0]
    Dn = int(t[1][0]); N = int(t[1][1]) if len(t[1]) > 1 else 1
    ty = t[2]; r = min(rows, N) if rows else N
    be, bs = Q[ty]
    raw = np.fromfile(GG, dtype=np.uint8, count=Dn * r // be * bs, offset=data0 + t[3])
    v = dequantize(raw, ty).astype(np.float32)
    return v.reshape(r, Dn) if len(t[1]) > 1 else v

def rms(x, w):
    return (x / np.sqrt((x * x).mean(-1, keepdims=True) + EPS)) * w

class Model:
    def __init__(self, nlayer=4, vocab=12000):
        t0 = time.time()
        self.emb = load('token_embd.weight', vocab)
        self.onorm = load('output_norm.weight')
        self.ow = load('output.weight', vocab)
        self.V = self.emb.shape[0]
        self.L = []
        for l in range(nlayer):
            p = 'blk.%d.' % l
            self.L.append(dict(
                an=load(p+'attn_norm.weight'),
                q=load(p+'attn_q.weight'), qb=load(p+'attn_q.bias'),
                k=load(p+'attn_k.weight'), kb=load(p+'attn_k.bias'),
                v=load(p+'attn_v.weight'), vb=load(p+'attn_v.bias'),
                o=load(p+'attn_output.weight'),
                fn=load(p+'ffn_norm.weight'),
                g=load(p+'ffn_gate.weight'),
                u=load(p+'ffn_up.weight'),
                d=load(p+'ffn_down.weight')))
        self.nlayer = nlayer
        self.load_t = time.time() - t0

    def rope(self, x, pos):
        # Qwen2 用「分半」形式: rotate_half = cat(-x2, x1)
        T = x.shape[0]
        inv = 1.0 / (THETA ** (np.arange(0, HD, 2) / HD))   # (HD/2,)
        e = np.outer(pos, inv)                              # (T,HD/2)
        c = np.concatenate([np.cos(e), np.cos(e)], axis=-1)  # (T,HD)
        s = np.concatenate([np.sin(e), np.sin(e)], axis=-1)
        h = HD // 2
        x1, x2 = x[..., :h], x[..., h:]
        rot = np.concatenate([-x2, x1], axis=-1)
        return x * c[:, None, :] + rot * s[:, None, :]

    def forward(self, ids, cache=None):
        T = len(ids)
        x = self.emb[ids].astype(np.float32)
        pos = np.arange(T)
        for l in range(self.nlayer):
            L = self.L[l]
            h = rms(x, L['an'])
            q = (h @ L['q'].T + L['qb']).reshape(T, H, HD)
            k = (h @ L['k'].T + L['kb']).reshape(T, KV, HD)
            v = (h @ L['v'].T + L['vb']).reshape(T, KV, HD)
            q = self.rope(q, pos); k = self.rope(k, pos)
            rep = H // KV
            kk = np.repeat(k, rep, axis=1); vv = np.repeat(v, rep, axis=1)
            at = np.einsum('thd,shd->hts', q, kk) / np.sqrt(HD)
            at = at - at.max(-1, keepdims=True)
            aw = np.exp(at); aw /= aw.sum(-1, keepdims=True)
            o = np.einsum('hts,shd->thd', aw, vv).reshape(T, D)
            x = x + o @ L['o'].T
            h2 = rms(x, L['fn'])
            g = h2 @ L['g'].T
            g = g / (1 + np.exp(-g))
            u = h2 @ L['u'].T
            x = x + (g * u) @ L['d'].T
        h = rms(x, self.onorm)
        return h @ self.ow.T

if __name__ == '__main__':
    t0 = time.time()
    m = Model(4, 12000)
    print('加载4层+词表%d: %.2fs' % (m.V, m.load_t))
    ids = np.array([262, 3667, 286, 5498, 374])   # 待查真实token
    t1 = time.time(); lg = m.forward(ids); tf = time.time()-t1
    print('前向 T=%d: %.3fs  logits%s' % (len(ids), tf, lg.shape))
    top = np.argsort(lg[-1])[::-1][:8]
    print('next top8 ids: %s' % top.tolist())
    print('总计 %.2fs' % (time.time()-t0))
