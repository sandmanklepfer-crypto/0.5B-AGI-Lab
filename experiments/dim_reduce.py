#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dim_reduce.py — 专门做「高维 → 低维自洽结构」的网络
======================================================
用户洞察:
  低维工具很完备, 但高维的东西很抠 (D2=14.8 vs 4.5)
  需要一个【天生擅长把高维线性分解到低维】的网络
  而不是在高维空间硬算

今天的标度律: 同样锚点数, 低维插值效率高 11 倍
→ 所以降维是性价比最高的杠杆

本实验对比四种降维:
  A 原始高维 (基线)
  B 真内在维度 (上界)
  C PCA 线性降维
  ★D 自编码器/非线性降维 (天生做这个的网络)
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

D, N, TRUE_D = 64, 1500, 5
print('=' * 66)
print('高维→低维: 四种方法在「下游任务」上的表现')
print('=' * 66)

# ==================== 数据: 64维, 但内在只有 5 维 ====================
U = rng.randn(TRUE_D, D) / np.sqrt(D)          # 真子空间
Ztrue = rng.randn(N, TRUE_D) * 1.5
X = Ztrue @ U + rng.randn(N, D) * 0.08         # 高维观测

# 下游任务: 一个非线性函数 (需要真理解结构)
y = np.array([np.sin(z[0]) * np.cos(z[1]) + 0.5 * z[2] - 0.3 * z[3] * z[4] for z in Ztrue])


def downstream(Ztr, Ytr, Zte, Yte):
    """在表示Z上做核回归, 返回相对误差"""
    d2 = ((Ztr[:, None, :] - Ztr[None, :, :]) ** 2).sum(-1)
    sig2 = max(np.median(d2), 1e-9)
    a = np.linalg.solve(np.exp(-d2 / sig2) + 1e-2 * np.eye(len(Ztr)), Ytr)
    d2t = ((Zte[:, None, :] - Ztr[None, :, :]) ** 2).sum(-1)
    pr = np.exp(-d2t / sig2) @ a
    return float(np.mean(np.abs(pr - Yte)) / np.std(Yte))


# ==================== D: 自编码器 (纯 numpy, 简单版) ====================
def train_ae(X, k=5, iters=300, lr=0.02):
    """三层 AE: X -> tanh(W1 X) -> W2 h, 线性解码, 反向传播"""
    n, d = X.shape
    W1 = rng.randn(k, d) / np.sqrt(d)
    W2 = rng.randn(d, k) / np.sqrt(k)
    b1 = np.zeros((k, 1)); b2 = np.zeros((d, 1))
    Xt = X.T                                   # (d,n)
    for it in range(iters):
        H = np.tanh(W1 @ Xt + b1)              # (k,n)
        Xr = W2 @ H + b2                       # (d,n)
        dX = 2 * (Xr - Xt) / n
        gW2 = dX @ H.T; gb2 = dX.sum(1, keepdims=True)
        dH = (W2.T @ dX) * (1 - H ** 2)
        gW1 = dH @ Xt.T; gb1 = dH.sum(1, keepdims=True)
        W2 -= lr * gW2; b2 -= lr * gb2
        W1 -= lr * gW1; b1 -= lr * gb1
    return W1, b1


def encode(X, W1, b1):
    """X: (n,d) → 返回 (k,n)"""
    return np.tanh(W1 @ X.T + b1)


# ==================== 评估 ====================
n_tr = 120
idx = rng.permutation(N)
itr, ite = idx[:n_tr], idx[n_tr:n_tr + 300]
Ytr, Yte = y[itr], y[ite]

print()
print('  %-26s %-12s %-14s %s' % ('方法', '表示维度', '下游误差', '说明'))
print('  %-26s %-12d %-14.3f %s' % ('A 原始高维', D,
      downstream(X[itr], Ytr, X[ite], Yte), '基线 (D2高, 工具抠)'))
print('  %-26s %-12d %-14.3f %s' % ('B 真内在维度(上界)', TRUE_D,
      downstream(Ztrue[itr], Ytr, Ztrue[ite], Yte), '理想上界'))

# PCA
mu = X[itr].mean(0)
Xc = X[itr] - mu
Uu, S, Vt = np.linalg.svd(Xc, full_matrices=False)
for k in [5, 10]:
    P = Vt[:k]
    print('  %-26s %-12d %-14.3f %s' % ('C PCA (线性, k=%d)' % k, k,
          downstream((X[itr] - mu) @ P.T, Ytr, (X[ite] - mu) @ P.T, Yte), ''))

# AE (非线性)
for k in [5, 10]:
    W1, b1 = train_ae(X[itr], k, iters=400, lr=0.03)
    Ztr = encode(X[itr], W1, b1).T
    Zte = encode(X[ite], W1, b1).T
    print('  %-26s %-12d %-14.3f %s' % ('★D 自编码器 (k=%d)' % k, k,
          downstream(Ztr, Ytr, Zte, Yte), '★ 非线性降维'))

print()
print('  误差 1.0 = 只猜均值')
print('  用时 %.2fs' % (time.time() - t0))
