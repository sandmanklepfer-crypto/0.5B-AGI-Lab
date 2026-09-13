#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
insight_test.py — "灵光一闪"能来自低维结构吗?
================================================
用户问: 低维架构能否用很少算力, 指导高维模型产生强大效果?

关键区分 (本实验测的就是这个):
  低维信号分两类:
    ① 模型自己状态的投影   → 没有新信息 (模型本来就知道) → 无效
    ② 外部世界给的关键量    → 有新信息 → 有效

"灵光一闪" = 用极少信息撬动大变化
  ✅ 它存在 (现实中的 prompt / 思维链 / 提示词)
  ❓ 但它的来源是"新信息", 还是"低维结构"?

设计: 高维任务 (D=64), 加 4 维"提示"
  A 提示 = 输入的随机投影  (自己状态的投影, 无新信息)
  B 提示 = 外部关键 bit    (模型看不到的真信息)
  C 提示 = 随机            (对照)
  D 无提示                (基线)

判据: 只有 B 有提升 → "灵光"来自新信息, 不来自低维
      若 A 也有提升 → 低维结构本身就有魔力
"""
import numpy as np, time

t0 = time.time()
D, DH, NTRAIN, NTEST = 64, 32, 2000, 500
rng = np.random.RandomState(0)

# ==================== 高维任务 ====================
# 目标: y = 三分类, 但【关键区分信息】在 x 的一个隐藏子空间里
Wt = rng.randn(6, D) / np.sqrt(D)          # 6 个投影
X = rng.randn(NTRAIN + NTEST, D)
proj = X @ Wt.T                             # (N, 6)
# 类别由 【第 5,6 个投影】决定 (前 4 个是干扰) — 严格 3 类
y = np.stack([proj[:, 4], proj[:, 5], -proj[:, 4] - proj[:, 5]], 1).argmax(1)

Xtr, Xte = X[:NTRAIN], X[NTRAIN:]
ytr, yte = y[:NTRAIN], y[NTRAIN:]
proj_tr, proj_te = proj[:NTRAIN], proj[NTRAIN:]


def make_hint(kind, proj, n):
    """4 维提示"""
    if kind == 'none':
        return np.zeros((n, 4))
    if kind == 'self':      # A: 自己状态的投影 (前4个投影, 都是干扰)
        return proj[:, :4] * 0.3
    if kind == 'world':     # B: 外部关键信息 (第5,6个投影 + 它们的差)
        return np.stack([proj[:, 4], proj[:, 5],
                         proj[:, 4] - proj[:, 5], proj[:, 4] + proj[:, 5]], 1) * 0.3
    if kind == 'rand':      # C: 随机
        return np.random.RandomState(7).randn(n, 4) * 0.3


def train_eval(kind, iters=350, lr=0.08, seed=1):
    r = np.random.RandomState(seed)
    Hh = 24
    W1 = r.randn(Hh, D+4)/np.sqrt(D+4); b1 = np.zeros((Hh, 1))
    W2 = r.randn(3, Hh)/np.sqrt(Hh); b2 = np.zeros((3, 1))
    Wr = r.randn(D+4, D+4)                     # 输入白化 (稳定训练)
    P = [W1, b1, W2, b2]
    M = [np.zeros_like(p) for p in P]; V = [np.zeros_like(p) for p in P]

    Htr = make_hint(kind, proj_tr, NTRAIN)
    Hte = make_hint(kind, proj_te, NTEST)
    Xtr2 = np.hstack([Xtr, Htr]).T             # (D+4, N)
    Xte2 = np.hstack([Xte, Hte]).T
    Ytr = np.zeros((NTRAIN, 3)); Ytr[np.arange(NTRAIN), ytr] = 1

    for it in range(iters):
        Z1 = W1 @ Xtr2 + b1
        A1 = np.tanh(Z1)
        Yp = W2 @ A1 + b2
        e = np.exp(Yp - Yp.max(0, keepdims=True)); Pp = e/e.sum(0, keepdims=True)
        dY = (Pp - Ytr.T)/NTRAIN
        gW2 = dY @ A1.T; gb2 = dY.sum(1, keepdims=True)
        dZ = (W2.T @ dY)*(1 - A1**2)
        gW1 = dZ @ Xtr2.T; gb1 = dZ.sum(1, keepdims=True)
        for i, g in enumerate([gW1, gb1, gW2, gb2]):
            M[i] = 0.9*M[i] + 0.1*g; V[i] = 0.999*V[i] + 0.001*g**2
            P[i] -= lr*(M[i]/(1-0.9**(it+1)))/(np.sqrt(V[i]/(1-0.999**(it+1)))+1e-8)

    Z1 = W1 @ Xte2 + b1; A1 = np.tanh(Z1); Yp = W2 @ A1 + b2
    return float((Yp.argmax(0) == yte).mean())


print('=' * 74)
print('灵光一闪测试: 4维提示能否撬动 64维任务?')
print('=' * 74)
print('  任务: 3 分类, 关键信息藏在 x 的第 5,6 个隐藏投影里')
print('  提示: 只有 4 维 (信息量 = 任务的 1/16)')
print()
print('  %-28s %-12s %s' % ('提示类型', '测试准确率', '说明'))
print('  ' + '-' * 68)
res = {}
for kind, nm in [('none', 'D 无提示 (基线)'),
                 ('self', 'A 自己状态的投影 (前4个投影)'),
                 ('world', '★B 外部关键信息 (第5,6个投影)'),
                 ('rand', 'C 随机 4 维')]:
    a = np.mean([train_eval(kind, seed=s) for s in [0]])
    res[kind] = a
    print('  %-28s %-12.3f %s' % (nm, a, ''))

print()
print('=' * 74)
print('提升幅度 (相对无提示)')
print('=' * 74)
for kind, nm in [('self', 'A 自己投影'), ('world', '★B 外部信息'), ('rand', 'C 随机')]:
    d = res[kind] - res['none']
    print('  %-14s %+.3f  %s' % (nm, d,
          '✅ 有效' if d > 0.05 else ('⚠️ 微弱' if d > 0.01 else '❌ 无效')))

print()
print('  随机猜测 = 0.333')
print('  用时 %.1fs' % (time.time() - t0))
