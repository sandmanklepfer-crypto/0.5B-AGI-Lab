#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_loop2.py — 闭环修正版: 回流必须连续
==========================================
brain_loop 的发现:
  用【离散onehot】回流 → 脑新奇度 0.143→0.002 (被压死)
  → 离散化本身就是杀手: 回流信号只有K种取值, 轨道塌成周期
推论: 离散瓶颈只能放【输出端】(语言本来就是离散的),
      回流端必须【连续】。

三组对照 (输出端一律离散, 只改回流端的连续性):
  H 硬符号回流    onehot(K维)          ← 上一版, 已知会死
  P 概率回流      softmax概率(K维连续)  ← 连续
  Z 嵌入回流      连续隐向量(H维)       ← 最连续
再扫 eps, 找「内化」和「污染」的分界。
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
K, H = 8, 32


def renorm(A, r=0.98):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


def brain_step(A, X, F, E, inj=None):
    act = SIG(X)
    F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
    g = E / (KAPPA + E)
    core = A @ act - MU * F * X
    if inj is not None:
        core = core + inj
    X = X + DT * (g * core - G0 * X)
    E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
    return X, F, E


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
    p = np.exp(z); return p / p.sum(0, keepdims=True)


W_IN_Z = None

def make_inj(B, X, mode, W_in, eps):
    """回流信号: 三种连续性"""
    global W_IN_Z
    lg, Hh = enc(B, X)
    P = softmax(lg)
    if W_IN_Z is None:
        W_IN_Z = np.random.RandomState(42).randn(X.shape[0], H) / np.sqrt(H)
    if mode == 'H':            # 硬符号(离散)
        idx = lg.argmax(0)
        S = np.zeros((K, X.shape[1])); S[idx, np.arange(X.shape[1])] = 1.0
        return eps * (W_in @ S)
    if mode == 'P':            # 概率(连续)
        return eps * (W_in @ P)
    if mode == 'Z':            # 连续嵌入
        return eps * (W_IN_Z @ np.tanh(Hh))
    return None


def rollout(A, X0, steps, B=None, W_in=None, eps=0.0, mode='P', ret_seq=False):
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, X.shape[1]), 0.4)
    Xs, seq = [X.copy()], []
    for t in range(steps):
        inj = make_inj(B, X, mode, W_in, eps) if (B is not None) else None
        if ret_seq:
            lg, _ = enc(B, X); seq.append(lg.argmax(0).copy())
        X, F, E = brain_step(A, X, F, E, inj)
        Xs.append(X.copy())
    out = np.concatenate(Xs, axis=1)
    return (out, np.array(seq)) if ret_seq else out


def train_bridge(B, Xall, iters=200, lr=0.02):
    M = Xall.shape[1]
    B = {k: v.copy() for k, v in B.items()}
    ms = {k: np.zeros_like(v) for k, v in B.items()}
    vs = {k: np.zeros_like(v) for k, v in B.items()}
    for it in range(iters + 1):
        lg, Hh = enc(B, Xall); P = softmax(lg)
        Xd = B['Wd'] @ P + B['bd'][:, None]
        dX = 2.0 * (Xd - Xall) / M
        G = dict(W1=None, b1=None, W2=None, b2=None,
                 Wd=dX @ P.T, bd=dX.sum(1))
        dP = B['Wd'].T @ dX
        dlg = P * (dP - (dP * P).sum(0, keepdims=True))
        G['W2'] = dlg @ Hh.T; G['b2'] = dlg.sum(1)
        dHh = B['W2'].T @ dlg
        dpre = dHh * (1 - Hh ** 2)
        G['W1'] = dpre @ Xall.T; G['b1'] = dpre.sum(1)
        for k in B:
            ms[k] = 0.9 * ms[k] + 0.1 * G[k]
            vs[k] = 0.999 * vs[k] + 0.001 * (G[k] ** 2)
            mh = ms[k] / (1 - 0.9 ** (it + 1)); vh = vs[k] / (1 - 0.999 ** (it + 1))
            B[k] -= lr * mh / (np.sqrt(vh) + 1e-8)
    return B


def self_err(B, Xall):
    """说出的话(离散符号)能重建自己多少 — 这是"语言之外的自己"的度量"""
    lg, _ = enc(B, Xall)
    idx = lg.argmax(0)
    S = np.zeros((K, Xall.shape[1])); S[idx, np.arange(Xall.shape[1])] = 1.0
    Xd = B['Wd'] @ S + B['bd'][:, None]
    return float(np.linalg.norm(Xd - Xall) / (np.linalg.norm(Xall) + 1e-9))


def life(A, W_in=None, B=None, eps=0.0, mode='P', steps=4000, seed=99):
    X0 = np.random.RandomState(seed).randn(D, 1) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 1), 0.4)
    tr = []
    for t in range(steps):
        inj = make_inj(B, X, mode, W_in, eps) if B is not None else None
        X, F, E = brain_step(A, X, F, E, inj)
        tr.append(X[:, 0].copy())
    tr = np.array(tr)
    motion = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    ns = tr[-1500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::25]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return motion, effdim, nov


def death(A, W_in=None, B=None, eps=0.0, mode='P', steps=5000, cut=1200):
    X0 = np.random.RandomState(5).randn(D, 32) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 32), 0.4)
    post = []
    for t in range(steps):
        inj = make_inj(B, X, mode, W_in, eps) if B is not None else None
        et = 0.0 if t >= cut else ETA
        act = SIG(X)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        core = A @ act - MU * F * X
        if inj is not None:
            core = core + inj
        X = X + DT * (g * core - G0 * X)
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        if t >= cut:
            post.append(np.linalg.norm(X, axis=0).mean())
    return float(np.mean(post[-50:]))


# ==================== 主实验 ====================
rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))
W_in = rng.randn(D, K) / np.sqrt(K)
NTR, NTE, STEPS = 48, 24, 15
Xtr = rng.randn(D, NTR) * 0.5
Xte = rng.randn(D, NTE) * 0.5

print("=" * 100)
print("闭环修正: 回流端连续性对照 (输出端一律离散)  D=%d 脑  K=%d符号" % (D, K))
print("=" * 100)

m0, e0, n0 = life(A)
print("\n[基线] 脑自由跑: 运动=%.5f 有效维=%.1f 新奇=%.3f" % (m0, e0, n0))

B = train_bridge(init_bridge(1), rollout(A, Xtr, STEPS), iters=250, lr=0.02)
print("[阶段1] 开环训桥完成, 自表达误差=%.4f" % self_err(B, rollout(A, Xte, STEPS)))

print("\n[核心对照] 回流连续性 → 脑的生死 (eps=0.8)")
print("  %-16s %-10s %-10s %-10s %-14s %s"
      % ("回流方式", "自表达误差", "脑运动", "脑有效维", "脑新奇(保留率)", "断流后|x|"))
# 基线 (未接桥)
mm0,ee0,nn0 = life(A)
print("  %-16s %-10s %-10.5f %-10.1f %-8.3f(100%%) %-10s  (参照)"
      % ("基线(裸脑)", "-", mm0, ee0, n0, "-"))
for mode, name in [('H', '硬符号(离散)'), ('P', '概率(连续)'), ('Z', '嵌入(连续)')]:
    Bx = {k: v.copy() for k, v in B.items()}
    for it in range(3):
        Xt = rollout(A, Xtr, STEPS, Bx, W_in, 0.8, mode)
        Bx = train_bridge(Bx, Xt, iters=80, lr=0.008)
    er = self_err(Bx, rollout(A, Xte, STEPS, Bx, W_in, 0.8, mode))
    mm, ee, nn = life(A, W_in, Bx, 0.8, mode, steps=3000)
    qq = death(A, W_in, Bx, 0.8, mode)
    keep = 100 * nn / n0
    tag = "✅活" if keep > 60 else ("⚠️削弱" if keep > 20 else "❌压死")
    print("  %-16s %-10.4f %-10.5f %-10.1f %-8.3f(%.0f%%) %.4f  %s"
          % (name, er, mm, ee, nn, keep, qq, tag))

print("\n[扫描] eps × 回流方式 → 脑新奇度 (环境越亮=越活)")
print("  %-8s %-14s %-14s %-14s" % ("eps", "硬符号", "概率", "嵌入"))
for eps in [0.1, 0.3, 0.8, 2.0, 5.0]:
    row = []
    for mode in ['H', 'P', 'Z']:
        Bx = {k: v.copy() for k, v in B.items()}
        for it in range(2):
            Xt = rollout(A, Xtr, STEPS, Bx, W_in, eps, mode)
            Bx = train_bridge(Bx, Xt, iters=60, lr=0.008)
        _, _, nn = life(A, W_in, Bx, eps, mode, steps=2000)
        row.append(nn)
    print("  %-8.1f %-14.3f %-14.3f %-14.3f" % (eps, row[0], row[1], row[2]))

print("\n[说出的话] 用连续的嵌入回流(eps=0.8), 跑60步看符号序列")
_, seq = rollout(A, (rng.randn(D, 1) * 0.5), 60, B, W_in, 0.8, 'Z', ret_seq=True)
print("  " + " ".join(str(s) for s in seq[:, 0]))
uniq = len(set(seq[:, 0].tolist()))
print("  用了 %d/%d 个符号" % (uniq, K))
