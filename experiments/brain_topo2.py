#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_topo2.py — 命门到底在哪: 拓扑(河道) 还是 非对称(漩涡)?
=============================================================
第一版结论: 对称耦合 → 全部冻死在固定点 (动=0.00000)
本版: 同一拓扑, 只加"非对称"(每条边一个随机权重, 不再 i↔j 相等)
      → 看活是不是从非对称里长出来的, 以及拓扑还管不管用
"""
import numpy as np

np.random.seed(7)
D      = 64
DT     = 0.05
STEPS  = 6000
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25
RHO, MU = 0.02, 1.8
SIG     = np.tanh

def norm_spec(A, target):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (target / max(w, 1e-9))

# ---------- 拓扑掩码(对称) ----------
def m_ring(n):
    A = np.zeros((n, n))
    for i in range(n):
        A[i, (i + 1) % n] = 1.0
        A[(i + 1) % n, i] = 1.0
    return A

def m_er(n, k=6, seed=0):
    r = np.random.RandomState(seed)
    A = ((r.rand(n, n) < k / n).astype(float))
    A = np.triu(A, 1); A = A + A.T
    return A

def m_ws(n, k=6, p=0.15, seed=0):
    r = np.random.RandomState(seed)
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(1, k // 2 + 1):
            A[i, (i + j) % n] = 1.0; A[(i + j) % n, i] = 1.0
    for i in range(n):
        for j in range(1, k // 2 + 1):
            if r.rand() < p:
                tgt = (i + j) % n
                A[i, tgt] = 0.0; A[tgt, i] = 0.0
                new = r.randint(n); t = 0
                while (new == i or A[i, new] > 0) and t < 100:
                    new = r.randint(n); t += 1
                A[i, new] = 1.0; A[new, i] = 1.0
    return A

def m_ba(n, m=3, seed=0):
    r = np.random.RandomState(seed)
    A = np.zeros((n, n))
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            A[i, j] = A[j, i] = 1.0
    for new in range(m + 1, n):
        deg = A[:new, :new].sum(1) + 1.0
        p = deg / deg.sum()
        for c in r.choice(new, size=min(m, new), replace=False, p=p):
            A[new, c] = A[c, new] = 1.0
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

# ---------- 由掩码生成耦合矩阵: 对称 vs 非对称 ----------
def sym(M):
    return M.copy()

def asym(M, seed=0):
    """只留一个方向 + 随机权重 → 非对称(非平衡)"""
    r = np.random.RandomState(seed)
    W = r.randn(*M.shape) * M          # 保留拓扑, 权重随机(非对称)
    return W

# ---------- 度量 ----------
def metrics(states):
    X = np.array(states[-2000:]); xs = X[::5]; m = len(xs)
    C = np.cov(xs.T)
    w = np.clip(np.linalg.eigvalsh(C), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    Dm = np.linalg.norm(xs[:, None, :] - xs[None, :, :], axis=2)
    idx = np.arange(m)
    mask = np.abs(idx[:, None] - idx[None, :]) > 10
    rec = float(np.median(np.where(mask, Dm, np.inf).min(1)))
    scale = float(np.mean(np.linalg.norm(xs, axis=1))) + 1e-9
    return effdim, rec / scale

def run(A, label, rho=0.98, cut_at=None):
    A = norm_spec(A, rho)
    x = np.random.randn(D) * 0.5
    f = np.zeros(D); e = 0.4
    Hx, He, states = [], [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        f = np.clip(f + DT * RHO * (act ** 2 - f), 0, 2)
        dx = s * (A @ act - DELTA * x - MU * f * x)
        eta = 0.0 if (cut_at is not None and t >= cut_at) else ETA
        de = eta * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT * de, 0.0)
        Hx.append(np.linalg.norm(x)); He.append(e)
        if t % 10 == 0:
            states.append(x.copy())
    tx = np.array(Hx[-1500:]); te = np.array(He[-1500:])
    motion = float(np.abs(np.diff(tx)).mean())
    effdim, novelty = metrics(states)
    if cut_at is not None:
        d = np.array(Hx[cut_at:])
        tail = float(np.mean(d[-200:]))
        print("    %-18s 断流后末段|x|=%.5f → %s"
              % (label, tail, '真死(模式消散)' if tail < 0.05 else '没死'), flush=True)
        return
    alive = tx.mean() > 0.3 and te.mean() > 0.05
    moving = motion > 1e-4
    tag = '真活' if (alive and moving) else ('假活(冻住)' if alive else '死')
    print("    %-18s |x|=%.3f e=%.2f 动=%.5f 新奇=%.3f 有效维=%5.1f → %s"
          % (label, tx.mean(), te.mean(), motion, novelty, effdim, tag), flush=True)
    return novelty, effdim

print("=" * 84)
print("① 对称 vs 非对称 × 5种拓扑   (D=%d, 谱半径=0.98, 同套动力学)")
print("=" * 84)
TOPO = [("环", m_ring(D)), ("随机ER", m_er(D)), ("小世界WS", m_ws(D)),
        ("无标度BA", m_ba(D)), ("分层模块=脑组织", m_hier(D))]
for name, M in TOPO:
    print("  [%s]" % name)
    run(sym(M), "对称(往下滚)")
    run(asym(M, seed=1), "非对称(有漩涡)")

print()
print("=" * 84)
print("② 非对称版: 断流即死测试 (第3000步关能量源)")
print("=" * 84)
for name, M in TOPO:
    run(asym(M, seed=1), name, cut_at=3000)

print()
print("=" * 84)
print("③ 脑组织拓扑(非对称) 扫「临界程度」→ 活在哪段最旺")
print("=" * 84)
Mh = asym(m_hier(D), seed=1)
best = None
for rho in [0.80, 0.90, 0.95, 0.98, 1.00, 1.05, 1.10]:
    nov, ed = run(Mh, "谱半径=%.2f" % rho, rho=rho)
    if best is None or nov > best[1]:
        best = (rho, nov)
print("  → 新奇度峰值 @ 谱半径=%.2f" % best[0])
