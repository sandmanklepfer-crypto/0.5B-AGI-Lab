#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
worth.py — 定量算账: 「丢精度 + 崩得早」换「速度暴涨」, 值不值?
================================================================
判据: 净收益 = 连续方案成本 / 符号+锚点方案成本
      >1   值得   |   >100  非常值得   |   <1  不值得

★ 关键洞察: 崩的不是"总长 L", 是"两次锚点之间的步数 L0"
   无锚点 : 精度 ~ (1-p)^L   → L 一大必崩
   有锚点 : 精度 ~ (1-p)^L0  → 与总长 L 无关!  L→∞ 也不崩
"""
import numpy as np, time

t0 = time.time()
Vn = np.load('/workspace/_cache_V.npy')
Qt = np.load('/workspace/_cache_Qt.npy')
n, D = Vn.shape


def u(X):
    return X / (np.linalg.norm(X, axis=-1, keepdims=True) + 1e-12)


Cb = u(Vn); K = len(Cb)


def step(V):
    return 0.5 * np.tanh(V @ Qt) + 0.5 * V


# ---------- ① 实测成本 ----------
N = 300
t = time.perf_counter()
for _ in range(N):
    step(Cb)
t_cont = (time.perf_counter() - t) / N / K
t = time.perf_counter()
for _ in range(N):
    (u(Cb) @ Cb.T).argmax(1)
t_iden = (time.perf_counter() - t) / N / K
c = t_iden / t_cont
c_flop = (K * D) / float(D * D)

print("=" * 92)
print("定量算账: 「丢一点精度 + 超长就崩」换「速度暴涨」, 到底值不值?")
print("=" * 92)
print()
print("① 真实成本 (实测 + FLOP 理论)")
print("   连续一步        %8.2f us/词    FLOP %d" % (1e6 * t_cont, D * D))
print("   验证一次(=识别)  %8.2f us/词    FLOP %d" % (1e6 * t_iden, K * D))
print("   符号查表         %8.3f us/词    ~0 (O(1) 索引)" % 0)
print("   ★ c = 验证成本 / 连续步成本 = %.4f (实测)  |  %.4f (FLOP 理论)" % (c, c_flop))
print()

# ---------- ② 实测单步误差率 p ----------
tab = (u(step(Cb)) @ Cb.T).argmax(1)
V = Cb.copy(); TR = [V.copy()]
for _ in range(200):
    V = step(V); TR.append(V.copy())
TR = np.array(TR); SR = np.empty_like(TR)
for i in range(K):
    s = i; ss = [s]
    for _ in range(200):
        s = tab[s]; ss.append(s)
    SR[:, i] = Cb[np.array(ss)]
fid = (u(TR) * u(SR)).sum(-1).mean(1)
p_obs = 1 - fid[1]
print("② 单步误差率 p = %.4f   (无锚点时, 保真度指数衰减)" % p_obs)
print("   L=1 %.3f | L=5 %.3f | L=10 %.3f | L=20 %.3f | L=50 %.3f | L=200 %.3f"
      % (fid[1], fid[5], fid[10], fid[20], fid[50], fid[200]))
print("   半衰期 ≈ %.1f 步  → 这就是「再长点就崩」的物理原因" % (np.log(2) / max(-np.log(1 - p_obs), 1e-9)))
print()

# ---------- ③ 加锚点后的账 ----------
print("=" * 92)
print("③ ★ 核心账: 加了锚点, 精度只与【锚点间隔 L0】有关, 与总长 L 无关")
print("=" * 92)
print()
print("   净收益 = L0 / (c/q) = L0·q / c     其中 q = (1-p)^L0 = 段精度")
print("   解析最优: L0* = 1/|ln(1-p)| ≈ 1/p,  最优净收益 = 0.368 / (c·|ln(1-p)|)")
print()
print("  %-14s %-12s %-12s %-16s %s" % ("单步误差p", "最优间隔L0", "该点精度", "最优净收益", "判定 (c=%.3f)" % c))
print("  " + "-" * 82)
for pp in [0.005, 0.01, 0.02, 0.05, 0.10, p_obs]:
    L0s = 1.0 / max(-np.log(1 - pp), 1e-9)
    q = (1 - pp) ** L0s
    g = L0s * q / c
    tag = "✅✅ 非常值得" if g > 100 else ("✅ 值得" if g > 1 else "❌ 不值得")
    star = " ← 实测" if abs(pp - p_obs) < 1e-9 else ""
    print("  %-14.3f %-12.1f %-12.3f %-16.0f %s%s" % (pp, L0s, q, g, tag, star))
print()

# ---------- ④ 高精度档 ----------
print("  ④ 若要求【段精度 ≥ 0.90】(不想要崩, 只想要快):")
print("  %-14s %-14s %-12s %-14s %s" % ("单步误差p", "允许的L0", "段精度", "净收益", "判定"))
print("  " + "-" * 78)
for pp in [0.005, 0.01, 0.02, 0.05, 0.10, p_obs]:
    L0 = 0
    while (1 - pp) ** (L0 + 1) >= 0.90:
        L0 += 1
    q = (1 - pp) ** L0
    g = L0 * q / c
    tag = ("✅✅ 非常值得" if g > 100 else ("✅ 值得" if g > 1 else "❌ 不值得"))
    note = "  ★识别层不达标, 需先改进" if L0 == 0 else ""
    print("  %-14.3f %-14d %-12.4f %-14.1f %s%s" % (pp, L0, q, g, tag, note))
print()

# ---------- ⑤ c 敏感性 ----------
print("=" * 92)
print("⑤ ★ 决定性的旋钮: 收益 ∝ 1/c  (验证必须比推理便宜)")
print("=" * 92)
print()
print("  %-14s %-20s %-20s %-20s" % ("单步误差 p", "c=0.05 (廉价验证)", "c=0.20", "c=1.00 (验证=推理)"))
print("  " + "-" * 78)
for pp in [0.01, 0.02, 0.05, p_obs]:
    row = []
    for cc in [0.05, 0.2, 1.0]:
        g = 0.368 / (cc * max(-np.log(1 - pp), 1e-9))
        row.append("%.0f 倍" % g)
    print("  %-14.3f %-20s %-20s %-20s" % (pp, row[0], row[1], row[2]))
print()
print("  用时 %.2fs" % (time.time() - t0))
