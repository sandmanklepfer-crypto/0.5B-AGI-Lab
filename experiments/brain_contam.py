#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_contam.py — 梯度会不会杀死生命? 「训脑 / 训桥」对照
==========================================================
脑: 非对称耦合 + 疲劳慢变量 + 能量门控 (brain_topo3 验证过的活核)
    D=12, A(12x12)=144 参数 (B01 就是 D=12 就活)
桥: 线性读出 W (12 -> K 类)
任务(模拟语言): 给初始状态 X0, 演化 T 步后预测 X0 的 K 类投影
    这个任务的真解 = 「别破坏信息」→ 梯度会推着脑退化成静止/线性衰减器
    而「活着」要求持续运动不重复  ← 两者在同一根杠杆上冲突

用【完整数值梯度】(不用 SPSA, 不依赖超参):
    192 个参数, 中心差分, 真梯度

三组 (同初始脑, 同任务, 同轮数, 多种子平均):
  A 训脑+训桥   损失 = 语言损失            ← 梯度流进脑
  B 只训桥      脑梯度置零                 ← 脑不碰梯度
  C 训脑+训桥   损失 = 语言损失 + λ·运动正则
指标: 准确率 / |A|范数 / 运动量 / 新奇度 / 有效维 / 断流即死
"""
import numpy as np

D, DT, K = 12, 0.05, 4
T        = 20
M        = 64
ETA, GAMMA, KAPPA = 0.5, 0.15, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh


def renorm(A, rho=0.98):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (rho / max(w, 1e-9))


def forward(A, X0, steps, record=False, cut_at=None):
    X = X0.copy()
    f = np.zeros_like(X)
    e = np.full((1, X.shape[1]), 0.4)
    traj = [] if record else None
    for t in range(steps):
        s = e / (KAPPA + e)
        act = SIG(X)
        f = np.clip(f + DT * RHO * (act ** 2 - f), 0, 2)
        et = 0.0 if (cut_at is not None and t >= cut_at) else ETA
        dX = s * (A @ act - MU * f * X) - G0 * X
        de = et * (act ** 2).sum(0, keepdims=True) - GAMMA * e
        X = X + DT * dX
        e = np.maximum(e + DT * de, 0.0)
        if record:
            traj.append(X.copy())
    return X, (np.array(traj) if record else None), e


def make_task(seed, n):
    r = np.random.RandomState(seed)
    P = r.randn(K, D)
    X0 = (r.randn(D, n) * 0.5)
    return X0, (P @ X0).argmax(0)


def ce(W, Xt, y):
    z = W @ Xt
    z = z - z.max(0, keepdims=True)
    p = np.exp(z); p /= p.sum(0, keepdims=True)
    return float(-np.log(p[y, np.arange(len(y))] + 1e-12).mean())


# ---------- 参数打包 ----------
NA = D * D


def unpack(v):
    return v[:NA].reshape(D, D), v[NA:].reshape(K, D)


def loss(v, Xtr, ytr, lam=0.0, want_motion=False):
    A, W = unpack(v)
    Xt, traj, _ = forward(A, Xtr, T, record=(lam > 0))
    L = ce(W, Xt, ytr)
    mot = 0.0
    if lam > 0:
        mot = float(np.linalg.norm(np.diff(traj, axis=0), axis=(1, 2)).mean())
        L = L - lam * mot * 100.0
    return (L, mot) if want_motion else L


def numgrad(v, Xtr, ytr, train_brain=True, lam=0.0, eps=2e-4):
    g = np.zeros_like(v)
    for i in range(len(v)):
        vp = v.copy(); vp[i] += eps
        vm = v.copy(); vm[i] -= eps
        g[i] = (loss(vp, Xtr, ytr, lam) - loss(vm, Xtr, ytr, lam)) / (2 * eps)
    if not train_brain:
        g[:NA] = 0.0                      # 脑梯度清零 = 冻结脑
    return g


def train(A0, W0, Xtr, ytr, iters=40, lr=0.05, train_brain=True, lam=0.0, tag=""):
    v = np.concatenate([A0.ravel(), W0.ravel()])
    mom = np.zeros_like(v)
    for i in range(iters):
        g = numgrad(v, Xtr, ytr, train_brain, lam)
        if i % 5 == 0:
            A_, W_ = unpack(v)
            print("      [%s] 迭代 %2d/%d  loss=%.4f  |A|=%.2f  运动=%.5f"
                  % (tag, i, iters, loss(v, Xtr, ytr, lam),
                     np.linalg.norm(A_), life(A_, steps=600)['motion']), flush=True)
        # 梯度裁剪(防爆)
        gn = np.linalg.norm(g)
        if gn > 50:
            g = g * (50 / gn)
        mom = 0.9 * mom + g
        v = v - (lr / (1 + i / 30.0)) * mom
    return unpack(v)


# ---------- 生命指标 ----------
def life(A, steps=4000, seed=99):
    X0 = (np.random.RandomState(seed).randn(D, 1) * 0.5)
    _, traj, _ = forward(A, X0, steps, record=True)
    tr = traj[:, :, 0]
    motion = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    ns = tr[-1500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::25]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    idx = np.arange(len(sub)); mask = np.abs(idx[:, None] - idx[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return dict(motion=motion, effdim=effdim, novelty=nov, anorm=float(np.linalg.norm(A)),
                asym=float(np.linalg.norm(A - A.T) / (np.linalg.norm(A) + 1e-9)))


def death(A, steps=6000, cut=1500):
    X0 = (np.random.RandomState(5).randn(D, M) * 0.5)
    _, tr, _ = forward(A, X0, steps, record=True, cut_at=cut)
    return float(np.linalg.norm(tr[cut - 50:cut], axis=1).mean()), \
           float(np.linalg.norm(tr[-50:], axis=1).mean())


def acc(A, W, Xte, yte):
    Xt, _, _ = forward(A, Xte, T)
    return float(((W @ Xt).argmax(0) == yte).mean())


# ==================== 主实验 ====================
SEEDS = [0, 1]
print("=" * 110)
print("梯度污染实验 | 脑 D=%d(%d参数, 非对称+疲劳+能量门控) | 任务=%d类 | 演化%d步 | 数值真梯度 | %d种子"
      % (D, NA, K, T, len(SEEDS)))
print("=" * 110)

rows = {"初始": [], "A 训脑": [], "B 只训桥": [], "C 正则": []}
for sd in SEEDS:
    A0 = renorm(np.random.RandomState(sd).randn(D, D))
    W0 = np.random.RandomState(100 + sd).randn(K, D) * 0.01
    Xtr, ytr = make_task(1 + sd, 300)
    Xte, yte = make_task(50 + sd, 200)

    def rec(name, A, W):
        m = life(A); m['acc'] = acc(A, W, Xte, yte); m['death'] = death(A)[1]
        rows[name].append(m)

    rec("初始", A0, W0)
    Aa, Wa = train(A0, W0, Xtr, ytr, train_brain=True, tag="A训脑")
    rec("A 训脑", Aa, Wa)
    Ab, Wb = train(A0, W0, Xtr, ytr, train_brain=False, tag="B只训桥")
    rec("B 只训桥", Ab, Wb)
    Ac, Wc = train(A0, W0, Xtr, ytr, train_brain=True, lam=0.5, tag="C正则")
    rec("C 正则", Ac, Wc)
    print("  种子%d 完成 | acc: A=%.0f%% B=%.0f%% C=%.0f%% | 运动: 初始=%.4f A=%.4f B=%.4f C=%.4f"
          % (sd, 100*rows["A 训脑"][-1]['acc'], 100*rows["B 只训桥"][-1]['acc'],
             100*rows["C 正则"][-1]['acc'], rows["初始"][-1]['motion'],
             rows["A 训脑"][-1]['motion'], rows["B 只训桥"][-1]['motion'],
             rows["C 正则"][-1]['motion']), flush=True)

print()
print("=" * 110)
print("%-10s %8s %9s %9s %8s %8s %8s   %s"
      % ("组", "准确率", "|A|范数", "运动量", "新奇度", "有效维", "非对称", "断流后|x|→0"))
print("-" * 110)
for name in ["初始", "A 训脑", "B 只训桥", "C 正则"]:
    g = lambda k: np.mean([r[k] for r in rows[name]])
    print("%-10s %7.1f%% %9.2f %9.5f %8.3f %8.1f %8.3f   %.5f"
          % (name, 100*g('acc'), g('anorm'), g('motion'), g('novelty'),
             g('effdim'), g('asym'), g('death')))

print()
print("=" * 110)
print("相对初始脑的变化")
print("=" * 110)
print("%-10s %11s %11s %11s %11s %11s %11s"
      % ("组", "准确率Δ", "|A|Δ", "运动量Δ", "新奇度Δ", "有效维Δ", "非对称Δ"))
for name in ["A 训脑", "B 只训桥", "C 正则"]:
    d = lambda k: np.mean([r[k] for r in rows[name]]) - np.mean([r[k] for r in rows["初始"]])
    print("%-10s %+10.1f%% %+10.2f %+10.5f %+10.3f %+10.1f %+10.3f"
          % (name, 100*d('acc'), d('anorm'), d('motion'), d('novelty'), d('effdim'), d('asym')))
