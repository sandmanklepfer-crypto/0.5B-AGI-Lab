#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_cheaper.py — 验证是否比生成省参数? (P vs NP 的实践版)
==============================================================
核心问题: "全领域验证器" 能否用很少参数覆盖很大领域?

理论: P vs NP 的直觉是「验证比生成容易」
  · 生成: 给定 x, 找到正确的 y      (在 K^N 空间里搜索)
  · 验证: 给定 (x, y), 判断对不对   (只需算一下)

如果验证器普遍比生成器省很多参数, 那"小验证器 + 大生成器"就是
"用很少算力撬动大能力"的唯一合法形式 —— 这正是用户要的

测: 达到同样准确率 (>80%), 生成器需要多少参数, 验证器需要多少
"""
import numpy as np, time

t0 = time.time()
D = 24
rng = np.random.RandomState(0)


def train_cls(X, Y, K, H, iters=100, lr=0.15, seed=0):
    """训练一个 (X → K类) 的 MLP, 返回 (参数, 准确率)"""
    r = np.random.RandomState(seed)
    din = X.shape[1]
    W1 = r.randn(H, din)/np.sqrt(din); b1 = np.zeros((1, H))
    W2 = r.randn(K, H)/np.sqrt(H); b2 = np.zeros((1, K))
    Yh = np.eye(K)[Y]
    for it in range(iters):
        A1 = np.tanh(X @ W1.T + b1)                # (n,H)
        Yp = A1 @ W2.T + b2                        # (n,K)
        e = np.exp(Yp - Yp.max(1, keepdims=True)); P = e/e.sum(1, keepdims=True)
        dY = (P - Yh)/len(X)
        gW2 = dY.T @ A1; gb2 = dY.sum(0, keepdims=True)     # (K,H),(1,K)
        dZ = (dY @ W2) * (1 - A1**2)                        # (n,H)
        gW1 = dZ.T @ X; gb1 = dZ.sum(0, keepdims=True)      # (H,din),(1,H)
        W2 -= lr*gW2; b2 -= lr*gb2
        W1 -= lr*gW1; b1 -= lr*gb1
    npar = W1.size + b1.size + W2.size + b2.size
    return npar, (W1, b1, W2, b2)


def eval_cls(pack, X, Y, K):
    W1, b1, W2, b2 = pack
    A1 = np.tanh(X @ W1.T + b1)
    return ((A1 @ W2.T + b2).argmax(1) == Y).mean()


def min_H(Xtr, ytr, Xte, yte, K, thresh=0.8, seed=0):
    """找到最小的 H 使准确率 > thresh"""
    for H in [2, 4, 8, 16, 32, 64]:
        np_, pack = train_cls(Xtr, ytr, K, H, seed=seed)
        if eval_cls(pack, Xte, yte, K) > thresh:
            return H, np_
    return None, None


print('=' * 78)
print('验证 vs 生成: 同样准确率(>80%), 谁更省参数?')
print('=' * 78)
print()
print('  %-8s %-24s %-24s %s' % ('类别K', '生成器 (x→y)', '验证器 ((x,y)→对错)', '参数比'))

for K in [4, 16]:
    W = rng.randn(K, D)/np.sqrt(D)
    ntr, nte = 400, 200
    Xtr = rng.randn(ntr, D); ytr = (Xtr @ W.T).argmax(1)
    Xte = rng.randn(nte, D); yte = (Xte @ W.T).argmax(1)

    # ---------- 生成器 ----------
    Hg, pg = min_H(Xtr, ytr, Xte, yte, K)

    # ---------- 验证器: 输入 (x, onehot(y)), 输出 对/错 ----------
    Oh = np.eye(K)
    Xa = np.hstack([Xtr, Oh[ytr]])
    ybad = (ytr + rng.randint(1, K, ntr)) % K
    Xv = np.vstack([Xa, np.hstack([Xtr, Oh[ybad]])])
    lab = np.concatenate([np.ones(ntr), np.zeros(ntr)]).astype(int)

    Xta = np.hstack([Xte, Oh[yte]])
    yb2 = (yte + rng.randint(1, K, nte)) % K
    Xvt = np.vstack([Xta, np.hstack([Xte, Oh[yb2]])])
    lab2 = np.concatenate([np.ones(nte), np.zeros(nte)]).astype(int)

    Hv, pv = min_H(Xv, lab, Xvt, lab2, 2)

    r1 = '%d 参数' % pg if pg else '需更大'
    r2 = '%d 参数' % pv if pv else '需更大'
    ratio = '%.1fx' % (pg/pv) if (pg and pv) else '—'
    print('  %-8d %-24s %-24s %s' % (K, 'H=%s (%s)' % (Hg, r1),
                                     'H=%s (%s)' % (Hv, r2), ratio))

print()
print('=' * 78)
print('结论判据')
print('=' * 78)
print('  · 若验证器参数 << 生成器 → 验证确实更省 → "小验证器"可行')
print('  · 若两者接近 → 验证不比生成省 → 全领域验证器需要同等能力')
print()
print('  用时 %.1fs' % (time.time() - t0))
