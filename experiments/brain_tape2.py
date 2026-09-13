#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_tape2.py — 真纸带: 内容寻址 (头由脑的状态决定)
======================================================
上一版的问题:
  头严格单向前进 → 每格只访问一次 → 读到的永远是"上一步的自己"
  = 延迟一步的自反馈, 不是纸带 (伪装的"成功")

本版真纸带 (内容寻址 = 真·图灵机的头可控跳转):
  地址 = LSH(脑状态)  → 状态相似则落在同一格
  读: 该格存的内容 → 注入脑
  写: 把当前脑状态写进该格
  新地址 → 新格子 (纸带增长 = 无限纸带)

这带来的关键性质:
  脑回到相似状态时, 读到的是【很久以前】写的自己
  → 这正好是用户要的「长段重复」: 回访间隔 = 周期长度

★ 核心度量: 回访间隔分布
  小单元重复 (1 1 1 1)  → 回访间隔 ≈ 1     (病态)
  长段重复 (每天吃饭)    → 回访间隔很大     (可接受)
  真活 (永不重复)        → 格子持续增长, 很少回访

对照:
  A 无纸带(有限状态机) / B 真纸带(内容寻址) / C 延迟线(上一版的伪纸带)
"""
import numpy as np
import time
from collections import defaultdict

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H, K = 32, 16
EPS = 0.15
TOTAL = 100000
BLOCK = 10000
TRAIN_SAMPLES, TRAIN_ITERS = 1500, 100


def renorm(A, r=1.02):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


class Brain:
    def __init__(self, A, seed=99):
        r = np.random.RandomState(seed)
        self.A = A
        self.x = r.randn(D, 1) * 0.5
        self.F = np.zeros_like(self.x)
        self.E = np.full((1, 1), 0.4)

    def step(self, inj=None, cut=False):
        act = SIG(self.x)
        self.F = np.clip(self.F + DT * RHO * (act ** 2 - self.F), 0, 2)
        g = self.E / (KAPPA + self.E)
        core = self.A @ act - MU * self.F * self.x
        if inj is not None:
            core = core + inj
        et = 0.0 if cut else ETA
        self.x = self.x + DT * (g * core - G0 * self.x)
        self.E = np.maximum(self.E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * self.E), 0.0)


class CAMTape:
    """内容寻址纸带: 地址 = LSH(状态)。真·可跳转的头。"""

    def __init__(self, R=12, levels=3, seed=5, tol_bits=1):
        r = np.random.RandomState(seed)
        self.W = r.randn(R, D) / np.sqrt(D)
        self.levels = levels
        self.edges = np.linspace(-1.0, 1.0, levels - 1)   # 量化边界
        self.tol = tol_bits
        self.store = {}          # addr -> content (D,1)
        self.last_visit = {}     # addr -> step
        self.revisit_gaps = []   # 回访间隔记录
        self.n_new = 0
        self.t = 0

    def addr(self, x):
        p = self.W @ x[:, 0]
        p = np.tanh(p)                                   # 有界
        q = np.digitize(p, self.edges)                    # 0..levels-1
        return int(np.ravel_multi_index(tuple(q.tolist()), (self.levels,) * len(q)))

    def read(self, a):
        return self.store.get(a, None)

    def write(self, a, x):
        self.store[a] = x.copy()
        self.t += 1
        if a in self.last_visit:
            self.revisit_gaps.append(self.t - self.last_visit[a])
        else:
            self.n_new += 1
        self.last_visit[a] = self.t


class DelayLine:
    """上一版的伪纸带: 严格单向的头 = 延迟线 (对照用)"""

    def __init__(self):
        self.tape = np.zeros((D, 1)); self.head = 0; self.pmean = 0.0
        self.w = np.random.RandomState(8).randn(D) / np.sqrt(D)

    def read(self, x):
        return self.tape

    def write(self, x):
        self.tape = x.copy()
        proj = float(self.w @ x[:, 0])
        self.pmean = 0.995 * self.pmean + 0.005 * proj
        if proj - self.pmean > 0.25:
            self.head += 1


class Bridge:
    def __init__(self, seed=1):
        b = np.random.RandomState(seed)
        self.B = dict(W1=b.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
                      W2=b.randn(K, H) / np.sqrt(H), b2=np.zeros(K),
                      Wd=b.randn(D, K) / np.sqrt(K), bd=np.zeros(D))
        self.ms = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.vs = {k: np.zeros_like(v) for k, v in self.B.items()}

    def enc(self, X):
        Hh = np.tanh(self.B['W1'] @ X + self.B['b1'][:, None])
        return self.B['W2'] @ Hh + self.B['b2'][:, None], Hh

    def sm(self, z):
        z = z - z.max(0, keepdims=True); p = np.exp(z); return p / p.sum(0, keepdims=True)

    def train(self, X, iters=TRAIN_ITERS, lr=0.01):
        M = X.shape[1]
        for it in range(iters + 1):
            lg, Hh = self.enc(X); P = self.sm(lg)
            Xd = self.B['Wd'] @ P + self.B['bd'][:, None]
            dX = 2.0 * (Xd - X) / M
            G = dict(Wd=dX @ P.T, bd=dX.sum(1))
            dP = self.B['Wd'].T @ dX
            dlg = P * (dP - (dP * P).sum(0, keepdims=True))
            G['W2'] = dlg @ Hh.T; G['b2'] = dlg.sum(1)
            dpre = (self.B['W2'].T @ dlg) * (1 - Hh ** 2)
            G['W1'] = dpre @ X.T; G['b1'] = dpre.sum(1)
            for k in self.B:
                self.ms[k] = 0.9 * self.ms[k] + 0.1 * G[k]
                self.vs[k] = 0.999 * self.vs[k] + 0.001 * (G[k] ** 2)
                self.B[k] -= lr * (self.ms[k] / (1 - 0.9 ** (it + 1))) / \
                             (np.sqrt(self.vs[k] / (1 - 0.999 ** (it + 1))) + 1e-8)

    def self_err(self, X):
        lg, _ = self.enc(X); idx = lg.argmax(0)
        S = np.zeros((K, X.shape[1])); S[idx, np.arange(X.shape[1])] = 1.0
        Xd = self.B['Wd'] @ S + self.B['bd'][:, None]
        return float(np.linalg.norm(Xd - X) / (np.linalg.norm(X) + 1e-9))


def eff_nov(tr):
    ns = tr[-2500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    ed = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::40]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); m = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(m, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return ed, nov


def gap_profile(tr, gaps=(1, 5, 50, 300, 1500, 8000, 30000)):
    sc = np.linalg.norm(tr - tr.mean(0), axis=1).mean() + 1e-9
    return {g: (float(np.median(np.linalg.norm(tr[g:] - tr[:-g], axis=1))) / sc if g < len(tr) else np.nan)
            for g in gaps}


rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))
W_rd = np.random.RandomState(7).randn(D, D) / np.sqrt(D)
W_in = np.random.RandomState(9).randn(D, K) / np.sqrt(K)

print("=" * 100)
print("真纸带 (内容寻址) | 脑D=%d 跑%d步 | 核心: 回访间隔分布 = 「重复的周期长度」" % (D, TOTAL))
print("=" * 100)

for mode, name in [('none', 'A 无纸带 (有限状态机)'),
                   ('delay', 'C 延迟线 (上一版的伪纸带)'),
                   ('cam', 'B 真纸带·内容寻址')]:
    t0 = time.time()
    br = Brain(A, seed=99)
    tape = CAMTape() if mode == 'cam' else (DelayLine() if mode == 'delay' else None)
    bri = Bridge()
    traj = []
    print("\n" + "-" * 100)
    print("[%s]" % name)
    print("-" * 100)
    print("  %-6s %-8s %-8s %-8s %-10s %-9s %-9s %s"
          % ("块", "纸带格数", "回访中位数", "有效维", "新奇", "自表达", "最小复发", "耗时"))
    for bi in range(TOTAL // BLOCK):
        bs = len(traj)
        for _ in range(BLOCK):
            lg, _ = bri.enc(br.x)
            P = bri.sm(lg)
            inj = EPS * (W_in @ P)
            if tape is not None:
                if mode == 'cam':
                    a = tape.addr(br.x)
                    c = tape.read(a)
                    if c is not None:
                        inj = inj + W_rd @ SIG(c)
                else:
                    inj = inj + W_rd @ SIG(tape.read(br.x))
            br.step(inj)
            if tape is not None:
                if mode == 'cam':
                    tape.write(tape.addr(br.x), br.x)
                else:
                    tape.write(br.x)
            traj.append(br.x[:, 0].copy())
        tr = np.array(traj)
        stride = max(1, len(tr) // TRAIN_SAMPLES)
        bri.train(tr[::stride][:TRAIN_SAMPLES].T)
        ed, nov = eff_nov(tr)
        se = bri.self_err(tr[-800:].T)
        if mode == 'cam':
            nslots = len(tape.store)
            gaps = tape.revisit_gaps[-BLOCK:]
            med_gap = int(np.median(gaps)) if gaps else -1
        elif mode == 'delay':
            nslots = tape.head; med_gap = -1
        else:
            nslots = 1; med_gap = -1
        prof = gap_profile(tr[-20000:], gaps=(300,))
        print("  %-6d %-8d %-8s %-8.1f %-10.3f %-9.4f %-9.3f %.0fs"
              % (bi + 1, nslots, med_gap, ed, nov, se, prof[300], time.time() - t0), flush=True)

    tr = np.array(traj)
    ed, nov = eff_nov(tr)
    print("\n  ── 最终体检 ──")
    if mode == 'cam':
        print("  纸带格数 = %d  (增长了 %d 次)" % (len(tape.store), tape.n_new))
        g = np.array(tape.revisit_gaps)
        if len(g):
            print("  ★ 回访间隔: 中位数=%d步  均值=%.0f步  最大=%d步" %
                  (int(np.median(g)), g.mean(), g.max()))
            print("     %s" % ("✅ 长段重复 (间隔>100步)" if np.median(g) > 100
                               else "❌ 小单元重复 (间隔<100步) — 就是'1 1 1 1'"))
    print("  有效维 = %.1f   新奇度 = %.3f" % (ed, nov))

    print("\n  ── ★ 周期检测 ──")
    for ga, v in gap_profile(tr).items():
        if np.isnan(v):
            print("    gap=%-6d 超出窗口" % ga); continue
        print("    gap=%-6d  %.4f %-42s %s" % (ga, v, "█" * int(min(v, 1) * 40),
              "❌周期" if v < 0.06 else ("弱" if v < 0.12 else "✅无重复")))
    vals = [v for v in gap_profile(tr).values() if not np.isnan(v)]
    print("    → 最小复发=%.4f  %s" % (min(vals),
          "✅ 窗口内无周期" if min(vals) > 0.06 else "❌ 存在周期"))

    print("\n  ── 断流即死 ──")
    br2 = Brain(A, seed=99); tp2 = CAMTape() if mode == 'cam' else (DelayLine() if mode == 'delay' else None)
    for _ in range(3000):
        inj = None
        if tp2 is not None:
            if mode == 'cam':
                c = tp2.read(tp2.addr(br2.x))
                inj = W_rd @ SIG(c) if c is not None else None
            else:
                inj = W_rd @ SIG(tp2.read(br2.x))
        br2.step(inj)
        if tp2 is not None:
            tp2.write(tp2.addr(br2.x), br2.x) if mode == 'cam' else tp2.write(br2.x)
    post = []
    for t in range(5000):
        inj = None
        if tp2 is not None:
            if mode == 'cam':
                c = tp2.read(tp2.addr(br2.x))
                inj = W_rd @ SIG(c) if c is not None else None
            else:
                inj = W_rd @ SIG(tp2.read(br2.x))
        br2.step(inj, cut=(t >= 1200))
        if t >= 1200:
            post.append(float(np.linalg.norm(br2.x)))
    print("    断流后 |x| = %.5f  %s" % (np.mean(post[-50:]),
          "✅ 真死(消散)" if np.mean(post[-50:]) < 0.02 else "❌ 死不了"))
