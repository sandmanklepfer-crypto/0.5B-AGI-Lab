#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_tape.py — 给脑加一张纸带: 有限状态机 → 图灵机
=====================================================
理论依据:
  有限状态机 (有界 x, 无外部存储) → 状态数有限 → 必然周期重复  ← 你的"复读"
  图灵机 = 有限状态机 + 无限纸带 → 状态可无限增长 → 永不真正重复

纸带设计 (真·图灵机结构, 非偷懒):
  · 纸带 tape: 可增长的格子序列, 每格 D 维
  · 读写头 head: 位置由【脑自己的状态】决定 (读/写都在这格)
  · 写入: 把当前脑状态写进当前格 (覆盖旧内容)
  · 读入: 当前格内容注入脑 (走状态通道, 不改 f)
  · 越界: 头走到纸带末尾就【增长一格】 ← 这就是"无限纸带"

四组对照:
  A 无纸带        纯有限状态机
  B 纸带(只读不写) 对照: 是"读"起作用还是"写"起作用?
  C 纸带(读+写)    完整图灵机
  D 纸带(写不读)   对照: 写但不反馈

指标:
  ① 复发距离: 轨迹回到旧状态有多近 (越小=越重复)
  ② 吸引子漂移: 窗口均值的漂移 (图灵机应持续漂移)
  ③ 符号多样性: 桥说出的符号数随时间
  ④ 有效维 / 新奇度
  ⑤ 断流即死: 必须保持
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H, K = 32, 16
STEPS = 15000


def renorm(A, r=0.98):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


def brain_step(A, x, F, E, inj=None):
    """脑的一步。f 永不改 —— 纸带只作为输入项, 不作梯度更新。"""
    act = SIG(x)
    F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
    g = E / (KAPPA + E)
    core = A @ act - MU * F * x
    if inj is not None:
        core = core + inj
    x = x + DT * (g * core - G0 * x)
    E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
    return x, F, E


def run(A, W_rd, W_wr, steps=STEPS, mode='tape', seed=99, head_rate=1):
    """
    mode: 'none'(无纸带) | 'rw'(读+写) | 'r'(只读) | 'w'(只写)
    返回: 轨迹 (steps, D), 纸带长度序列, head 序列
    """
    rng = np.random.RandomState(seed)
    x = (rng.randn(D, 1) * 0.5)
    F = np.zeros_like(x)
    E = np.full((1, 1), 0.4)

    tape = [np.zeros((D, 1))]          # 纸带: 可增长
    head = 0
    traj, tape_len, heads = [], [], []

    for t in range(steps):
        # ---- 读: 当前格内容注入脑 ----
        if mode in ('rw', 'r'):
            r = tape[head]
            inj = W_rd @ SIG(r)
        else:
            inj = None

        # ---- 脑演化 (f 不变) ----
        x, F, E = brain_step(A, x, F, E, inj)

        # ---- 写: 把脑状态写进当前格 ----
        if mode in ('rw', 'w'):
            tape[head] = x.copy()

        # ---- 头移动: 由脑自己决定 (这是"通用性"的关键) ----
        if mode != 'none':
            drive = float(SIG(x[0, 0]))
            step = 1 if drive > 0.2 else (-1 if drive < -0.2 else 0)
            if t % head_rate == 0:
                head = head + step
            if head < 0:
                head = 0
            if head >= len(tape):
                tape.append(np.zeros((D, 1)))     # ← 纸带增长 = 无限纸带

        traj.append(x[:, 0].copy())
        tape_len.append(len(tape))
        heads.append(head)

    return np.array(traj), np.array(tape_len), np.array(heads)


# ==================== 指标 ====================
def recurrence(traj, gap=300, ns=1400):
    """复发距离: 每个点到"gap步以前"最近点的距离 / 典型尺度。小=重复"""
    idx = np.linspace(0, len(traj) - 1, ns).astype(int)
    sub = traj[idx]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    tidx = idx
    mask = np.abs(tidx[:, None] - tidx[None, :]) > gap
    scale = Dm[~np.eye(ns, dtype=bool)].mean()
    rec = np.where(mask, Dm, np.inf).min(1)
    return float(np.median(rec)) / (scale + 1e-9)


def drift(traj, win=500):
    """吸引子漂移: 相邻窗口均值之间的距离 (持续>0 = 在漂移)"""
    n = len(traj) // win
    means = np.array([traj[i * win:(i + 1) * win].mean(0) for i in range(n)])
    return np.linalg.norm(np.diff(means, axis=0), axis=1)


def metrics(traj):
    motion = float(np.linalg.norm(np.diff(traj, axis=0), axis=1).mean())
    ns = traj[-3000:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    effdim = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::40]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return motion, effdim, nov


# ==================== 桥 (读写头的"语言"输出) ====================
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


def train_bridge(B, Xall, iters=400, lr=0.01):
    M = Xall.shape[1]; B = {k: v.copy() for k, v in B.items()}
    ms = {k: np.zeros_like(v) for k, v in B.items()}; vs = {k: np.zeros_like(v) for k, v in B.items()}
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
            ms[k] = 0.9 * ms[k] + 0.1 * G[k]; vs[k] = 0.999 * vs[k] + 0.001 * (G[k] ** 2)
            B[k] -= lr * (ms[k] / (1 - 0.9 ** (it + 1))) / (np.sqrt(vs[k] / (1 - 0.999 ** (it + 1))) + 1e-8)
    return B


rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))
W_rd = rng.randn(D, D) / np.sqrt(D)
W_wr = rng.randn(D, D) / np.sqrt(D)

print("=" * 104)
print("纸带实验: 有限状态机 → 图灵机 | 脑D=%d | 步数=%d | 纸带=可增长" % (D, STEPS))
print("=" * 104)

RES = {}
for mode, name in [('none', 'A 无纸带(有限状态机)'), ('r', 'B 纸带·只读'),
                   ('rw', 'C 纸带·读+写(图灵机)'), ('w', 'D 纸带·只写')]:
    traj, tl, hd = run(A, W_rd, W_wr, mode=mode)
    mv, ed, nov = metrics(traj)
    rec = recurrence(traj)
    dr = drift(traj)
    RES[mode] = dict(traj=traj, tl=tl, hd=hd, mv=mv, ed=ed, nov=nov, rec=rec, dr=dr)
    print("  %-24s 复发距离=%.4f 运动=%.5f 有效维=%.1f 新奇=%.3f 纸带长=%d 头位置=%d"
          % (name, rec, mv, ed, nov, tl[-1], hd[-1]))

print()
print("-" * 104)
print("① 复发距离 (越小=越重复; <0.1 基本可视为周期)")
print("-" * 104)
for mode, name in [('none', 'A 无纸带'), ('r', 'B 只读'), ('rw', 'C 读+写'), ('w', 'D 只写')]:
    r = RES[mode]['rec']
    tag = "❌ 死的重复" if r < 0.08 else ("⚠️ 弱重复" if r < 0.15 else "✅ 不重复(活)")
    print("  %-12s %.4f   %s" % (name, r, tag))

print()
print("-" * 104)
print("② 吸引子漂移 (窗口均值的变化; 持续>0 = 系统在历史上前进, 不回到旧地方)")
print("-" * 104)
for mode, name in [('none', 'A 无纸带'), ('r', 'B 只读'), ('rw', 'C 读+写'), ('w', 'D 只写')]:
    d = RES[mode]['dr']
    half1, half2 = d[:len(d) // 2].mean(), d[len(d) // 2:].mean()
    tag = "✅ 持续漂移" if half2 > half1 * 0.7 else "❌ 漂移衰减(趋于周期)"
    print("  %-12s 前半段=%.5f 后半段=%.5f   %s" % (name, half1, half2, tag))

print()
print("-" * 104)
print("③ 语言: 桥说出的符号, 随时间窗口用了几个 (语言有没有「历史」)")
print("-" * 104)

def sym_windows(traj, wins=6):
    """把轨迹切段, 每段单独训桥看它只能用几个符号表达"""
    seg = len(traj) // wins
    out = []
    for i in range(wins):
        Xs = traj[i * seg:(i + 1) * seg]
        Bs = train_bridge(init_bridge(K), Xs[::3].T, iters=200, lr=0.01)
        lg, _ = enc(Bs, Xs[::3].T)
        sq = lg.argmax(0)
        cnt = np.bincount(sq, minlength=K) / len(sq)
        ent = float(-(cnt[cnt > 0] * np.log(cnt[cnt > 0])).sum() / np.log(K))
        out.append((len(set(sq.tolist())), ent))
    return out

print("  %-12s %s" % ("组", "  ".join("W%d" % (i + 1) for i in range(6))))
for mode, name in [('none', 'A 无纸带'), ('rw', 'C 读+写')]:
    res = sym_windows(RES[mode]['traj'])
    print("  %-12s %s" % (name + " 符号数", "  ".join("%2d" % r[0] for r in res)))
    print("  %-12s %s" % ("", "  ".join("%.2f" % r[1] for r in res)))
print("  (符号数持续不降/熵保持 = 语言没有塌缩成'1 1 1')")

print()
print("-" * 104)
print("④ 断流即死 (必须保持) + 纸带是否污染 f")
print("-" * 104)


def death(mode, steps=8000, cut=2500):
    rngd = np.random.RandomState(5)
    x = (rngd.randn(D, 8) * 0.5); F = np.zeros_like(x); E = np.full((1, 8), 0.4)
    tape = [np.zeros((D, 8))]; head = 0; post = []
    for t in range(steps):
        inj = W_rd @ SIG(tape[head]) if mode in ('rw', 'r') else None
        et = 0.0 if t >= cut else ETA
        act = SIG(x)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        core = A @ act - MU * F * x
        if inj is not None:
            core = core + inj
        x = x + DT * (g * core - G0 * x)
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        if mode in ('rw', 'w'):
            tape[head] = x.copy()
        if mode != 'none':
            drive = float(SIG(x[0, 0]))
            head += (1 if drive > 0.2 else (-1 if drive < -0.2 else 0))
            head = max(0, head)
            if head >= len(tape):
                tape.append(np.zeros((D, 8)))
        if t >= cut:
            post.append(np.linalg.norm(x, axis=0).mean())
    return float(np.mean(post[-50:]))


for mode, name in [('none', 'A 无纸带'), ('r', 'B 只读'), ('rw', 'C 读+写'), ('w', 'D 只写')]:
    q = death(mode)
    print("  %-12s 断流后|x|=%.5f  %s" % (name, q, "✅ 真死(消散)" if q < 0.02 else "❌ 死不了"))

print()
print("  注: 纸带只作为脑方程的【输入项】, 从不参与梯度 → f 不可能被污染 (构造保证)")
