#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_loop.py — 完整闭环: 脑 → 桥 → 符号(嘴) → 内化回流脑
============================================================
架构 (三条路, 不是一条):

   ┌───────────────────── 脑内循环 (思考) ─────────────────┐
   │                                                      │
   ▼                                                      │
 ┌─────┐   x    ┌─────────┐  符号   ┌─────┐                │
 │ 脑  │───────►│  桥      │───────►│ 嘴  │──► 说出来的话   │
 │自持核│        │非线性解码│        │离散 │                │
 └──┬──┘        └─────────┘        └─────┘                │
    │                │                                    │
    └──── 内化回流 ◄──┘  (走「状态」通道, 不是梯度通道) ────┘

铁律 (三条, 一条不破):
  ① 脑绝不接收梯度      → 梯度只更新桥
  ② 内化走状态通道      → s 作为脑方程的【输入项】, 不改 f
  ③ 内化项必须乘能量门   → 否则断流就死不掉 (V30 判据会失效)

自指目标 (无外部标签, 不写 if 裁判):
  说出的话要能重建自己:   L = || x − Dec(ŝ) ||²
  离散瓶颈 (K个符号) → 桥只能表达「可命名」的部分
  说不出 = 重构误差 = 语言之外的那部分自己

对照:
  A 开环  桥训完不回流            ← 只会说, 不被影响
  B 闭环  桥训完 + s 回流内化      ← 完整闭环 (语言长进脑子)
  扫描 内化强度 eps → 看「内化」和「污染」的分界
"""
import numpy as np

# ==================== 脑 (自持核, f 永不改) ====================
D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6      # 能量: 产能/耗散/门控
G0, RHO, MU = 0.35, 0.02, 1.8           # 基础耗散/疲劳时间尺度/疲劳抑制
SIG = np.tanh


def renorm(A, r=0.98):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


def brain_step(A, X, F, E, s_in=None, W_in=None, eps=0.0):
    """脑的一步。内化项在能量门【里面】→ 断流即死仍成立。"""
    act = SIG(X)
    F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
    g = E / (KAPPA + E)
    core = A @ act - MU * F * X
    if s_in is not None:
        core = core + eps * (W_in @ s_in)     # 内化: 状态通道
    dX = g * core - G0 * X                    # 耗散在门外 → E→0 只剩 -G0·x
    dE = ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E
    X = X + DT * dX
    E = np.maximum(E + DT * dE, 0.0)
    return X, F, E


# ==================== 桥 (非线性编解码 + 离散瓶颈) ====================
K, H = 8, 32           # K 个符号(语言的最小单位), 隐层 32


def init_bridge(seed=1):
    r = np.random.RandomState(seed)
    return dict(W1=r.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
                W2=r.randn(K, H) / np.sqrt(H), b2=np.zeros(K),
                Wd=r.randn(D, K) / np.sqrt(K), bd=np.zeros(D))


def enc(B, X):
    Hh = np.tanh(B['W1'] @ X + B['b1'][:, None])
    lg = B['W2'] @ Hh + B['b2'][:, None]
    return lg, Hh


def softmax(z):
    z = z - z.max(0, keepdims=True)
    p = np.exp(z)
    return p / p.sum(0, keepdims=True)


def onehot(lg):
    idx = lg.argmax(0)
    S = np.zeros((K, lg.shape[1]))
    S[idx, np.arange(lg.shape[1])] = 1.0
    return S, idx


# ==================== 闭环前向 ====================
def rollout(A, X0, steps, B=None, W_in=None, eps=0.0):
    """B=None → 开环(脑自由跑); B!=None 且 eps>0 → 内化回流"""
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, X.shape[1]), 0.4)
    Xs = [X.copy()]; Ss = []
    for t in range(steps):
        s_in = None
        if B is not None:
            lg, _ = enc(B, X)
            Sh, idx = onehot(lg)
            if eps > 0:
                s_in = Sh                      # 硬符号(真离散)回流
        X, F, E = brain_step(A, X, F, E, s_in, W_in, eps)
        Xs.append(X.copy())
    return np.concatenate(Xs, axis=1)          # (D, N*(steps+1))


# ==================== 桥训练 (梯度只到桥) ====================
def train_bridge(B, Xall, iters=200, lr=0.01):
    M = Xall.shape[1]
    B = {k: v.copy() for k, v in B.items()}
    ms = {k: np.zeros_like(v) for k, v in B.items()}
    vs = {k: np.zeros_like(v) for k, v in B.items()}
    b1, b2 = 0.9, 0.999
    for it in range(iters + 1):
        lg, Hh = enc(B, Xall)
        P = softmax(lg)
        Xd = B['Wd'] @ P + B['bd'][:, None]
        dX = 2.0 * (Xd - Xall) / M                       # dL/dXd
        gW = 2.0 * (Xd - Xall) * (Xd - Xall)             # dummy(未用)
        dWd = dX @ P.T
        dbd = dX.sum(1)
        dP = B['Wd'].T @ dX
        dlg = P * (dP - (dP * P).sum(0, keepdims=True))
        dW2 = dlg @ Hh.T
        db2 = dlg.sum(1)
        dHh = B['W2'].T @ dlg
        dpre = dHh * (1 - Hh ** 2)
        dW1 = dpre @ Xall.T
        db1 = dpre.sum(1)
        G = dict(W1=dW1, b1=db1, W2=dW2, b2=db2, Wd=dWd, bd=dbd)
        for k in B:
            ms[k] = b1 * ms[k] + (1 - b1) * G[k]
            vs[k] = b2 * vs[k] + (1 - b2) * (G[k] ** 2)
            mh = ms[k] / (1 - b1 ** (it + 1))
            vh = vs[k] / (1 - b2 ** (it + 1))
            B[k] -= lr * mh / (np.sqrt(vh) + 1e-8)
    return B


# ==================== 指标 ====================
def self_err(B, Xall):
    """自表达误差: 说出的话能重建自己多少 (越小=越能说出自己)"""
    lg, _ = enc(B, Xall)
    Sh, idx = onehot(lg)
    Xd = B['Wd'] @ Sh + B['bd'][:, None]
    return float(np.linalg.norm(Xd - Xall) / (np.linalg.norm(Xall) + 1e-9))


def sym_usage(B, Xall):
    lg, _ = enc(B, Xall)
    _, idx = onehot(lg)
    cnt = np.bincount(idx, minlength=K) / len(idx)
    ent = float(-(cnt[cnt > 0] * np.log(cnt[cnt > 0])).sum() / np.log(K))
    return ent, cnt


def life(A, W_in=None, B=None, eps=0.0, steps=4000, seed=99):
    X0 = np.random.RandomState(seed).randn(D, 1) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 1), 0.4)
    tr = []
    for t in range(steps):
        s_in = None
        if B is not None and eps > 0:
            _, idx = onehot(enc(B, X)[0])
            Sh = np.zeros((K, 1)); Sh[idx, 0] = 1.0
            s_in = Sh
        X, F, E = brain_step(A, X, F, E, s_in, W_in, eps)
        tr.append(X.copy())
    tr = np.array(tr)[:, :, 0]                   # (T, D)
    motion = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    ns = tr[-1500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::25]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return motion, effdim, nov


def death(A, W_in=None, B=None, eps=0.0, steps=6000, cut=1500):
    X0 = np.random.RandomState(5).randn(D, 32) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 32), 0.4)
    pre, post = [], []
    for t in range(steps):
        s_in = None
        if B is not None and eps > 0:
            _, idx = onehot(enc(B, X)[0])
            Sh = np.zeros((K, 32)); Sh[idx, np.arange(32)] = 1.0
            s_in = Sh
        et = 0.0 if t >= cut else ETA
        act = SIG(X)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        core = A @ act - MU * F * X
        if s_in is not None:
            core = core + eps * (W_in @ s_in)
        X = X + DT * (g * core - G0 * X)
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        (pre if t < cut else post).append(np.linalg.norm(X, axis=0).mean())
    return float(np.mean(pre[-50:])), float(np.mean(post[-50:]))


# ==================== 主实验 ====================
rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))                    # 非对称活核
W_in = rng.randn(D, K) / np.sqrt(K)            # 内化注入矩阵(固定随机)
B0 = init_bridge(1)

NTR, NTE, STEPS = 48, 24, 15
Xtr = (rng.randn(D, NTR) * 0.5)
Xte = (rng.randn(D, NTE) * 0.5)

print("=" * 96)
print("完整闭环: 脑(D=%d,自持核) → 桥(非线性+%d符号瓶颈) → 嘴 → 内化回流脑" % (D, K))
print("=" * 96)

m0, e0, n0 = life(A)
print("\n[基线] 脑自由跑(未接任何东西):  运动=%.5f 有效维=%4.1f 新奇=%.3f" % (m0, e0, n0))
p, q = death(A)
print("        断流即死: %.2f → %.4f  %s" % (p, q, "真死 ✅" if q < 0.02 else "没死 ❌"))

# ---------- 阶段1: 开环训桥 (脑冻结, 只训桥) ----------
print("\n[阶段1] 开环训桥 (脑冻结, 梯度只到桥)...")
B = train_bridge(B0, rollout(A, Xtr, STEPS), iters=250, lr=0.02)
Xte_all = rollout(A, Xte, STEPS)
err_open = self_err(B, Xte_all)
ent, cnt = sym_usage(B, Xte_all)
print("  自表达误差=%.4f  符号利用率=%.1f/%d (熵%.2f)" % (err_open, (cnt > 0.02).sum(), K, ent))
print("  符号分布: " + " ".join("%.2f" % c for c in cnt))

# ---------- 阶段2: 闭环内化 ----------
print("\n[阶段2] 闭环内化 (s 回流脑, 仍只训桥)...")
Bc = {k: v.copy() for k, v in B.items()}
EPS = 0.8
for it in range(3):
    Xtr_c = rollout(A, Xtr, STEPS, Bc, W_in, EPS)
    Bc = train_bridge(Bc, Xtr_c, iters=80, lr=0.008)
    Xte_c = rollout(A, Xte, STEPS, Bc, W_in, EPS)
    err = self_err(Bc, Xte_c)
    print("  闭环第%d轮: 自表达误差=%.4f" % (it + 1, err))
err_closed = self_err(Bc, Xte_c)
ent_c, cnt_c = sym_usage(Bc, Xte_c)
print("  符号利用率=%.1f/%d (熵%.2f)  分布: %s"
      % ((cnt_c > 0.02).sum(), K, ent_c, " ".join("%.2f" % c for c in cnt_c)))

# ---------- 闭环后: 脑还活吗 ----------
print("\n[闭环后] 脑的动力学是否还活?")
m1, e1, n1 = life(A, W_in, Bc, EPS)
p2, q2 = death(A, W_in, Bc, EPS)
print("  闭环脑:      运动=%.5f 有效维=%4.1f 新奇=%.3f" % (m1, e1, n1))
print("  断流即死:    %.2f → %.4f  %s" % (p2, q2, "真死 ✅" if q2 < 0.02 else "没死 ❌"))

# ---------- 内化强度扫描 ----------
print("\n[扫描] 内化强度 eps → 「内化」和「污染」的分界在哪")
print("  %-8s %-12s %-12s %-12s %-12s %s"
      % ("eps", "自表达误差", "脑运动", "脑有效维", "脑新奇", "断流后|x|"))
for eps in [0.0, 0.2, 0.5, 0.8, 1.5, 3.0]:
    Bx = {k: v.copy() for k, v in B.items()}
    for it in range(2):
        Xt = rollout(A, Xtr, STEPS, Bx, W_in, eps)
        Bx = train_bridge(Bx, Xt, iters=60, lr=0.008)
    Xe = rollout(A, Xte, STEPS, Bx, W_in, eps)
    er = self_err(Bx, Xe)
    mm, ee, nn = life(A, W_in, Bx, eps, steps=2000)
    _, qq = death(A, W_in, Bx, eps, steps=4000, cut=1000)
    print("  %-8.1f %-12.4f %-12.5f %-12.1f %-12.3f %.4f %s"
          % (eps, er, mm, ee, nn, qq, "✅死" if qq < 0.02 else "❌没死"))

# ---------- 说出的话 ----------
print("\n[说出的话] 闭环脑跑40步, 逐帧说出符号 (看有没有结构)")
X = (rng.randn(D, 1) * 0.5); F = np.zeros_like(X); E = np.full((1, 1), 0.4)
seq = []
for t in range(40):
    _, idx = onehot(enc(Bc, X)[0])
    seq.append(int(idx[0]))
    Sh = np.zeros((K, 1)); Sh[idx, 0] = 1.0
    X, F, E = brain_step(A, X, F, E, Sh, W_in, EPS)
print("  " + " ".join(str(s) for s in seq))
tr = np.zeros((K, K))
for x, y in zip(seq[:-1], seq[1:]):
    tr[x, y] += 1
tr = tr / (tr.sum(1, keepdims=True) + 1e-9)
print("  符号转移矩阵 (行=当前, 列=下一个):")
for i in range(K):
    if tr[i].sum() > 0:
        print("   %d ► %s" % (i, " ".join("%.2f" % v for v in tr[i])))
