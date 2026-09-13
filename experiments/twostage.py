#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
twostage.py — 「极小识别层 + 意义层」两段式, 行不行?
======================================================
用户架构:
  第一段: 极小网络, 只负责识别 (这是哪个字/形状)
  第二段: 意义层, 负责处理意思

关键: 识别层能压多小?
  按【识别任务】压 → 能压很小
  但意义层可能需要更多信息 → 就废了

测: 识别够用的最小 k  vs  意义够用的最小 k
"""
import numpy as np, time, json

t0 = time.time()
Vn = np.load('/workspace/_cache_V.npy')            # (48,896)
lab = np.array([gi for gi in range(8) for _ in range(6)])   # 8 语义类
D = Vn.shape[1]

mu = Vn.mean(0)
_, S, Vt = np.linalg.svd(Vn - mu, full_matrices=False)


def rec_err(Z, k):
    Xr = Z @ Vt[:k] + mu
    return float(np.linalg.norm(Xr - Vn) / np.linalg.norm(Vn))


def meaning_acc(Z, tr, te):
    Y = np.eye(8)[lab]
    W = np.linalg.lstsq(Z[tr], Y[tr], rcond=None)[0]
    return float(((Z[te] @ W).argmax(1) == lab[te]).mean())


tr = np.where(lab < 4)[0]
te = np.where(lab >= 4)[0]
base = meaning_acc(Vn - mu, tr, te)

print("=" * 90)
print("极小识别层 + 意义层   (48词 / 8语义类, 跨域: 训4类 测4类)")
print("=" * 90)
print()
print("  %-6s %-14s %-14s %-14s %-12s %s" % (
    "k", "识别层参数", "重建误差", "意义精度", "相对满维", "判定"))
print("  " + "-" * 84)

RES = []
for k in [2, 4, 8, 16, 32, 64, 128]:
    Z = (Vn - mu) @ Vt[:k].T
    r = rec_err(Z, k)
    a = meaning_acc(Z, tr, te)
    tag = "✅ 够用" if a > base * 0.9 else ("⚠️ 掉" if a > base * 0.7 else "❌ 废")
    RES.append((k, D * k, r, a))
    print("  %-6d %-14d %-14.4f %-14.4f %-12.1f%% %s" % (
        k, D * k, r, a, 100 * a / base, tag))

print()
print("  满维基线 (896维) = %.4f" % base)
print()

print("=" * 90)
print("★ 关键: 「识别够用」和「意义够用」的最小 k")
print("=" * 90)
print()
k_id = next((k for k, _, r, _ in RES if r < 0.15), None)
k_me = next((k for k, _, _, a in RES if a > base * 0.9), None)
p_id = next((p for k, p, r, _ in RES if k == k_id), None)
p_me = next((p for k, p, _, a in RES if k == k_me), None)
print("  %-34s %-12s %s" % ("判据", "最小 k", "识别层参数"))
print("  " + "-" * 62)
print("  %-34s %-12s %s" % ("识别够用 (重建误差<15%)",
      "k=%d" % k_id if k_id else "—", p_id))
print("  %-34s %-12s %s" % ("意义够用 (精度>90%基线)",
      "k=%d" % k_me if k_me else "—", p_me))
print()

if k_id and k_me and k_me > k_id:
    print("  ★ 意义层需要的 k 比识别层【大 %d 倍】" % (k_me / k_id))
    print("    → 识别层若按「够识别就行」来压 → 意义层直接废")
    print("    → 识别层的压缩率【必须由意义任务决定】, 不能由识别任务决定")

print()
print("=" * 90)
print("★ 第二对照: 识别层用「识别目标」监督训练 vs 无监督")
print("=" * 90)
print()
print("  %-6s %-18s %-18s %s" % ("k", "无监督(PCA)", "监督(判别方向)", "差异"))
print("  " + "-" * 66)
for k in [4, 8, 16, 32]:
    Z1 = (Vn - mu) @ Vt[:k].T
    a1 = meaning_acc(Z1, tr, te)
    mus = np.array([Vn[tr][lab[tr] == c].mean(0) for c in range(4)])
    # mus 是 (4,896): 判别方向在【右奇异向量 Vd】里 (896 维), 不是 U (4×4)
    _, _, Vd = np.linalg.svd(mus - mus.mean(0), full_matrices=False)
    Z2 = (Vn - mu) @ Vd[:min(k, len(Vd))].T
    a2 = meaning_acc(Z2, tr, te)
    print("  %-6d %-18.4f %-18.4f %+.4f %s" % (
        k, a1, a2, a2 - a1, "★监督更好" if a2 > a1 + 0.03 else ""))

print()
print("  用时 %.2fs" % (time.time() - t0))
