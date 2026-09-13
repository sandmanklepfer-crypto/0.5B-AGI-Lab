#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_speak.py — 脑对接语言: 用「序列」而不是「单符号」
========================================================
上一轮的瓶颈(率失真权衡):
  K=32 单符号 = 5 bit,  9维脑状态需 ~27 bit  → 差5倍
  桥要么"说得多但失真"(1.29x), 要么"说得准但只剩一个词"(0.93x, 熵0.199)

核心洞察: 语言是【序列】不是单个符号
  窗口 W=8, K=32 → 8×5 = 40 bit ≥ 27 bit  → 够了

设计:
  脑(D=96, 24块) → 取窗口(每S步采一个) → 桥逐位置编码 → W个符号
  → 用这串符号重建整个窗口 (序列瓶颈)
  桥结构: 共享编码 + 因果卷积(给上下文) + 逐位置分类头

用序列能否同时拿到: 高熵(说得多) + 低失真(说得准)?

对照: 窗口长度 W = 1, 2, 4, 8, 16
指标: 自表达误差 / 相对基线 / 符号熵 / 每秒有效切换
"""
import numpy as np
import time

DT = 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
D, NB = 96, 24                # 脑: 96维, 24块
d = D // NB
H = 64                        # 桥隐层
K = 32                        # 符号数(词表)


# ==================== 脑 ====================
def make_brain(seed=0, scale=2.5):
    r = np.random.RandomState(seed)
    A = np.zeros((D, D))
    for b in range(NB):
        s = b * d; e = s + d
        sub = r.randn(d, d)
        w = np.abs(np.linalg.eigvals(sub)).max()
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
    return np.array(tr)                      # (T, D)


# ==================== 桥: 序列编码 ====================
class SeqBridge:
    """共享编码 + 因果卷积上下文 + 逐位置分类 + 序列解码"""

    def __init__(self, W, K, seed=1):
        r = np.random.RandomState(seed)
        self.W, self.K = W, K
        self.B = dict(
            W1=r.randn(H, D) / np.sqrt(D), b1=np.zeros(H),
            Wc=r.randn(H, H) / np.sqrt(H),         # 上下文(因果卷积核, 看向前一步)
            W2=r.randn(K, H) / np.sqrt(H), b2=np.zeros(K),
            Emb=r.randn(D, K) / np.sqrt(K),        # 每符号的嵌入
        )
        self.ms = {k: np.zeros_like(v) for k, v in self.B.items()}
        self.vs = {k: np.zeros_like(v) for k, v in self.B.items()}

    def forward(self, Xw):
        """Xw: (D, W*batch) 按窗口排列 → 返回 (logits, 各中间量)"""
        m = Xw.shape[1]
        Hh = np.tanh(self.B['W1'] @ Xw + self.B['b1'][:, None])     # (H, m)
        # 因果上下文: 每步读前一步的 h (在窗口内)
        Hc = Hh.copy()
        nwin = m // self.W
        for w in range(nwin):
            s = w * self.W
            for t in range(1, self.W):
                Hc[:, s + t] = Hh[:, s + t] + self.B['Wc'] @ Hh[:, s + t - 1]
        Hc = np.tanh(Hc)
        lg = self.B['W2'] @ Hc + self.B['b2'][:, None]              # (K, m)
        return lg, Hh, Hc

    def loss_grad(self, Xw):
        m = Xw.shape[1]
        lg, Hh, Hc = self.forward(Xw)
        # softmax (逐位置)
        z = lg - lg.max(0, keepdims=True)
        P = np.exp(z); P /= P.sum(0, keepdims=True)
        Xd = self.B['Emb'] @ P                                      # (D, m)
        diff = Xd - Xw
        L = float((diff ** 2).sum() / m)
        # 反传
        dX = 2.0 * diff / m                                         # (D,m)
        G = {}
        G['Emb'] = dX @ P.T                                         # (D,K)
        dP = self.B['Emb'].T @ dX                                   # (K,m)
        dlg = P * (dP - (dP * P).sum(0, keepdims=True))
        G['W2'] = dlg @ Hc.T; G['b2'] = dlg.sum(1)
        dHc = (self.B['W2'].T @ dlg) * (1 - Hc ** 2)                # (H,m)
        dHh = dHc.copy()
        G['Wc'] = np.zeros_like(self.B['Wc'])
        nwin = m // self.W
        for w in range(nwin):
            s = w * self.W
            for t in range(1, self.W):
                G['Wc'] += dHc[:, s + t] @ Hh[:, s + t - 1].T
                dHh[:, s + t - 1] += self.B['Wc'].T @ dHc[:, s + t]
        dpre = dHh * (1 - Hh ** 2)
        G['W1'] = dpre @ Xw.T; G['b1'] = dpre.sum(1)
        return L, G

    def train(self, Xw, iters=300, lr=0.01):
        for it in range(iters + 1):
            L, G = self.loss_grad(Xw)
            for k in self.B:
                self.ms[k] = 0.9 * self.ms[k] + 0.1 * G[k]
                self.vs[k] = 0.999 * self.vs[k] + 0.001 * (G[k] ** 2)
                self.B[k] -= lr * (self.ms[k] / (1 - 0.9 ** (it + 1))) / \
                             (np.sqrt(self.vs[k] / (1 - 0.999 ** (it + 1))) + 1e-8)
        return L

    def evaluate(self, Xw):
        m = Xw.shape[1]
        lg, _, _ = self.forward(Xw)
        z = lg - lg.max(0, keepdims=True); P = np.exp(z); P /= P.sum(0, keepdims=True)
        Xd = self.B['Emb'] @ P
        se = float(np.linalg.norm(Xd - Xw) / np.linalg.norm(Xw))
        base = float(np.linalg.norm(Xw - Xw.mean(1, keepdims=True)) / np.linalg.norm(Xw))
        idx = lg.argmax(0)
        # 符号熵 (逐位置)
        nwin = m // self.W
        Hs = []
        for t in range(self.W):
            c = np.bincount(idx[t::self.W], minlength=self.K) / max(nwin, 1)
            c = c[c > 0]
            Hs.append(float(-(c * np.log(c)).sum() / np.log(self.K)))
        return se, base, float(np.mean(Hs)), idx


def make_windows(tr, W, stride, count):
    """从脑轨迹取窗口: 每窗 W 个采样点(间隔 stride 步)"""
    n = len(tr)
    span = (W - 1) * stride + 1
    starts = np.linspace(0, n - span - 1, count).astype(int)
    out = []
    for s in starts:
        out.append(tr[s:s + span:stride])           # (W, D)
    # 顺序: w0t0,w0t1,...,w0tW-1, w1t0,...  → 转成 (D, W*count) 供桥使用
    return np.concatenate(out, 0).T                  # (D, W*count)


# ==================== 主实验 ====================
if __name__ == '__main__':
    A = make_brain()
    print("=" * 104)
    print("脑对接语言: 序列瓶颈 | 脑D=%d(%d块) 词表K=%d" % (D, NB, K))
    print("=" * 104)

    t0 = time.time()
    tr = run_brain(A, 60000)
    print("脑轨迹 %d 步, 用时 %.1fs" % (len(tr), time.time() - t0))

    # 采样步长: 脑的块周期 ~70 步 → 每 10 步采一次, 保证相邻样本有变化
    STRIDE = 10
    print("采样步长 = %d 步 (脑的块周期约70步, 这样相邻样本有真实变化)" % STRIDE)

    print()
    print("-" * 104)
    print("序列长度 W 的效果 (信息量 = W × log2(%d) = W × %.0f bit)" % (K, np.log2(K)))
    print("-" * 104)
    print("  %-6s %-10s %-10s %-9s %-9s %-9s %s"
          % ("W", "信息量bit", "自表达", "vs基线", "符号熵", "每符号变化率", "耗时"))

    results = {}
    for W in [1, 2, 4, 8, 16]:
        Xtr = make_windows(tr[:45000], W, STRIDE, 1500)
        Xte = make_windows(tr[45000:55000], W, STRIDE, 400)
        br = SeqBridge(W, K)
        tt = time.time()
        br.train(Xtr, iters=300, lr=0.01)
        se, base, ent, idx = br.evaluate(Xte)
        # 每符号变化率 (语言切换快不快)
        nwin = len(idx) // W
        changes = 0; tot = 0
        for w in range(nwin):
            s = idx[w * W:(w + 1) * W]
            changes += int((s[1:] != s[:-1]).sum()); tot += W - 1
        rate = changes / max(tot, 1)
        results[W] = (se, base, ent, rate)
        print("  %-6d %-10.0f %-10.4f %-9.2fx %-9.3f %-9.3f %.0fs"
              % (W, W * np.log2(K), se, se / base, ent, rate, time.time() - tt), flush=True)

    print()
    print("-" * 104)
    print("关键对比: 序列是否打破了「率失真权衡」")
    print("-" * 104)
    print("  上一轮(K=32 单符号): 要么 失真1.29x+熵0.51, 要么 失真0.93x+熵0.20  ← 二者不可兼得")
    print()
    print("  %-6s %-12s %-12s %s" % ("W", "自表达(失真)", "符号熵(信息)", "判定"))
    for W, (se, base, ent, rate) in results.items():
        good = se < base and ent > 0.5
        print("  %-6d %-12.4f %-12.3f %s"
              % (W, se, ent, "★ 兼得!" if good else ("失真达标" if se < base else "失真超标")))

    print()
    print("-" * 104)
    print("最优配置的「说出的话」(前 60 个符号)")
    print("-" * 104)
    bestW = min(results, key=lambda w: results[w][0] / results[w][1])
    br = SeqBridge(bestW, K)
    Xtr = make_windows(tr[:45000], bestW, STRIDE, 1500)
    br.train(Xtr, iters=300, lr=0.01)
    Xte = make_windows(tr[45000:55000], bestW, STRIDE, 40)
    _, _, _, idx = br.evaluate(Xte)
    seq = idx[:60]
    print("  W=%d, 序列:" % bestW)
    print("  " + " ".join("%X" % s for s in seq))
    print("  用了 %d/%d 个符号" % (len(set(seq.tolist())), K))

    # 断流即死复核
    print()
    print("-" * 104)
    print("断流即死复核")
    print("-" * 104)
    r = np.random.RandomState(5)
    x = r.randn(D, 8) * 0.5; F = np.zeros_like(x); E = np.full((1, 8), 0.4)
    post = []
    for t in range(8000):
        act = SIG(x)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        x = x + DT * (g * (A @ act - MU * F * x) - G0 * x)
        et = 0.0 if t >= 3000 else ETA
        E = np.maximum(E + DT * (et * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        if t >= 3000:
            post.append(float(np.linalg.norm(x, axis=0).mean()))
    q = float(np.mean(post[-50:]))
    print("  断流后 |x| = %.6f  %s" % (q, "✅ 真死(消散)" if q < 0.02 else "❌ 死不了"))
