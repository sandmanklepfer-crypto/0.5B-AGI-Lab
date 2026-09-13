#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_edge.py — 找混沌边缘 (现在有纸带了, 相变扫描才有意义)
==============================================================
理论: 不可判定 → 不能从外部裁判生死 → 只能让它在动力学上自己活着
      唯一"永不停机也不空转"的区域 = 混沌边缘

正式尺子: 最大李雅普诺夫指数 λ_max
  λ < 0   稳定 → 收敛到不动点/周期 = 死(复读)
  λ ≈ 0   ★ 临界 = 混沌边缘 (有界且永不精确重复)
  λ > 0   混沌/发散 = 乱码

对照: 无纸带(有限状态机) vs 有纸带(图灵机)
      → 看纸带是否把"活"的区域扩大了

指标: λ_max / 复发距离 / 有效维 / 新奇度 / 断流即死
"""
import numpy as np

D, DT = 24, 0.05
ETA0, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0_0, RHO, MU0 = 0.35, 0.02, 1.8
SIG = np.tanh


def renorm_spec(A, r):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


class Sys:
    """一个"脑+纸带"的完整系统"""

    def __init__(self, A, W_rd, tape_on, G0=G0_0, MU=MU0, ETA=ETA0, seed=5, D=D):
        self.D = D
        self.A, self.W_rd, self.on = A, W_rd, tape_on
        self.G0, self.MU, self.ETA = G0, MU, ETA
        r = np.random.RandomState(seed)
        self.x = (r.randn(D, 1) * 0.5)
        self.F = np.zeros_like(self.x)
        self.E = np.full((1, 1), 0.4)
        self.tape = [np.zeros((D, 1))]
        self.head = 0

    def copy(self):
        s = Sys(self.A, self.W_rd, self.on, self.G0, self.MU, self.ETA, D=self.D)
        s.x = self.x.copy(); s.F = self.F.copy(); s.E = self.E.copy()
        s.tape = [t.copy() for t in self.tape]; s.head = self.head
        return s

    def step(self, cut=False):
        inj = None
        if self.on:
            inj = self.W_rd @ SIG(self.tape[self.head])
        act = SIG(self.x)
        self.F = np.clip(self.F + DT * RHO * (act ** 2 - self.F), 0, 2)
        g = self.E / (KAPPA + self.E)
        core = self.A @ act - self.MU * self.F * self.x
        if inj is not None:
            core = core + inj
        et = 0.0 if cut else self.ETA
        self.x = self.x + DT * (g * core - self.G0 * self.x)
        self.E = np.maximum(self.E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * self.E), 0.0)
        if self.on:
            self.tape[self.head] = self.x.copy()
            drive = float(SIG(self.x[0, 0]))
            if drive > 0.2:
                self.head += 1
            elif drive < -0.2:
                self.head -= 1
            if self.head < 0:
                self.head = 0
            if self.head >= len(self.tape):
                self.tape.append(np.zeros((self.D, 1)))


def lyapunov(A, W_rd, on, steps=2400, renorm_every=20, eps=1e-8, seed=5, **kw):
    s1 = Sys(A, W_rd, on, seed=seed, **kw)
    s2 = s1.copy()
    s2.x = s2.x + np.random.RandomState(seed + 1).randn(*s2.x.shape) * eps
    logs = []
    for blk in range(steps // renorm_every):
        for _ in range(renorm_every):
            s1.step(); s2.step()
        d = float(np.linalg.norm(s1.x - s2.x))
        if d > 1e-30:
            logs.append(np.log(d / eps))
            s2.x = s1.x + (s2.x - s1.x) * (eps / d)      # 只拉回脑, 纸带保留各自历史
    return float(np.mean(logs) / renorm_every) if logs else 0.0


def trajectory(A, W_rd, on, steps=12000, seed=99, **kw):
    s = Sys(A, W_rd, on, seed=seed, **kw)
    tr = []
    for _ in range(steps):
        s.step(); tr.append(s.x[:, 0].copy())
    return np.array(tr)


def metrics(tr):
    mv = float(np.linalg.norm(np.diff(tr, axis=0), axis=1).mean())
    ns = tr[-2500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    ed = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::40]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return mv, ed, nov


def recurrence(tr, gap=400, ns=1200):
    idx = np.linspace(0, len(tr) - 1, ns).astype(int)
    sub = tr[idx]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    mask = np.abs(idx[:, None] - idx[None, :]) > gap
    scale = Dm[~np.eye(ns, dtype=bool)].mean()
    return float(np.median(np.where(mask, Dm, np.inf).min(1))) / (scale + 1e-9)


def died(A, W_rd, on, steps=6000, cut=2000, **kw):
    s = Sys(A, W_rd, on, seed=5, **kw)
    s.x = np.random.RandomState(5).randn(D, 8) * 0.5
    post = []
    for t in range(steps):
        s.step(cut=(t >= cut))
        if t >= cut:
            post.append(np.linalg.norm(s.x, axis=0).mean())
    return float(np.mean(post[-50:]))


rng = np.random.RandomState(0)
A0 = rng.randn(D, D)
W_rd = rng.randn(D, D) / np.sqrt(D)

print("=" * 100)
print("混沌边缘扫描 | 最大李雅普诺夫指数 λ | 脑D=%d" % D)
print("=" * 100)
print("  判据: λ<0=死(复读)  λ≈0=★边缘(活)  λ>0=乱/发散")

print("\n" + "-" * 100)
print("① 扫谱半径 rho (主要控制参数) — 无纸带 vs 有纸带")
print("-" * 100)
print("  %-7s | %-26s | %-26s" % ("", "无纸带(有限状态机)", "有纸带(图灵机)"))
print("  %-7s | %-8s %-8s %-8s | %-8s %-8s %-8s" % ("rho", "λ", "复发", "有效维", "λ", "复发", "有效维"))
best = None
for rho in [0.85, 0.92, 0.98, 1.02, 1.06, 1.10, 1.18, 1.30]:
    A = renorm_spec(A0, rho)
    out = []
    for on in [False, True]:
        lam = lyapunov(A, W_rd, on)
        tr = trajectory(A, W_rd, on, steps=8000)
        rec = recurrence(tr)
        _, ed, _ = metrics(tr)
        out.append((lam, rec, ed))
    (l0, r0, e0), (l1, r1, e1) = out
    # 边缘判据: |λ| 最小 且 不重复
    score = abs(l1) * (1.0 if r1 > 0.1 else 3.0)
    if best is None or score < best[0]:
        best = (score, rho, l1, r1, e1)
    print("  %-7.2f | %-8.3f %-8.3f %-8.1f | %-8.3f %-8.3f %-8.1f"
          % (rho, l0, r0, e0, l1, r1, e1))

print("\n  ★ 边缘候选: rho=%.2f  有纸带 λ=%.3f 复发=%.3f 有效维=%.1f" % (best[1], best[2], best[3], best[4]))

print("\n" + "-" * 100)
print("② 在边缘附近细扫 rho (步长 0.01)")
print("-" * 100)
print("  %-7s %-10s %-10s %-10s %-10s %s" % ("rho", "λ", "复发", "有效维", "新奇", "判据"))
for rho in np.arange(best[1] - 0.04, best[1] + 0.045, 0.01):
    A = renorm_spec(A0, rho)
    lam = lyapunov(A, W_rd, True)
    tr = trajectory(A, W_rd, True, steps=10000)
    rec = recurrence(tr)
    mv, ed, nov = metrics(tr)
    if abs(lam) < 0.01 and rec > 0.15:
        tag = "★ 混沌边缘"
    elif lam < -0.02:
        tag = "死(收敛)"
    elif lam > 0.02:
        tag = "乱/发散"
    else:
        tag = "临界附近"
    print("  %-7.3f %-10.4f %-10.3f %-10.1f %-10.3f %s" % (rho, lam, rec, ed, nov, tag))

print("\n" + "-" * 100)
print("③ 扫能量供给 ETA (纸带开启, rho=%.2f) — 相变的另一个轴" % best[1])
print("-" * 100)
A = renorm_spec(A0, best[1])
print("  %-7s %-10s %-10s %-10s %-10s %s" % ("ETA", "λ", "复发", "有效维", "新奇", "断流后|x|"))
for et in [0.05, 0.10, 0.20, 0.35, 0.50, 0.80]:
    lam = lyapunov(A, W_rd, True, ETA=et)
    tr = trajectory(A, W_rd, True, steps=8000, ETA=et)
    rec = recurrence(tr)
    mv, ed, nov = metrics(tr)
    q = died(A, W_rd, True, ETA=et)
    print("  %-7.2f %-10.4f %-10.3f %-10.1f %-10.3f %.5f %s"
          % (et, lam, rec, ed, nov, q, "✅死" if q < 0.02 else "❌死不了"))

print("\n" + "-" * 100)
print("④ 边缘处的最终体检 (rho=%.2f)" % best[1])
print("-" * 100)
A = renorm_spec(A0, best[1])
tr = trajectory(A, W_rd, True, steps=15000)
mv, ed, nov = metrics(tr)
rec = recurrence(tr)
q = died(A, W_rd, True)
lam = lyapunov(A, W_rd, True)
print("  最大李雅普诺夫 λ  = %+.4f   %s" % (lam, "★边缘" if abs(lam) < 0.02 else ""))
print("  复发距离          = %.4f    (>0.15 = 不重复)" % rec)
print("  有效维            = %.1f" % ed)
print("  新奇度            = %.3f" % nov)
print("  运动量            = %.5f" % mv)
print("  断流即死          = %.5f  %s" % (q, "✅真死(消散)" if q < 0.02 else "❌死不了"))
