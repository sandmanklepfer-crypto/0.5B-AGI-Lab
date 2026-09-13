#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fork_svd.py — 分叉 + SVD 坐标系反馈
=====================================
用户洞察:
  分叉后不该用"二元对错", 应该:
    ① 以分叉的平均中心线为基准
    ② 拉出一套可无穷延伸的平面 (SVD 主方向)
    ③ 每时每刻建立 SVD 空间系
    ④ 在这个坐标系里判断 (而不是二元判别)

三种反馈:
  A 二元对错      r_k = 1 if 最好 else 0
  B SVD坐标       r_k = 分数 × 主方向坐标
  C 方向向量      r = Σ w_k·(h_k - c)  ← "中心线射线"
"""
import numpy as np, time

t0 = time.time()
D, K = 32, 4
rng = np.random.RandomState(0)
Vw = rng.randn(D, K) / np.sqrt(D)
N, NTRAIN = 1000, 700
X = rng.randn(N, D) * 0.5
SCR = X @ Vw
Y = SCR.argmax(1)


def train(mode, steps=1500, lr=0.1, sig=0.4):
    W = rng.randn(K, D) * 0.01
    base = 0.0
    for t in range(steps):
        i = rng.randint(NTRAIN)
        x = X[i]
        H = np.tanh(x[None, :] + rng.randn(K, D) * sig)   # (K,D) 分叉
        z = H @ W.T                                        # (K,K)
        z = z[np.arange(K), np.arange(K)]
        s = SCR[i]                                          # 世界打分
        p = np.exp(z - z.max()); p /= p.sum()

        if mode == 'binary':
            r = (s == s.max()).astype(float)
        elif mode == 'svdcoord':
            C = H - H.mean(0)
            _, _, Vt = np.linalg.svd(C, full_matrices=False)
            coord = C @ Vt[0]
            r = (s - s.mean()) / (s.std() + 1e-9)
            r = r * np.abs(coord) / (np.abs(coord).max() + 1e-9)
        else:  # direct
            c = H.mean(0)
            w = (s - s.mean()) / (s.std() + 1e-9)
            direct = (w[:, None] * (H - c)).mean(0)        # (D,) 中心线射线
            # 反馈: 各分支在射线上的投影 × 分数偏离
            r = w * (C_proj := (H - c) @ direct)
            r = r / (np.abs(r).max() + 1e-9)

        base = 0.99 * base + 0.01 * r.mean()
        d = r - base
        for k in range(K):
            g = np.zeros(K); g[k] = 1.0
            W = W + lr * d[k] * np.outer(g - p, H[k])
        W = np.clip(W, -3, 3)
    return ((X[NTRAIN:] @ W.T).argmax(1) == Y[NTRAIN:]).mean()


print('★ 分叉反馈方式对比 (D=%d K=%d)' % (D, K))
print('  随机基线: 0.2500')
res = {}
for mode, nm in [('binary', 'A 二元对错'), ('svdcoord', 'B SVD坐标'),
                 ('direct', '★C 方向向量(中心线射线)')]:
    a = train(mode)
    res[mode] = a
    print('  %-26s %.4f' % (nm, a))
print()
best = max(res, key=res.get)
print('  最优: %s (%.4f)' % (best, res[best]))
print('  vs 二元: %+.1f%%' % (100 * (res[best] - res['binary']) / max(res['binary'], 1e-9)))
print('  用时 %.2fs' % (time.time() - t0))
