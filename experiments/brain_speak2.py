#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_speak2.py — 脑对接语言 v2: 去直流 + 全窗口可见 + 序列
==============================================================
v1 诊断: 直流占72%, 波动占28% → 桥容量被直流浪费
v2 改动: ① 去直流 ② 编码器看整个窗口 ③ 扫序列长度 W ④ 扫采样步长
理论: 序列信息量 = W × log2(K) bit; 若误差随 W 单调降 → 序列能承载脑的内容
"""
import numpy as np
import time

DT = 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
D, NB = 96, 24
d = D // NB
H = 96
K = 32


def make_brain(seed=0, scale=2.5):
    r = np.random.RandomState(seed)
    A = np.zeros((D, D))
    for b in range(NB):
        s = b * d; e = s + d
        sub = r.randn(d, d); w = np.abs(np.linalg.eigvals(sub)).max()
        A[s:e, s:e] = sub * (1.15 / w)
    return A * scale


def run_brain(A, steps, seed=99):
    r = np.random.RandomState(seed)
    x = r.randn(D, 1) * 0.5
    F = np.zeros_like(x); E = np.full((1, 1), 0.4)
    tr = []
    for t in range(steps):
        act = SIG(x)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        x = x + DT * (g * (A @ act - MU * F * x) - G0 * x)
        E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        tr.append(x[:, 0].copy())
    return np.array(tr)


class SeqBridge2:
    """h_t=tanh(W1 x_t); c=mean(h); g_t=tanh(W2[h_t;c]); logits=W3 g_t"""

    def __init__(self, W, K, seed=1):
        r = np.random.RandomState(seed)
        self.W, self.K = W, K
        self.B = dict(
            W1=r.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
            W2=r.randn(H, 2 * H) / np.sqrt(2 * H), b2=np.zeros(H),
            W3=r.randn(K, H) / np.sqrt(H), b3=np.zeros(K),
            Emb=r.randn(D, K) / np.sqrt(K),
        )
        self.ms = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.vs = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.t = 0

    def forward(self, X):
        m = X.shape[1]; W = self.W
        Hh = np.tanh(self.B['W1'] @ X + self.B['b1'][:, None])
        nwin = m // W
        ctx = Hh.reshape(H, nwin, W).mean(2)
        Ctx = np.repeat(ctx, W, axis=1)
        G = np.tanh(self.B['W2'] @ np.vstack([Hh, Ctx]) + self.B['b2'][:, None])
        lg = self.B['W3'] @ G + self.B['b3'][:, None]
        return lg, Hh, Ctx, G

    def step(self, X, lr):
        m = X.shape[1]; W = self.W; nwin = m // W
        lg, Hh, Ctx, G = self.forward(X)
        z = lg - lg.max(0, keepdims=True); P = np.exp(z); P /= P.sum(0, keepdims=True)
        Xd = self.B['Emb'] @ P
        diff = Xd - X
        L = float((diff ** 2).sum() / m)
        dX = 2.0 * diff / m
        Gd = {}
        Gd['Emb'] = dX @ P.T
        dP = self.B['Emb'].T @ dX
        dlg = P * (dP - (dP * P).sum(0, keepdims=True))
        Gd['W3'] = dlg @ G.T; Gd['b3'] = dlg.sum(1)
        dG = (self.B['W3'].T @ dlg) * (1 - G ** 2)
        dcat = self.B['W2'].T @ dG
        dHh = dcat[:H].copy(); dCtx = dcat[H:]
        Gd['W2'] = dG @ np.vstack([Hh, Ctx]).T; Gd['b2'] = dG.sum(1)
        dCr = dCtx.reshape(H, nwin, W).sum(2)
        dHh = dHh + np.repeat(dCr, W, axis=1) / W
        dpre = dHh * (1 - Hh ** 2)
        Gd['W1'] = dpre @ X.T; Gd['b1'] = dpre.sum(1)
        for k in self.B:
            self.ms[k] = 0.9 * self.ms[k] + 0.1 * Gd[k]
            self.vs[k] = 0.999 * self.vs[k] + 0.001 * (Gd[k] ** 2)
            self.B[k] -= lr * (self.ms[k] / (1 - 0.9 ** (self.t + 1))) / \
                         (np.sqrt(self.vs[k] / (1 - 0.999 ** (self.t + 1))) + 1e-8)
        self.t += 1
        return L

    def train(self, X, iters=400, lr=0.01):
        for _ in range(iters):
            L = self.step(X, lr)
        return L

    def evaluate(self, X):
        m = X.shape[1]; W = self.W; nwin = m // W
        lg, _, _, _ = self.forward(X)
        z = lg - lg.max(0, keepdims=True); P = np.exp(z); P /= P.sum(0, keepdims=True)
        Xd = self.B['Emb'] @ P
        se = float(np.linalg.norm(Xd - X) / np.linalg.norm(X))
        base = float(np.linalg.norm(X - X.mean(1, keepdims=True)) / np.linalg.norm(X))
        idx = lg.argmax(0)
        ent = []
        for t in range(W):
            c = np.bincount(idx[t::W], minlength=self.K) / max(nwin, 1)
            c = c[c > 0]
            ent.append(float(-(c * np.log(c)).sum() / np.log(self.K)))
        return se, base, float(np.mean(ent)), idx


def windows(tr, W, stride, count):
    n = len(tr); span = (W - 1) * stride + 1
    starts = np.linspace(0, n - span - 1, count).astype(int)
    return np.concatenate([tr[s:s + span:stride] for s in starts], 0).T


if __name__ == '__main__':
    A = make_brain()
    print("跑脑...", flush=True)
    tr = run_brain(A, 80000)
    mu = tr[:40000].mean(0)
    trc = tr - mu
    print("=" * 104)
    print("脑对接语言 v2 | 去直流 + 全窗口可见 | 脑D=%d(%d块) K=%d" % (D, NB, K))
    print("=" * 104)
    print("直流已去 (原直流占72%%)  波动范数=%.3f" % np.linalg.norm(trc, axis=1).mean())

    print()
    print("-" * 104)
    print("① 采样步长: 窗口内样本够不够独立")
    print("-" * 104)
    for st in [1, 5, 20, 80, 300]:
        a = trc[20000:40000 - st]; b = trc[20000 + st:40000]
        col = [i for i in range(D) if a[:, i].std() > 1e-9 and b[:, i].std() > 1e-9]
        c = float(np.mean([np.corrcoef(a[:, i], b[:, i])[0, 1] for i in col]))
        print("  步长%-5d 相邻样本相关=%.4f  %s" % (st, c,
              "冗余" if c > 0.99 else ("高度相关" if c > 0.9 else "较独立 ✅")))

    print()
    print("-" * 104)
    print("② ★ 序列长度 W → 表达能力")
    print("-" * 104)
    print("  %-5s %-10s %-10s %-9s %-9s %-9s %s"
          % ("W", "信息量bit", "自表达", "vs基线", "符号熵", "切换率", "耗时"))
    STRIDE = 20
    res = {}
    for W in [1, 2, 4, 8, 16]:
        Xtr = windows(trc[:60000], W, STRIDE, 1200)
        Xte = windows(trc[60000:76000], W, STRIDE, 300)
        br = SeqBridge2(W, K)
        tt = time.time()
        br.train(Xtr, iters=400, lr=0.01)
        se, base, ent, idx = br.evaluate(Xte)
        nwin = len(idx) // W
        ch = 0; tot = 0
        for w in range(nwin):
            s = idx[w * W:(w + 1) * W]
            ch += int((s[1:] != s[:-1]).sum()); tot += W - 1
        rate = ch / max(tot, 1)
        res[W] = (se, base, ent, rate)
        print("  %-5d %-10.0f %-10.4f %-9.2fx %-9.3f %-9.3f %.0fs"
              % (W, W * np.log2(K), se, se / base, ent, rate, time.time() - tt), flush=True)

    print()
    print("-" * 104)
    print("③ 结论: 序列是否打破了率失真权衡?")
    print("-" * 104)
    print("  (v1 单符号: 要么 失真1.29x 要么 熵0.20 — 不可兼得)")
    for W, (se, base, ent, rate) in res.items():
        ok = (se < base) and (ent > 0.5)
        print("  W=%-3d  失真=%.3f(%s)  熵=%.3f  %s"
              % (W, se, "达标" if se < base else "超标", ent,
                 "★★ 兼得!" if ok else ("✓失真达标" if se < base else "✗")))

    print()
    print("-" * 104)
    print("④ 最优配置「说出的话」")
    print("-" * 104)
    cands = [w for w in res if res[w][0] < res[w][1]]
    bW = min(cands, key=lambda w: res[w][0]) if cands else max(res, key=lambda w: res[w][2])
    br = SeqBridge2(bW, K)
    Xtr = windows(trc[:60000], bW, STRIDE, 1200)
    br.train(Xtr, iters=400, lr=0.01)
    Xte = windows(trc[60000:76000], bW, STRIDE, 30)
    _, _, _, idx = br.evaluate(Xte)
    print("  W=%d:" % bW)
    print("  " + " ".join("%X" % s for s in idx[:64]))
    print("  用了 %d/%d 个符号" % (len(set(idx.tolist())), K))
