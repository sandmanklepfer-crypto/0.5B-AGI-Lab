#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
topreason2.py — 修正: 什么样的识别层, 长链推理才能【无损】?
=============================================================
topreason.py 发现: 随机码本 → 长链推理发散 (L=200 保真度 0.0007)
  ⇒ 识别层若只是"压缩聚类", 下游再快也只在放大错误

本实验定位: 到底是【码本】的问题, 还是【变换】的问题?
  变量1: 码本来源   A随机  B轨道采样(自洽)
  变量2: 变换类型   ①正交保距  ②收缩非线性

判据: 长链保真度 (符号链重建 vs 真实连续链, 余弦)
"""
import numpy as np, time

t0 = time.time()
D = 896
rng = np.random.RandomState(0)
Q, _ = np.linalg.qr(rng.randn(D, D))


def u(X):
    return X / (np.linalg.norm(X, axis=-1, keepdims=True) + 1e-12)


def step_orth(V):        # ① 正交旋转: 保距 (可逆推理)
    return u(V @ Q)


def step_contract(V):    # ② 收缩+非线性 (topreason.py 里那种)
    return 0.5 * np.tanh(V @ Q) + 0.5 * V


def orbit_vec(fn, V, N):     # 向量化: 整批码字一起推
    out = [V.copy()]
    for _ in range(N):
        V = fn(V)
        out.append(V.copy())
    return np.array(out)     # (N+1, K, D)


def quant(X, Cb):
    return (u(X) @ u(Cb).T).argmax(1)


def eval_cb(fn, Cb, Ls, maxL):
    tab = quant(fn(Cb), Cb)
    K = len(Cb)
    TR = orbit_vec(fn, Cb, maxL)          # (maxL+1, K, D) 参考连续链
    close = float(np.linalg.norm(fn(Cb) - Cb[tab], axis=1).mean())
    res = {}
    for L in Ls:
        vs = np.empty((L + 1, K, D))
        for i in range(K):
            s = i; ss = [s]
            for _ in range(L):
                s = tab[s]; ss.append(s)
            vs[:, i] = Cb[np.array(ss)]
        # 保真度: 每个码字、每个时刻的余弦
        a = u(TR[:L + 1]); b = u(vs)
        res[L] = float((a * b).sum(-1).mean())
    return res, close


# ---------- 码本 ----------
Crand = u(rng.randn(16, D))                       # A 随机码本
v0 = u(rng.randn(D))
Track = orbit_vec(step_orth, v0[None], 3000)[:, 0]   # 真实轨道 3001 点
Csamp16 = u(Track[::180][:16])                    # B 轨道采样 (自洽)
Csamp64 = u(Track[::45][:64])

print("=" * 94)
print("修正实验: 识别层码本 × 变换类型 → 长链推理是否无损")
print("=" * 94)
print("  %-40s %-12s %s" % ("配置", "闭合度", "长链保真度 (L=10/50/200)"))
print("  " + "-" * 88)

Ls = [1, 10, 50, 200]
maxL = 200
configs = [
    ("① 正交保距 + A 随机码本(16)", step_orth, Crand),
    ("① 正交保距 + B 自洽码本(16)", step_orth, Csamp16),
    ("① 正交保距 + B 自洽码本(64)", step_orth, Csamp64),
    ("② 收缩非线性 + A 随机码本(16)", step_contract, Crand),
    ("② 收缩非线性 + B 自洽码本(16)", step_contract, Csamp16),
]
R = {}
for nm, fn, Cb in configs:
    r, close = eval_cb(fn, Cb, Ls, maxL)
    R[nm] = r
    tag = "✅无损" if r[200] > 0.9 else ("⚠️" if r[200] > 0.5 else "❌崩")
    print("  %-40s %-12.4f L10=%.3f  L50=%.3f  L200=%.3f  %s" % (
        nm, close, r[10], r[50], r[200], tag))

print()
print("=" * 94)
print("关键定位")
print("=" * 94)
print()
print("  对照1: 同是随机码本, 变换换成正交 → 保真度 %.3f → %.3f" % (
    R["② 收缩非线性 + A 随机码本(16)"][200], R["① 正交保距 + A 随机码本(16)"][200]))
print("  对照2: 同是收缩变换, 码本换成自洽 → 保真度 %.3f → %.3f" % (
    R["② 收缩非线性 + A 随机码本(16)"][200], R["② 收缩非线性 + B 自洽码本(16)"][200]))
print("  对照3: 同是正交, 码本 16→64 (更密) → 保真度 %.3f → %.3f" % (
    R["① 正交保距 + B 自洽码本(16)"][200], R["① 正交保距 + B 自洽码本(64)"][200]))
print()
print("  用时 %.2fs" % (time.time() - t0))
