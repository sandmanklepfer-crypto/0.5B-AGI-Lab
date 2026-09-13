#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_quad.py — 四件套合体 (首次)
===================================
脑(自持核) + 纸带(读写闭环) + 桥(非线性+离散符号) + 内化(弱)

修正前几轮的三个缺口:
  缺口2: 纸带和桥从未接在一起  → 本版同时开
  缺口3: 桥用人造结构训        → 本版用【脑自己的真实轨迹】训 (在线)
  观测: 之前只跑120步          → 本版跑 100000 步

关键诊断「周期检测」:
  对不同时间间隔 gap, 量 "当前点到 gap 步前最近点" 的距离
  若在某 gap 处出现凹陷 → 存在该长度的周期
  ★ 小单元重复 (1 1 1 1)   → gap=1 就凹陷
  ★ 长段重复 (每天吃饭)     → 大 gap 凹陷, 但窗口内看不到
  ★ 真活 (永不重复)         → 全程无凹陷

对照:
  A 有限状态机: 脑 + 桥 + 内化, 无纸带
  B 图灵机:     脑 + 纸带 + 桥 + 内化  ← 四件套

全程检查: 断流即死 / 有效维 / 符号熵 / 自表达误差
"""
import numpy as np
import time

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H, K = 32, 16
EPS = 0.15                      # 内化强度 (验证过: <=0.2 保生命)
TOTAL = 100000
BLOCK = 5000                    # 每块: 模拟 + 在线训桥 + 度量
TRAIN_ITERS = 120
TRAIN_SAMPLES = 2000


def renorm(A, r=1.02):
    w = np.abs(np.linalg.eigvals(A)).max()
    return A * (r / max(w, 1e-9))


class Quad:
    """四件套: 脑 + 纸带 + 桥 + 内化"""

    def __init__(self, A, tape_on, seed=99, bridge_seed=1):
        r = np.random.RandomState(seed)
        self.A = A
        self.tape_on = tape_on
        self.W_rd = np.random.RandomState(7).randn(D, D) / np.sqrt(D)   # 纸带→脑
        self.w_head = np.random.RandomState(8).randn(D) / np.sqrt(D)    # 决定头移动
        self.W_in = np.random.RandomState(9).randn(D, K) / np.sqrt(K)   # 符号→脑(内化)
        self.x = r.randn(D, 1) * 0.5
        self.F = np.zeros_like(self.x)
        self.E = np.full((1, 1), 0.4)
        self.tape = [np.zeros((D, 1))]
        self.head = 0
        self.pmean = 0.0
        self.thr = 0.25
        self.n_fwd = 0; self.n_back = 0; self.n_stay = 0
        b = np.random.RandomState(bridge_seed)
        self.B = dict(W1=b.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
                      W2=b.randn(K, H) / np.sqrt(H), b2=np.zeros(K),
                      Wd=b.randn(D, K) / np.sqrt(K), bd=np.zeros(D))
        self.ms = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.vs = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.tstep = 0

    # ---------- 桥 ----------
    def enc(self, X):
        Hh = np.tanh(self.B['W1'] @ X + self.B['b1'][:, None])
        return self.B['W2'] @ Hh + self.B['b2'][:, None], Hh

    def softmax(self, z):
        z = z - z.max(0, keepdims=True)
        p = np.exp(z); return p / p.sum(0, keepdims=True)

    def train_bridge(self, Xall, iters=TRAIN_ITERS, lr=0.01):
        """在线训练: 梯度只到桥, 脑的 f 永不被触碰"""
        M = Xall.shape[1]
        for it in range(iters + 1):
            lg, Hh = self.enc(Xall)
            P = self.softmax(lg)
            Xd = self.B['Wd'] @ P + self.B['bd'][:, None]
            dX = 2.0 * (Xd - Xall) / M
            G = dict(Wd=dX @ P.T, bd=dX.sum(1))
            dP = self.B['Wd'].T @ dX
            dlg = P * (dP - (dP * P).sum(0, keepdims=True))
            G['W2'] = dlg @ Hh.T; G['b2'] = dlg.sum(1)
            dpre = (self.B['W2'].T @ dlg) * (1 - Hh ** 2)
            G['W1'] = dpre @ Xall.T; G['b1'] = dpre.sum(1)
            for k in self.B:
                self.ms[k] = 0.9 * self.ms[k] + 0.1 * G[k]
                self.vs[k] = 0.999 * self.vs[k] + 0.001 * (G[k] ** 2)
                self.B[k] -= lr * (self.ms[k] / (1 - 0.9 ** (it + 1))) / \
                             (np.sqrt(self.vs[k] / (1 - 0.999 ** (it + 1))) + 1e-8)

    def self_err(self, X):
        lg, _ = self.enc(X)
        idx = lg.argmax(0)
        S = np.zeros((K, X.shape[1])); S[idx, np.arange(X.shape[1])] = 1.0
        Xd = self.B['Wd'] @ S + self.B['bd'][:, None]
        return float(np.linalg.norm(Xd - X) / (np.linalg.norm(X) + 1e-9))

    # ---------- 一步 ----------
    def step(self, cut=False):
        # 桥读脑 → 符号 (嘴说话)
        lg, _ = self.enc(self.x)
        P = self.softmax(lg)
        sym = int(lg.argmax(0)[0])

        inj = None
        if EPS > 0:
            inj = EPS * (self.W_in @ P)              # 内化: 状态通道
        if self.tape_on:
            rd = self.W_rd @ SIG(self.tape[self.head])  # 纸带→脑
            inj = rd if inj is None else inj + rd

        act = SIG(self.x)
        self.F = np.clip(self.F + DT * RHO * (act ** 2 - self.F), 0, 2)
        g = self.E / (KAPPA + self.E)
        core = self.A @ act - MU * self.F * self.x
        if inj is not None:
            core = core + inj
        et = 0.0 if cut else ETA
        self.x = self.x + DT * (g * core - G0 * self.x)
        self.E = np.maximum(self.E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * self.E), 0.0)

        if self.tape_on:
            self.tape[self.head] = self.x.copy()          # 写
            # 头移动: 驱动必须【去直流】, 否则头单向前进, 读的永远是空格子
            proj = float(self.w_head @ self.x[:, 0])
            self.pmean = 0.995 * self.pmean + 0.005 * proj
            dd = proj - self.pmean                         # 去掉偏置 → 有正有负
            if dd > self.thr:
                self.head += 1; self.n_fwd += 1
            elif dd < -self.thr:
                self.head -= 1; self.n_back += 1
            else:
                self.n_stay += 1
            self.head = max(0, self.head)
            if self.head >= len(self.tape):
                self.tape.append(np.zeros((D, 1)))        # 无限纸带
        self.tstep += 1
        return sym


# ==================== 度量 ====================
def eff_dim_novel(tr):
    ns = tr[-2500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)), 0, None)
    ed = float((w.sum() ** 2) / max((w ** 2).sum(), 1e-12))
    sub = ns[::40]
    Dm = np.linalg.norm(sub[:, None, :] - sub[None, :, :], axis=2)
    i = np.arange(len(sub)); mask = np.abs(i[:, None] - i[None, :]) > 5
    nov = float(np.where(mask, Dm, np.inf).min(1).mean()) / (np.linalg.norm(sub, axis=1).mean() + 1e-9)
    return ed, nov


def gap_profile(tr, gaps=(1, 5, 50, 300, 1500, 8000, 30000)):
    """周期检测: 各时间间隔上的复发距离 (凹陷=该长度存在周期)"""
    scale = np.linalg.norm(tr - tr.mean(0), axis=1).mean() + 1e-9
    out = {}
    for ga in gaps:
        if ga >= len(tr):
            out[ga] = np.nan; continue
        a, b = tr[ga:], tr[:-ga]
        d = np.linalg.norm(a - b, axis=1)
        out[ga] = float(np.median(d)) / scale
    return out


# ==================== 主实验 ====================
rng = np.random.RandomState(0)
A = renorm(rng.randn(D, D))

print("=" * 104)
print("四件套合体 | 脑D=%d + 纸带 + 桥(%d符号) + 内化(eps=%.2f)" % (D, K, EPS))
print("跑 %d 步 | 每 %d 步一块: 模拟 + 用真实轨迹在线训桥 + 度量" % (TOTAL, BLOCK))
print("=" * 104)

for tape_on, name in [(False, "A 有限状态机 (无纸带)"), (True, "B 图灵机 (四件套)")]:
    t0 = time.time()
    q = Quad(A, tape_on, seed=99)
    traj = []
    sym_hist = []
    print("\n" + "-" * 104)
    print("[%s]" % name)
    print("-" * 104)
    print("  %-6s %-7s %-7s %-8s %-8s %-8s %-8s %-7s %s"
          % ("块", "符号", "熵", "最长连续", "有效维", "新奇", "自表达", "复发", "头前/后/停"))
    for bi in range(TOTAL // BLOCK):
        bstart = len(traj)
        for _ in range(BLOCK):
            q.step()
            traj.append(q.x[:, 0].copy())
        tr = np.array(traj)
        # 在线训桥: 用脑【自己的真实轨迹】(跨全历史等距采样, 只用过去)
        stride = max(1, len(tr) // TRAIN_SAMPLES)
        Xr = tr[::stride][:TRAIN_SAMPLES].T
        q.train_bridge(Xr)
        # 度量 (训练后重算本块符号 —— 这样每块都用当前桥)
        lg, _ = q.enc(tr[bstart:].T)
        block_syms = lg.argmax(0).tolist()
        # ★ 最长连续同符号 = "1 1 1 1" 检测器
        runlen = 1; mx_run = 1
        for a, b in zip(block_syms, block_syms[1:]):
            if a == b:
                runlen += 1; mx_run = max(mx_run, runlen)
            else:
                runlen = 1
        sym_hist.extend(block_syms)
        cnt = np.bincount(np.array(block_syms), minlength=K) / len(block_syms)
        ent = float(-(cnt[cnt > 0] * np.log(cnt[cnt > 0])).sum() / np.log(K))
        nuniq = int((cnt > 0.01).sum())
        ed, nov = eff_dim_novel(tr)
        se = q.self_err(tr[-800:].T)
        # 复发 (最近窗口, gap=300)
        win = tr[-6000:]
        rec = float(np.median(np.linalg.norm(win[300:] - win[:-300], axis=1))) / \
              (np.linalg.norm(win - win.mean(0), axis=1).mean() + 1e-9)
        hd = "%d/%d/%d" % (q.n_fwd, q.n_back, q.n_stay) if tape_on else "-"
        print("  %-6d %-7d %-7.3f %-8d %-8.1f %-8.3f %-8.4f %-7.3f %s"
              % (bi + 1, nuniq, ent, mx_run, ed, nov, se, rec, hd), flush=True)

    tr = np.array(traj)
    print("\n  ── 最终体检 (跑了 %d 步) ──" % TOTAL)
    ed, nov = eff_dim_novel(tr)
    print("  纸带长度 = %d 格   头位置 = %d" % (len(q.tape), q.head))
    print("  有效维 = %.1f   新奇度 = %.3f" % (ed, nov))

    print("\n  ── ★ 周期检测 (各时间间隔的复发距离, 凹陷=存在周期) ──")
    prof = gap_profile(tr)
    for ga, v in prof.items():
        if np.isnan(v):
            print("    gap=%-6d  超出窗口" % ga); continue
        bar = "█" * int(min(v, 1.0) * 45)
        tag = "❌ 周期在此" if v < 0.06 else ("弱" if v < 0.12 else "✅ 无重复")
        print("    gap=%-6d  %.4f %-46s %s" % (ga, v, bar, tag))
    vals = [v for v in prof.values() if not np.isnan(v)]
    print("    → 最小复发=%.4f  最大复发=%.4f  %s"
          % (min(vals), max(vals),
             "❌ 存在周期(死)" if min(vals) < 0.06 else "✅ 窗口内无周期(活)"))

    print("\n  ── 断流即死 (最后检验) ──")
    q2 = Quad(A, tape_on, seed=99)
    for _ in range(3000):
        q2.step()
    post = []
    for t in range(5000):
        q2.step(cut=(t >= 1200))
        if t >= 1200:
            post.append(np.linalg.norm(q2.x))
    print("    断流后 |x| = %.5f  %s" % (np.mean(post[-50:]),
          "✅ 真死(消散)" if np.mean(post[-50:]) < 0.02 else "❌ 死不了"))

    print("\n  ── 符号使用 (语言有没有'历史') ──")
    half = len(sym_hist) // 2
    u1 = len(set(sym_hist[:half])); u2 = len(set(sym_hist[half:]))
    print("    前半段用了 %d/%d 个符号   后半段用了 %d/%d 个" % (u1, K, u2, K))
    print("    %s" % ("✅ 语言在扩展/保持" if u2 >= u1 else "❌ 语言在塌缩"))
