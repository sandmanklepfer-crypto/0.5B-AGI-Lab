#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_topo3.py — 修「断流即死」+ 用尾段重新量「活」
====================================================
brain_topo2 发现: 断流后全都"没死"(|x|还在2.7~4.8)
根因: 我的动力学把耗散 -DELTA*x 也乘进了能量门 s(e)
      → e→0 时 s→0 → 整体冻住 = 「冻死」, 不是「消散」
修正(照 V30 的原话 "E=0 只剩 -γx"):
      维持力(需要能量):  s(e) * (A@act - MU*f*x)
      基础耗散(永远存在): -G0 * x        ← 不乘 s
      → e→0: dx = -G0*x → x→0 = 真死
"""
import numpy as np

np.random.seed(7)
D      = 64
DT     = 0.05
STEPS  = 8000
ETA, GAMMA, KAPPA = 0.5, 0.15, 0.6
G0     = 0.35                 # 基础耗散(不依赖能量)
RHO, MU = 0.02, 1.8
SIG     = np.tanh

def norm_spec(A, target=0.98):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (target / max(w, 1e-9))

# ---- 拓扑(复用 brain_topo2 的掩码) ----
def m_er(n, k=6, seed=0):
    r = np.random.RandomState(seed)
    A = np.triu((r.rand(n, n) < k / n).astype(float), 1)
    return A + A.T

def m_ws(n, k=6, p=0.15, seed=0):
    r = np.random.RandomState(seed)
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(1, k // 2 + 1):
            A[i, (i + j) % n] = A[(i + j) % n, i] = 1.0
    for i in range(n):
        for j in range(1, k // 2 + 1):
            if r.rand() < p:
                tgt = (i + j) % n
                A[i, tgt] = A[tgt, i] = 0.0
                new = r.randint(n); t = 0
                while (new == i or A[i, new] > 0) and t < 100:
                    new = r.randint(n); t += 1
                A[i, new] = A[new, i] = 1.0
    return A

def m_hier(n=64, seed=0):
    r = np.random.RandomState(seed)
    levels, probs = [8, 16, 32, 64], [0.45, 0.15, 0.05, 0.012]
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            for sz, p in zip(levels, probs):
                if i // sz == j // sz:
                    if r.rand() < p:
                        A[i, j] = A[j, i] = 1.0
                    break
    return A

def asym(M, seed=1):
    return np.random.RandomState(seed).randn(*M.shape) * M

# ---- 度量(只用尾段) ----
def measures(Hx, states):
    tx = np.array(Hx[-1500:])
    motion = float(np.abs(np.diff(tx)).mean())
    X = np.array(states[-200:]); m = len(X)
    C = np.cov(X.T); w = np.clip(np.linalg.eigvalsh(C), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    Dm = np.linalg.norm(X[:, None, :] - X[None, :, :], axis=2)
    idx = np.arange(m); mask = np.abs(idx[:, None] - idx[None, :]) > 5
    rec = float(np.median(np.where(mask, Dm, np.inf).min(1)))
    sc = float(np.mean(np.linalg.norm(X, axis=1))) + 1e-9
    return tx.mean(), motion, rec / sc, effdim

def run(A, label, cut_at=None):
    A = norm_spec(A)
    x = np.random.randn(D) * 0.5
    f = np.zeros(D); e = 0.4
    Hx, states = [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        f = np.clip(f + DT * RHO * (act ** 2 - f), 0, 2)
        et = 0.0 if (cut_at is not None and t >= cut_at) else ETA
        dx = s * (A @ act - MU * f * x) - G0 * x     # ← 耗散在门外
        de = et * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT * de, 0.0)
        Hx.append(np.linalg.norm(x))
        if t % 10 == 0:
            states.append(x.copy())
    if cut_at is not None:
        pre = float(np.mean(Hx[cut_at - 500:cut_at]))
        post = float(np.mean(Hx[-200:]))
        tag = '真死(消散)' if post < 0.02 else ('停住没消散' if post < 0.5 * pre else '没死')
        print("    %-18s 断流前=%.3f → 断流后=%.5f  %s" % (label, pre, post, tag), flush=True)
        return
    nrm, mot, nov, ed = measures(Hx, states)
    alive = nrm > 0.3 and mot > 1e-4
    print("    %-18s |x|=%.3f 动=%.5f 新奇=%.3f 有效维=%5.1f → %s"
          % (label, nrm, mot, nov, ed, '真活' if alive else ('冻住' if nrm > 0.3 else '死')),
          flush=True)
    return nrm, mot, nov, ed

TOPO = [("随机ER", m_er(D)), ("小世界WS", m_ws(D)), ("脑组织=分层模块", m_hier(D))]

print("=" * 84)
print("① 修正耗散后: 对称 vs 非对称 (尾段度量, 更干净)")
print("=" * 84)
for name, M in TOPO:
    print("  [%s]" % name)
    run(M.copy(), "对称")
    run(asym(M), "非对称")

print()
print("=" * 84)
print("② 修正后「断流即死」测试 (第4000步关能量源)  ← 这次该真死了")
print("=" * 84)
for name, M in TOPO:
    run(M.copy(), "对称 " + name, cut_at=4000)
    run(asym(M), "非对称 " + name, cut_at=4000)

print()
print("=" * 84)
print("③ 能量供给强度扫描 (非对称·脑组织): 活 ↔ 死 的相变在哪")
print("=" * 84)
Mh = asym(m_hier(D))
for et in [0.05, 0.10, 0.20, 0.30, 0.50]:
    ETA = et
    nrm, mot, nov, ed = run(Mh, "ETA=%.2f" % et)
