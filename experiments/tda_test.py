#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tda_test.py — 持续同调能否降维?
==================================
用户想法: 用持续同调找"洞/关键点", 直接做降维

诚实的区分 (先说清):
  降维        → 输出【低维坐标】 (每点一个向量)
  持续同调    → 输出【拓扑不变量】 (条形码/贝蒂数, 不是坐标)
  两者不是同一件事 —— 本实验测这个

方法: Rips 过滤 + 图论贝蒂数
  β0(t) = 连通分量数       (并查集)
  β1(t) = E - V + β0       (独立环数, 图论精确公式)
  β1 的持久性 = "有几个洞, 多久不消失"

对比三种表示:
  A 原始高维 (896维 / 64维)
  B PCA 降到低维
  C 拓扑特征 (β1 曲线)

关键判据: 拓扑特征能否区分"有洞"和"无洞"的结构?
"""
import numpy as np, time
from scipy.spatial.distance import pdist, squareform

t0 = time.time()
rng = np.random.RandomState(0)


def betti_curve(D, n_t=40):
    """输入距离矩阵, 返回 (阈值列表, β0列表, β1列表)"""
    n = D.shape[0]
    iu = np.triu_indices(n, 1)
    edges = D[iu]
    tvals = np.percentile(edges, np.linspace(5, 95, n_t))
    b0s, b1s = [], []
    for t in tvals:
        # 并查集数连通分量
        par = list(range(n))

        def find(x):
            while par[x] != x:
                par[x] = par[par[x]]; x = par[x]
            return x

        E = 0
        for (i, j), d in zip(zip(*iu), edges):
            if d <= t:
                E += 1
                ri, rj = find(i), find(j)
                if ri != rj: par[ri] = rj
        V = n
        b0 = len({find(i) for i in range(n)})
        b1 = E - V + b0                     # ★ 图论精确公式
        b0s.append(b0); b1s.append(b1)
    return tvals, np.array(b0s), np.array(b1s)


def topology_signature(X):
    """拓扑特征: β1 曲线的峰值 + 峰值位置"""
    D = squareform(pdist(X))
    tv, b0, b1 = betti_curve(D)
    peak = int(b1.max())
    # 峰值处的"相对阈值" (峰值位置 / 中位距离)
    if b1.max() > 0:
        pos = float(tv[int(np.argmax(b1))] / (np.median(D[D > 0]) + 1e-9))
    else:
        pos = 0.0
    return peak, pos


# ==================== 造数据: 有洞 vs 无洞 ====================
N, DIM = 60, 64
U = rng.randn(2, DIM); U /= np.linalg.norm(U, axis=1, keepdims=True)   # 2维子空间

# A: 环 (1个洞)
th = rng.uniform(0, 2*np.pi, N)
RING_2d = np.stack([np.cos(th), np.sin(th)], 1)
X_ring = RING_2d @ U + rng.randn(N, DIM) * 0.08

# B: 圆盘 (无洞)
r = np.sqrt(rng.uniform(0, 1, N))
th2 = rng.uniform(0, 2*np.pi, N)
DISC_2d = np.stack([r*np.cos(th2), r*np.sin(th2)], 1)
X_disc = DISC_2d @ U + rng.randn(N, DIM) * 0.08

print('=' * 70)
print('持续同调 vs PCA: 能否识别「洞」')
print('=' * 70)
print()

# ==================== 三种表示下的拓扑签名 ====================
configs = [
    ('原始高维 (64维)', X_ring, X_disc),
    ('真子空间 (2维)', RING_2d, DISC_2d),
]

# PCA 降到 2 维
for name, Xr, Xd in list(configs):
    pass

mu = np.vstack([X_ring, X_disc]).mean(0)
_, _, Vt = np.linalg.svd(np.vstack([X_ring, X_disc]) - mu, full_matrices=False)
P = Vt[:2]
configs.append(('PCA降到2维', (X_ring - mu) @ P.T, (X_disc - mu) @ P.T))

print('  %-20s %-22s %-22s %s' % ('表示', '环 β1峰值/相对尺度', '圆盘 β1峰值/相对尺度', '能否区分'))
for name, Xr, Xd in configs:
    pr, posr = topology_signature(Xr)
    pd, posd = topology_signature(Xd)
    diff = (pr != pd) or (abs(posr - posd) > 0.3)
    print('  %-20s %-22s %-22s %s' % (
        name, 'β1=%d  位置=%.2f' % (pr, posr),
        'β1=%d  位置=%.2f' % (pd, posd),
        '✅ 能' if diff else '❌ 不能'))

print()
print('  ★ 判据: "环"应有 β1≥1; "圆盘"应 β1=0')
print('  ★ 若高维列显示两者都不可分 → 维度诅咒让拓扑失效')
print()
print('  用时 %.2fs' % (time.time() - t0))
