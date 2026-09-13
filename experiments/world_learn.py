#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world_learn.py — 世界标量反馈 + 核的切空间写活
================================================
核心难点: 只有"对/错"1比特时, 核该往哪写?
解法: 切空间反对称更新 (保正交)
      A ← A·(I + δ·sign·(v uᵀ − u vᵀ))
      v = 输入方向, u = 输出方向
      对 → 加强这个映射; 错 → 减弱
数学保证: 反对称 ⇒ 一阶保正交 ⇒ 语义不受损

三组对照:
  A 核冻结      只学读出层 (基线)
  B 核切空间写活  今天验证过的方式 (损失仅6%)
  C 核普通写活   对照组 (应该崩)

世界: 非线性 (二次型), 让核的动力学有价值
"""
import numpy as np, time

t0 = time.time()
D, K = 64, 4
rng = np.random.RandomState(0)

# ── 世界: 非线性 (需要动力学才能表达)
Ww = rng.randn(D, D) / np.sqrt(D)
Vw = rng.randn(D, K) / np.sqrt(D)


def ans(x):
    return int(np.argmax(np.tanh(x @ Ww) @ Vw))


Q, _ = np.linalg.qr(rng.randn(D, D))
A0 = Q * 1.15
I = np.eye(D)


def run(mode, steps=1500, lr=0.08, delta=0.03):
    A = A0.copy()
    W = rng.randn(K, D) * 0.01
    base, hist = 0.0, []
    for t in range(steps):
        x = rng.randn(D) * 0.5
        h = 0.5 * x + 0.5 * np.tanh(A @ x)
        z = W @ h
        p = np.exp(z - z.max()); p /= p.sum()
        pred = int(rng.choice(K, p=p))

        correct = (pred == ans(x))
        hist.append(1.0 if correct else 0.0)

        # ── 世界只说对错 (1 bit)
        r = 1.0 if correct else 0.0
        base = 0.99 * base + 0.01 * r
        sig = r - base

        # ── 读出层 (标量更新)
        g = np.zeros(K); g[pred] = 1.0
        W = W + lr * sig * np.outer(g - p, h)
        W = np.clip(W, -3, 3)

        # ── 核
        if mode == 'tape':
            v = x / (np.linalg.norm(x) + 1e-9)
            u = A @ x
            u = u / (np.linalg.norm(u) + 1e-9)
            S = delta * sig * (np.outer(v, u) - np.outer(u, v))
            A = A @ (I + S)
            if t % 200 == 199:                      # 定期重正交
                Qq, _ = np.linalg.qr(A); A = Qq * 1.15
        elif mode == 'naive':
            A = A + delta * sig * np.outer(x, A @ x)
            A = A / np.linalg.norm(A) * np.sqrt(D)

    return np.array(hist), A


def orth(A):
    An = A / np.linalg.norm(A) * np.sqrt(D)
    return float(np.abs(An @ An.T - I).mean())


print('=' * 62)
print('世界标量反馈 + 核写活  (D=%d, K=%d)' % (D, K))
print('=' * 62)
print('  %-18s %-10s %-10s %-10s %s' % ('核处理', '前400步', '后700步', '提升', '正交偏差'))
for mode, nm in [('freeze', 'A 核冻结'), ('tape', '★B 切空间写活'), ('naive', 'C 普通写活')]:
    h, A = run(mode)
    a, b = h[:400].mean(), h[-700:].mean()
    print('  %-18s %-10.4f %-10.4f %+-10.4f %.3f' % (nm, a, b, b - a, orth(A)))

print()
print('  随机基线 = %.4f' % (1 / K))
print('  判据: 提升越大越好; 正交偏差 ~0 = 语义未损')
print('  用时 %.2fs' % (time.time() - t0))
