#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_loop3.py — 严格版: 内化的「剂量-响应」曲线
================================================
brain_loop2 的发现(但是测量不一致, 本版严格重做):
  弱内化 → 脑更活(novelty 升高); 强内化 → 压死
本版统一: 所有 life() 一律 steps=4000, 同一随机种子, 同一度量
并测: K(词表大小) 对「自表达误差」的影响 = 语言的表达上限
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H = 32
STEPS_LIFE = 4000
STEPS_DEATH = 5000; CUT = 1200


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


def init_bridge(K, seed=1):
    r = np.random.RandomState(seed)
    return dict(W1=r.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
                W2=r.randn(K, H) / np.sqrt(H), b2=np.zeros(K),
                Wd=r.randn(D, K) / np.sqrt(K), bd=np.zeros(D))


def enc(B, X):
    Hh = np.tanh(B['W1'] @ X + B['b1'][:, None])
    return B['W2'] @ Hh + B['b2'][:, None], Hh


def softmax(z):
    z = z - z.max(0, keepdims=True); p = np.exp(z); return p / p.sum(0, keepdims=True)


def train_bridge(B, Xall, iters=250, lr=0.02):
    M = Xall.shape[1]
    B = {k: v.copy() for k, v in B.items()}
    ms = {k: np.zeros_like(v) for k, v in B.items()}
    vs = {k: np.zeros_like(v) for k, v in B.items()}
    for it in range(iters + 1):
        lg, Hh = enc(B, Xall); P = softmax(lg)
        Xd = B['Wd'] @ P + B['bd'][:, None]
        dX = 2.0 * (Xd - Xall) / M
        G = dict(Wd=dX @ P.T, bd=dX.sum(1))
        dP = B['Wd'].T @ dX
        dlg = P * (dP - (dP * P).sum(0, keepdims=True))
        G['W2'] = dlg @ Hh.T; G['b2'] = dlg.sum(1)
        dpre = (B['W2'].T @ dlg) * (1 - Hh ** 2)
        G['W1'] = dpre @ Xall.T; G['b1'] = dpre.sum(1)
        for k in B:
            ms[k] = 0.9 * ms[k] + 0.1 * G[k]
            vs[k] = 0.999 * vs[k] + 0.001 * (G[k] ** 2)
            B[k] -= lr * (ms[k] / (1 - 0.9 ** (it + 1))) / (np.sqrt(vs[k] / (1 - 0.999 ** (it + 1))) + 1e-8)
    return B


def self_err(B, Xall):
    lg, _ = enc(B, Xall)
    idx = lg.argmax(0)
    S = np.zeros((lg.shape[0], Xall.shape[1])); S[idx, np.arange(Xall.shape[1])] = 1.0
    Xd = B['Wd'] @ S + B['bd'][:, None]
    return float(np.linalg.norm(Xd - Xall) / (np.linalg.norm(Xall) + 1e-9))


def metrics(tr):
    motion = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    ns = tr[-1500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::25]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return motion, effdim, nov


def life(A, B=None, W_in=None, eps=0.0, mode='P', mode_dim=None, steps=STEPS_LIFE, seed=99):
    X0 = np.random.RandomState(seed).randn(D, 1) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 1), 0.4)
    tr = []
    for t in range(steps):
        inj = None
        if B is not None and eps > 0:
            lg, Hh = enc(B, X); P = softmax(lg)
            if mode == 'H':
                idx = lg.argmax(0); S = np.zeros((lg.shape[0], 1)); S[idx, 0] = 1.0
                inj = eps * (W_in @ S)
            elif mode == 'P':
                inj = eps * (W_in @ P)
            else:
                inj = eps * (mode_dim @ np.tanh(Hh))
        X, F, E = brain_step(A, X, F, E, inj)
        tr.append(X[:, 0].copy())
    return metrics(np.array(tr))


def death(A, B=None, W_in=None, eps=0.0, mode='P', mode_dim=None):
    X0 = np.random.RandomState(5).randn(D, 32) * 0.5
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 32), 0.4); post = []
    for t in range(STEPS_DEATH):
        inj = None
        if B is not None and eps > 0:
            lg, Hh = enc(B, X); P = softmax(lg)
            if mode == 'H':
                idx = lg.argmax(0); S = np.zeros((lg.shape[0], 32)); S[idx, np.arange(32)] = 1.0
                inj = eps * (W_in @ S)
            elif mode == 'P':
                inj = eps * (W_in @ P)
            else:
                inj = eps * (mode_dim @ np.tanh(Hh))
        et = 0.0 if t >= CUT else ETA
        act = SIG(X)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        core = A @ act - MU * F * X
        if inj is not None:
            core = core + inj
        X = X + DT * (g * core - G0 * X)
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        if t >= CUT:
            post.append(np.linalg.norm(X, axis=0).mean())
    return float(np.mean(post[-50:]))


rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))
W_in_K = rng.randn(D, 8) / np.sqrt(8)
W_in_H = np.random.RandomState(42).randn(D, H) / np.sqrt(H)
Xtr = rng.randn(D, 64) * 0.5
Xte = rng.randn(D, 32) * 0.5

print("=" * 104)
print("内化的剂量-响应曲线  |  脑 D=%d  |  统一 steps=%d  |  同一随机种子" % (D, STEPS_LIFE))
print("=" * 104)

# 严格基线
X0 = np.random.RandomState(99).randn(D, 1) * 0.5
X = X0.copy(); F = np.zeros_like(X); E = np.full((1, 1), 0.4); tr0 = []
for t in range(STEPS_LIFE):
    X, F, E = brain_step(A, X, F, E, None)
    tr0.append(X[:, 0].copy())
m0, e0, n0 = metrics(np.array(tr0))
print("\n[严格基线] 裸脑(未接桥): 运动=%.5f 有效维=%.1f 新奇=%.3f   <- 参照点" % (m0, e0, n0))
q0 = death(A)
print("            断流即死: 后段|x|=%.4f  %s" % (q0, "真死 ✅" if q0 < 0.02 else "没死 ❌"))

B = train_bridge(init_bridge(8), Xtr)
print("\n[桥已训好] 自表达误差(K=8)=%.4f" % self_err(B, Xte))

print("\n" + "-" * 104)
print("[A] 内化剂量扫描 (回流=概率P, 连续) — 脑新奇度相对基线的变化")
print("-" * 104)
print("  %-8s %-14s %-14s %-14s %-14s %s" % ("eps", "脑运动", "脑有效维", "脑新奇", "相对基线", "断流后|x|"))
print("  %-8s %-14.5f %-14.1f %-14.3f %-14s %s" % ("0(裸脑)", m0, e0, n0, "100%", "%.4f" % q0))
best = None
for eps in [0.02, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6, 3.2]:
    Bx = {k: v.copy() for k, v in B.items()}
    for it in range(2):
        Xt = []
        Xc = Xtr.copy(); Fc = np.zeros_like(Xc); Ec = np.full((1, Xc.shape[1]), 0.4)
        for t in range(10):
            lg, _ = enc(Bx, Xc); P = softmax(lg)
            Xc, Fc, Ec = brain_step(A, Xc, Fc, Ec, eps * (W_in_K @ P))
            Xt.append(Xc.copy())
        Bx = train_bridge(Bx, np.concatenate(Xt, 1), iters=60, lr=0.008)
    mm, ee, nn = life(A, Bx, W_in_K, eps, 'P')
    qq = death(A, Bx, W_in_K, eps, 'P')
    keep = 100 * nn / n0
    tag = "★增益" if nn > n0 * 1.1 else ("≈持平" if nn > n0 * 0.6 else ("削弱" if nn > n0 * 0.2 else "❌压死"))
    if best is None or nn > best[1]:
        best = (eps, nn)
    print("  %-8.2f %-14.5f %-14.1f %-14.3f %-14s %.4f  %s"
          % (eps, mm, ee, nn, "%.0f%%" % keep, qq, tag))
print("\n  ★ 新奇度峰值 @ eps=%.2f (新奇=%.3f, 基线=%.3f, 提升 %.0f%%)"
      % (best[0], best[1], n0, 100 * (best[1] / n0 - 1)))

print("\n" + "-" * 104)
print("[B] 词表大小 K → 语言的表达上限 (自表达误差, 越小=越能说出自己)")
print("-" * 104)
print("  %-8s %-16s %-16s" % ("K", "自表达误差", "相对'啥都不说'"))
# '啥都不说' 基线: 总是输出均值
base_err = float(np.linalg.norm(Xte - Xte.mean(1, keepdims=True)) / np.linalg.norm(Xte))
print("  %-8s %-16.4f %-16s" % ("(不说话)", base_err, "1.000"))
for K in [2, 4, 8, 16, 32, 64]:
    Bk = train_bridge(init_bridge(K), Xtr, iters=250)
    er = self_err(Bk, Xte)
    print("  %-8d %-16.4f %-16.2f" % (K, er, er / base_err))
