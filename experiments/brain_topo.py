#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_topo.py — 「像脑组织的分形结构」能不能当活核?
====================================================
问题: 把 B01/B02 那套"活"的动力学原样搬上去, 只换网络拓扑,
      看"活"到底是拓扑给的, 还是动力学给的。

固定: 动力学(自催化 + 疲劳慢变量 + 能量门控 + 耗散), D=64, 谱半径归一
变:   拓扑(环 / 随机 / 小世界 / 无标度 / 分层模块=脑组织)

活 的判据(全部是观测, 不是裁判):
  bounded   有界      (尾段|x|不发散不塌缩)
  e_self    能量自养  (尾段 e 自己维持, 不靠外参)
  motion    在动      (相邻位移 > 0)
  novelty   非周期    (尾段状态不回到旧状态的距离)
  effdim    有效维    (轨迹实际张开的维度, 遍历程度)
  dead      断流即死  (中途关掉能量源 → 是否衰到 0)
"""
import numpy as np

np.random.seed(7)
D          = 64
DT         = 0.05
STEPS      = 6000
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25
RHO, MU    = 0.02, 1.8          # 疲劳慢变量 / 疲劳抑制强度
SIG        = np.tanh

# ==================== 拓扑构造 ====================
def norm_spec(A, target):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (target / max(w, 1e-9))

def topo_ring(n):
    A = np.zeros((n, n))
    for i in range(n):
        A[i, (i + 1) % n] = 1.0
    return A

def topo_er(n, k=6, seed=0):
    r = np.random.RandomState(seed)
    A = (r.rand(n, n) < k / n).astype(float)
    np.fill_diagonal(A, 0.0)
    return A

def topo_ws(n, k=6, p=0.15, seed=0):          # 小世界
    r = np.random.RandomState(seed)
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(1, k // 2 + 1):
            A[i, (i + j) % n] = 1.0
            A[(i + j) % n, i] = 1.0
    for i in range(n):
        for j in range(1, k // 2 + 1):
            if r.rand() < p:
                tgt = (i + j) % n
                A[i, tgt] = 0.0; A[tgt, i] = 0.0
                new = r.randint(n)
                tries = 0
                while (new == i or A[i, new] > 0) and tries < 100:
                    new = r.randint(n); tries += 1
                A[i, new] = 1.0; A[new, i] = 1.0
    return A

def topo_ba(n, m=3, seed=0):                  # 无标度
    r = np.random.RandomState(seed)
    A = np.zeros((n, n))
    for i in range(m + 1):
        for j in range(i + 1, m + 1):
            A[i, j] = A[j, i] = 1.0
    for new in range(m + 1, n):
        deg = A[:new, :new].sum(1) + 1.0
        p = deg / deg.sum()
        chosen = r.choice(new, size=min(m, new), replace=False, p=p)
        for c in chosen:
            A[new, c] = A[c, new] = 1.0
    return A

def topo_hier(n=64, seed=0):                  # 分层模块 = 脑组织/海绵
    """自相似: 8→16→32→64 逐层套, 组内密连/跨组稀疏, 概率逐层递减"""
    r = np.random.RandomState(seed)
    levels = [8, 16, 32, 64]
    probs  = [0.45, 0.15, 0.05, 0.012]
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            for sz, p in zip(levels, probs):
                if i // sz == j // sz:
                    if r.rand() < p:
                        A[i, j] = A[j, i] = 1.0
                    break
    return A

# ==================== 度量 ====================
def metrics(states, Hx, He):
    X = np.array(states[-2000:])
    xs = X[::5]                                   # 400 个点
    m = len(xs)
    # 有效维: 协方差特征值的参与比
    C = np.cov(xs.T)
    w = np.linalg.eigvalsh(C); w = np.clip(w, 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    # 新奇度: 每个点到"50步以前任意点"的最小距离 (归一化) → 越大越不重复
    Dm = np.linalg.norm(xs[:, None, :] - xs[None, :, :], axis=2)
    mask = np.abs(np.arange(m)[:, None] - np.arange(m)[None, :]) > 10
    rec = float(np.median(np.where(mask, Dm, np.inf).min(1)))
    scale = float(np.mean(np.linalg.norm(xs, axis=1))) + 1e-9
    novelty = rec / scale
    return effdim, novelty

def run(A, label, cut_at=None):
    A = norm_spec(A, RHO_SPEC)
    x = np.random.randn(D) * 0.5
    f = np.zeros(D)
    e = 0.4
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
    effdim, novelty = metrics(states, Hx, He)
    mode = 'Y' if (tx.mean() > 0.3 and te.mean() > 0.05 and motion > 1e-4) else 'n'
    print("  %-16s |x|=%.3f e=%.3f 动=%.5f 新奇=%.3f 有效维=%5.1f  活=%s"
          % (label, tx.mean(), te.mean(), motion, novelty, effdim, mode), flush=True)
    return tx.mean(), te.mean(), novelty, effdim

def run_cut(A, label):
    A = norm_spec(A, RHO_SPEC)
    x = np.random.randn(D) * 0.5
    f = np.zeros(D); e = 0.4
    live, dead = [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        f = np.clip(f + DT * RHO * (act ** 2 - f), 0, 2)
        dx = s * (A @ act - DELTA * x - MU * f * x)
        eta = 0.0 if t >= 3000 else ETA
        de = eta * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT * de, 0.0)
        (live if t < 3000 else dead).append(np.linalg.norm(x))
    print("  %-16s 断流前|x|=%.3f  断流后|x|末段=%.5f  → %s"
          % (label, np.mean(live[-500:]), np.mean(dead[-200:]),
             '真死(模式消散)' if np.mean(dead[-200:]) < 0.05 else '没死'), flush=True)

# ==================== 主实验 ====================
RHO_SPEC = 0.98
print("=" * 78)
print("① 固定动力学(自催化+疲劳+能量门控), 只换拓扑 | D=%d 谱半径=%.2f" % (D, RHO_SPEC))
print("=" * 78)
TOPO = [
    ("环(ring)",        topo_ring(D)),
    ("随机(ER)",        topo_er(D, 6)),
    ("小世界(WS)",      topo_ws(D, 6, 0.15)),
    ("无标度(BA)",      topo_ba(D, 3)),
    ("分层模块=脑组织",  topo_hier(D)),
]
for name, A in TOPO:
    run(A, name)

print()
print("=" * 78)
print("② 断流即死测试 (第3000步关掉能量源)")
print("=" * 78)
for name, A in TOPO:
    run_cut(A, name)

print()
print("=" * 78)
print("③ 同样的脑组织拓扑, 扫「临界程度」(谱半径) → 活在哪一段最旺")
print("=" * 78)
Ah = topo_hier(D)
best = None
for rho in [0.85, 0.90, 0.95, 0.98, 1.00, 1.02]:
    RHO_SPEC = rho
    nrm, em, nov, ed = run(Ah, "谱半径=%.2f" % rho)
    if best is None or nov > best[1]:
        best = (rho, nov)
print("  → 新奇度峰值出现在 谱半径=%.2f" % best[0])
