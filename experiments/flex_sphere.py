#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flex_sphere.py — 柔性球面 (多图集 atls)
==========================================
用户洞察:
  单个球极投影是"刚性"的 → 远端全部挤到极点 → 无法分辨
  但若把球面变"柔性" → 换投影中心 → 原来的远端变近端
  → "一个点消失, 另一个点涌现"  (正是微分流形的 图集/atlas)

结构:
  多个投影中心 {c_1..c_k} (自适应选出, 覆盖不同尺度)
  每个点用【最近的中心】投影
  → 每个区域都有自己的高分辨率球面

对照:
  单球面 (原点为中心)  → 远端分离度 0.000008
  柔性球面 (k=4 中心)  → 远端分离度 0.049474  (提升 5959 倍)
"""
import numpy as np


def stereo(x, c):
    """以 c 为中心, 球极投影到单位球: 无穷远 → 北极"""
    y = x - c
    s = (y ** 2).sum(1, keepdims=True)
    return np.concatenate([2 * y / (s + 1), (s - 1) / (s + 1)], axis=1)


def geodesic_sep(S):
    """测地分离度 (角度, 保角投影的正确度量)"""
    Sn = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-12)
    d = np.arccos(np.clip(Sn @ Sn.T, -1, 1))
    return d[np.triu_indices(len(S), 1)]


def logpolar(x):
    """方向 + log 距离 (另一种柔性: 连续变焦)"""
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return np.concatenate([x / (n + 1e-12), np.log(n + 1e-12)], axis=1)


class FlexSphere:
    """柔性球面: 多图集自适应中心"""

    def __init__(self, ncard=4, mode='sphere'):
        self.n = ncard
        self.mode = mode          # 'sphere' | 'logpolar'
        self.C = None

    def fit(self, X):
        """k-means 选图集中心 (自动覆盖不同尺度/区域)"""
        X = np.asarray(X, float)
        r = np.random.RandomState(0)
        self.C = X[r.choice(len(X), min(self.n, len(X)), replace=False)].copy()
        for _ in range(20):
            lab = ((X[:, None] - self.C[None]) ** 2).sum(2).argmin(1)
            for k in range(len(self.C)):
                m = (lab == k)
                if m.sum() > 0:
                    self.C[k] = X[m].mean(0)
        return self

    def transform(self, X):
        X = np.asarray(X, float)
        if self.mode == 'logpolar':
            return logpolar(X)
        lab = ((X[:, None] - self.C[None]) ** 2).sum(2).argmin(1)
        out = np.empty((len(X), X.shape[1] + 1))
        for k in range(len(X)):
            out[k] = stereo(X[k:k+1], self.C[lab[k]])[0]
        return out

    def metric(self, X):
        S = self.transform(X)
        Sn = S / (np.linalg.norm(S, axis=1, keepdims=True) + 1e-12)
        return Sn @ Sn.T


if __name__ == '__main__':
    import time
    t0 = time.time()
    r = np.random.RandomState(0)
    # 三尺度数据
    X = np.vstack([r.randn(6, 4) * 0.5,
                   r.randn(6, 4) * 5 + np.array([100, 0, 0, 0]),
                   r.randn(6, 4) * 50 + np.array([0, 5000, 0, 0])])
    lab = np.array([0] * 6 + [1] * 6 + [2] * 6)

    print('=' * 62)
    print('柔性球面 vs 单球面 vs 对数极坐标 (三尺度数据)')
    print('=' * 62)
    print()
    print('  %-22s %-14s %-14s %s' % ('方案', '整体分离', '远端分离', '判定'))
    S0 = stereo(X, np.zeros(4))
    print('  %-22s %-14.4f %-14.6f %s' % ('单球面(原点)', geodesic_sep(S0).mean(),
          geodesic_sep(S0[lab == 2]).mean(), '基线'))
    fs = FlexSphere(4).fit(X); S1 = fs.transform(X)
    print('  %-22s %-14.4f %-14.6f %s' % ('★柔性球面(k=4)', geodesic_sep(S1).mean(),
          geodesic_sep(S1[lab == 2]).mean(), '★'))
    S2 = logpolar(X)
    print('  %-22s %-14.4f %-14.6f %s' % ('对数极坐标', geodesic_sep(S2).mean(),
          geodesic_sep(S2[lab == 2]).mean(), '★'))
    print()
    print('  远端(簇2)提升: 柔性 %.0f 倍, 对数极坐标 %.0f 倍'
          % (geodesic_sep(S1[lab == 2]).mean() / max(geodesic_sep(S0[lab == 2]).mean(), 1e-12),
             geodesic_sep(S2[lab == 2]).mean() / max(geodesic_sep(S0[lab == 2]).mean(), 1e-12)))
    print('  用时 %.2fs' % (time.time() - t0))
