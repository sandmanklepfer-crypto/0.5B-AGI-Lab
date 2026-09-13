#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tda_test2.py — 持续同调 (修正: 测"洞持续多久", 而非"洞有多少")
================================================================
上一版错在取 β1 峰值: 稠密图里 β1=E-V+β0 会无限增长
正确做法 (持续同调的核心思想):
  看 β1 从 1 变到 2 需要的尺度跨度
  → 跨度大 = 洞"持久" (真实拓扑特征)
  → 跨度小 = 噪声 (假洞)

persistence = log(t_{β1=2} / t_{β1=1})
"""
import numpy as np, time
from scipy.spatial.distance import pdist, squareform

t0 = time.time()
rng = np.random.RandomState(0)


def betti_profile(D, n_t=60):
    """返回 (尺度数组, β1 数组), 尺度用相对值 (除以中位距离)"""
    n = D.shape[0]
    iu = np.triu_indices(n, 1)
    ev = D[iu]
    med = np.median(ev) + 1e-12
    # 在 [0.2, 3.0] 倍中位距离上细扫
    tvals = np.linspace(0.2 * med, 3.0 * med, n_t)
    b1s = []
    A = (D <= 0)
    for t in tvals:
        par = np.arange(n)

        def find(x):
            r = x
            while par[r] != r: r = par[r]
            while par[x] != r: par[x], x = r, par[x]
            return r

        E = 0
        mask = (D <= t) & (D > 0)
        idx = np.argwhere(np.triu(mask))
        for i, j in idx:
            E += 1
            ri, rj = find(i), find(j)
            if ri != rj: par[ri] = rj
        C = len({find(i) for i in range(n)})
        b1s.append(E - n + C)
    return tvals / med, np.array(b1s)


def persistence_1(D):
    """H1 持久性: β1 从 1 到 2 的尺度跨度"""
    tv, b1 = betti_profile(D)
    t1 = None; t2 = None
    for i in range(len(b1)):
        if t1 is None and b1[i] >= 1: t1 = tv[i]
        if t2 is None and b1[i] >= 2: t2 = tv[i]
    if t1 is None or t2 is None or t2 <= t1: return 0.0, t1 or 0, t2 or 0
    return float(np.log(t2 / t1)), t1, t2


N, DIM = 60, 64
U = rng.randn(2, DIM); U /= np.linalg.norm(U, axis=1, keepdims=True)
th = rng.uniform(0, 2*np.pi, N)
RING2 = np.stack([np.cos(th), np.sin(th)], 1)
X_ring = RING2 @ U + rng.randn(N, DIM)*0.08

r = np.sqrt(rng.uniform(0, 1, N)); th2 = rng.uniform(0, 2*np.pi, N)
DISC2 = np.stack([r*np.cos(th2), r*np.sin(th2)], 1)
X_disc = DISC2 @ U + rng.randn(N, DIM)*0.08

# PCA 降到 2 维
allX = np.vstack([X_ring, X_disc]); mu = allX.mean(0)
_, _, Vt = np.linalg.svd(allX - mu, full_matrices=False)
P = Vt[:2]
R_pca = (X_ring - mu) @ P.T
D_pca = (X_disc - mu) @ P.T

print('=' * 74)
print('持续同调 (修正版): 测「洞持续多久」')
print('=' * 74)
print()
print('  %-20s %-14s %-14s %s' % ('表示', '环 持久性', '圆盘 持久性', '能否区分'))
print('  ' + '-' * 68)
for nm, Xr, Xd in [('原始高维 (64维)', X_ring, X_disc),
                   ('真子空间 (2维)', RING2, DISC2),
                   ('PCA降到2维', R_pca, D_pca)]:
    Dr = squareform(pdist(Xr)); Dd = squareform(pdist(Xd))
    pr, t1r, t2r = persistence_1(Dr)
    pd, t1d, t2d = persistence_1(Dd)
    print('  %-20s %-14.3f %-14.3f %s' % (nm, pr, pd, '✅ 能' if pr > pd*1.5 else '❌ 不能'))
    print('  %-20s (β1=1@%.2f, β1=2@%.2f)   (β1=1@%.2f, β1=2@%.2f)' % ('', t1r, t2r, t1d, t2d))

print()
print('  持久性 = log(t_β1=2 / t_β1=1)  → 越大 = 洞越"真实"')
print('  用时 %.2fs' % (time.time() - t0))
