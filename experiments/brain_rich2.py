#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_rich2.py — 脑丰富化: 打破「所有维度同步」
================================================
诊断(brain_rich诊断):
  特征值 2.31, 0.838, 0.0096... → 只有2个方向活着
  门控 g: 均值0.946 std0.013    → 饱和, 失效
  疲劳 F: 均值0.158 std0.013    → 恒定, 失效
根因: 24个维度共用同一套标量参数(G0/MU/rho) → 同步收缩/同步疲劳 → 坍缩到2维

假说: 给每个维度【自己的节奏】→ 不同维度在不同时间活跃 → 遍历更多维度

对照 (逐项加):
  A 基线            标量参数
  B 异质耗散        G0_i 每维不同
  C 多时间尺度疲劳   rho_i 跨3个数量级 (0.001~0.3)
  D B+C            异质 + 多尺度
  E D + 门控去饱和   KAPPA 调大, 让 g 工作在敏感区
  F E + 异质增益     MU_i 每维不同
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA = 0.5, 0.18
G0, RHO, MU, KAPPA = 0.35, 0.02, 1.8, 0.6
SIG = np.tanh
STEPS = 40000


def renorm_spec(A, r=1.02):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


def make_params(mode, seed=3):
    r = np.random.RandomState(seed)
    g = np.full(D, G0) if mode in ('A', 'C') else G0 * (0.2 + 1.6 * r.rand(D))
    if mode in ('A', 'B'):
        rho = np.full(D, RHO)
    else:
        rho = 10 ** (r.uniform(-3, -0.5, D))        # 0.001 ~ 0.32
    mu = np.full(D, MU) if mode != 'F' else MU * (0.2 + 1.6 * r.rand(D))
    kap = KAPPA if mode != 'E' else 60.0            # 调大 → g 远离饱和
    return g, rho, mu, kap


def run(A, mode, steps=STEPS, seed=99, warm=12000):
    G, RHOv, MUv, kap = make_params(mode)
    r = np.random.RandomState(seed)
    x = r.randn(D, 1) * 0.5
    F = np.zeros_like(x)
    E = np.full((1, 1), 0.4)
    tr, gs = [], []
    for t in range(steps):
        act = SIG(x)
        F = np.clip(F + DT * RHOv[:, None] * (act ** 2 - F), 0, 2)
        g = E / (kap + E)
        core = A @ act - MUv[:, None] * F * x
        x = x + DT * (g * core - G[:, None] * x)
        E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        tr.append(x[:, 0].copy()); gs.append(float(g))
    return np.array(tr), np.array(gs), G, RHOv, MUv


def metrics(tr):
    ns = tr[-5000:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    w = np.sort(w)[::-1]
    ed = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::50]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); m = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(m, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    mv = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    return ed, nov, mv, w


def death(A, mode, seed=99, steps=6000, cut=2000):
    G, RHOv, MUv, kap = make_params(mode)
    r = np.random.RandomState(seed)
    x = r.randn(D, 8) * 0.5
    F = np.zeros_like(x); E = np.full((1, 8), 0.4)
    post = []
    for t in range(steps):
        act = SIG(x)
        F = np.clip(F + DT * RHOv[:, None] * (act ** 2 - F), 0, 2)
        g = E / (kap + E)
        core = A @ act - MUv[:, None] * F * x
        x = x + DT * (g * core - G[:, None] * x)
        et = 0.0 if t >= cut else ETA
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        if t >= cut:
            post.append(float(np.linalg.norm(x, axis=0).mean()))
    return float(np.mean(post[-50:]))


rng = np.random.RandomState(0)
A = renorm_spec(rng.randn(D, D))

print("=" * 108)
print("脑丰富化: 打破「所有维度同步」 | D=%d | %d步" % (D, STEPS))
print("=" * 108)
print("  %-26s %-8s %-9s %-9s %-9s %-8s %s"
      % ("配置", "有效维", "新奇度", "运动", "前2特征值占比", "g均值", "断流后|x|"))
res = {}
for mode, name in [
    ('A', 'A 基线(全标量)'),
    ('B', 'B 异质耗散'),
    ('C', 'C 多时间尺度疲劳'),
    ('D', 'D 异质+多尺度'),
    ('E', 'E D+门控去饱和'),
    ('F', 'F E+异质增益'),
]:
    tr, gs, G, RHOv, MUv = run(A, mode)
    ed, nov, mv, w = metrics(tr)
    frac = float(w[:2].sum() / w.sum())
    q = death(A, mode)
    res[mode] = (ed, nov, mv, frac, gs.mean(), q)
    print("  %-26s %-8.2f %-9.3f %-9.5f %-13.2f %-8.3f %.5f %s"
          % (name, ed, nov, mv, frac, gs.mean(), q, "✅死" if q < 0.02 else "❌"))

print()
print("-" * 108)
print("提升幅度 (相对基线)")
print("-" * 108)
b = res['A']
for mode, name in [('B', 'B 异质耗散'), ('C', 'C 多时间尺度疲劳'),
                   ('D', 'D 异质+多尺度'), ('E', 'E D+门控去饱和'), ('F', 'F E+异质增益')]:
    e = res[mode]
    print("  %-26s 有效维 %+.2f (%.1f倍)   新奇 %+.3f (%.1f倍)   前2维占比 %.2f→%.2f"
          % (name, e[0] - b[0], e[0] / b[0], e[1] - b[1], e[1] / max(b[1], 1e-9), b[3], e[3]))

print()
print("-" * 108)
print("最优配置的详细体检")
print("-" * 108)
best_mode = max(res, key=lambda k: res[k][0])
bm = res[best_mode]
print("  最优: %s   有效维=%.2f (基线 %.2f)" % (best_mode, bm[0], b[0]))
tr, gs, G, RHOv, MUv = run(A, best_mode)
ed, nov, mv, w = metrics(tr)
print("  特征值谱 (前12): " + " ".join("%.3f" % v for v in w[:12]))
print("  前5维占比: %.2f  前10维占比: %.2f  → %s"
      % (w[:5].sum() / w.sum(), w[:10].sum() / w.sum(),
         "✅ 多维度参与" if w[:10].sum() / w.sum() > 0.9 else "仍集中在少数维"))
print("  门控 g: 均值=%.3f std=%.4f → %s"
      % (gs.mean(), gs.std(), "✅ 有动态" if gs.std() > 0.05 else "❌ 仍饱和"))
print("  各维耗散 G0: %.2f ~ %.2f (异质性)" % (G.min(), G.max()))
print("  各维疲劳速度 rho: %.4f ~ %.4f (跨 %.0f 倍)"
      % (RHOv.min(), RHOv.max(), RHOv.max() / max(RHOv.min(), 1e-9)))
print("  断流即死: %.5f  %s" % (bm[5], "✅真死" if bm[5] < 0.02 else "❌"))
