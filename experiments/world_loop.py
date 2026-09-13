#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world_loop.py — 最小可行「世界」闭环 (修正版)
================================================
关键修正:
  ① hist 始终记录【真实正确率】, 与模式无关 (公平对照)
  ② reward 按模式给 (真世界/随机/自反馈)
  ③ 世界复杂度匹配读出层 (确保"有世界能学会", 否则测不出世界有无用)

闭环: 世界给输入 → 核演化 → 读出层输出 → 世界判对错 → 用标量更新
核永不改动 (正交性 = 语义不受损)
"""
import numpy as np, time

t0 = time.time()
D, K = 64, 4
rng = np.random.RandomState(0)

# ── 世界: 有规则, 温和非线性 (读出层学得会)
Ww = rng.randn(D, D) / np.sqrt(D)
Vw = rng.randn(D, K) / np.sqrt(D)


def world_answer(x):
    h = np.tanh(x @ Ww)
    return int(np.argmax(h @ Vw))


# ── 系统: 正交核 + 相位
Q, _ = np.linalg.qr(rng.randn(D, D))
A = Q * 1.15
Qt = np.ascontiguousarray(A.T)
NPH = 8
PHW = np.array([1.0, 1.618, 2.414, 1.732, 2.236, 1.414, 2.646, 1.303])
ph0 = rng.rand(NPH) * 2 * np.pi


def make_brain():
    """每次运行独立相位 (避免跨模式污染)"""
    ph = ph0.copy()

    def brain(x):
        nonlocal ph
        x = x.copy()
        for _ in range(3):
            x = 0.5 * x + 0.5 * np.tanh(x @ Qt)
            d = ph[None, :] - ph[:, None]
            ph = ph + 0.05 * (PHW + 0.5 * np.sin(d).mean(1))
        return x
    return brain


def run(mode, steps=1500, lr=0.15):
    W = rng.randn(K, D) * 0.01
    brain = make_brain()
    base = 0.0
    hist = []
    for t in range(steps):
        x = rng.randn(D) * 0.5
        h = brain(x)
        z = W @ h
        p = np.exp(z - z.max()); p /= p.sum()
        pred = int(rng.choice(K, p=p))

        correct = (pred == world_answer(x))       # ★ 真实正确率 (所有模式都记)
        hist.append(1.0 if correct else 0.0)

        if mode == 'world':
            reward = 1.0 if correct else 0.0      # ★ 真世界反馈
        elif mode == 'random':
            reward = 1.0 if rng.rand() < 0.25 else 0.0   # 随机反馈
        else:  # self
            reward = 1.0                          # 自反馈 (恒1)

        base = 0.99 * base + 0.01 * reward
        g = np.zeros(K); g[pred] = 1.0
        W = W + lr * (reward - base) * np.outer(g - p, h)
        W = np.clip(W, -2, 2)
    return np.array(hist)


print('=' * 60)
print('最小可行「世界」闭环')
print('=' * 60)
print(f'  世界: 温和非线性 (读出层学得会)   K={K} 类')
print(f'  核对正交性偏差: {np.abs(A@A.T/1.15**2-np.eye(D)).mean():.2e}')
print()
print('  %-20s %-12s %-12s %s' % ('反馈来源', '前400步', '后700步', '判定'))
for mode, nm in [('world', '★真世界反馈'), ('random', '随机反馈'), ('self', '自反馈')]:
    h = run(mode)
    a, b = h[:400].mean(), h[-700:].mean()
    tag = ('✅ 学会了' if b > a + 0.05 else '❌ 没学')
    print('  %-20s %-12.4f %-12.4f %s' % (nm, a, b, tag))
print()
print(f'  随机基线 = {1/K:.4f}')
print(f'  核从未改动 (正交偏差不变)')
print(f'  用时 {time.time()-t0:.2f}s')
