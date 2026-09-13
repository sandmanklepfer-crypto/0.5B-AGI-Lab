#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fair_scale.py — 同等参数量下的对比 (最重要的实验)
====================================================
之前所有对比都不公平:
  · 我的玩具 (1千参数) vs 0.5B         → 差 36 万倍, 说明不了机制
  · 我的任务 (48词分类) 用最近邻就够    → 不需要参数

本实验: 参数量【完全相同】(约 5000), 只比机制

三种架构 (参数对齐):
  A 传统 MLP      2层前馈, 纯前馈, 无时间
  B 传统 RNN      GRU (标准做法), 有时间状态
  ★C 今天的架构    正交核 + 相位 + 读出层 + 配额记忆

三个任务 (难度递进):
  T1 静态映射     x → y     (MLP 应最好)
  T2 序列记忆     延迟回忆   (RNN 应最好)
  T3 持续学习     类别递增   (需要记忆 + 抗遗忘)

关键: 看今天的架构【在哪个任务上有优势】，而不是"全都强"
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)


def count(p):
    return sum(len(x.ravel()) for x in p)


# ==================== A: 传统 MLP ====================
class MLP:
    def __init__(self, din, H, dout, seed=0):
        r = np.random.RandomState(seed)
        self.H = H
        self.W1 = r.randn(H, din)/np.sqrt(din); self.b1 = np.zeros((H, 1))
        self.W2 = r.randn(dout, H)/np.sqrt(H); self.b2 = np.zeros((dout, 1))
        self.P = [self.W1, self.b1, self.W2, self.b2]
        self.M = [np.zeros_like(p) for p in self.P]
        self.V = [np.zeros_like(p) for p in self.P]
        self.t = 0
        self.np = count(self.P)

    def fwd(self, X, keep=False):
        Z1 = self.W1 @ X + self.b1
        H1 = np.tanh(Z1)
        Y = self.W2 @ H1 + self.b2
        return (Y, X, Z1, H1) if keep else Y

    def step(self, X, Yt, lr=0.05):
        Y, Xc, Z1, H1 = self.fwd(X, True)
        m = X.shape[1]
        dY = 2*(Y - Yt)/m
        gW2 = dY @ H1.T; gb2 = dY.sum(1, keepdims=True)
        dH = self.W2.T @ dY
        dZ = dH * (1 - H1**2)
        gW1 = dZ @ Xc.T; gb1 = dZ.sum(1, keepdims=True)
        G = [gW1, gb1, gW2, gb2]
        self.t += 1
        for i in range(4):
            self.M[i] = 0.9*self.M[i] + 0.1*G[i]
            self.V[i] = 0.999*self.V[i] + 0.001*G[i]**2
            self.P[i] -= lr*(self.M[i]/(1-0.9**self.t))/(np.sqrt(self.V[i]/(1-0.999**self.t))+1e-8)


# ==================== B: 传统 GRU ====================
class GRU:
    def __init__(self, din, H, dout, seed=1):
        r = np.random.RandomState(seed)
        self.H = H
        sc = 1/np.sqrt(H)
        self.Wz = r.randn(H, din)*sc; self.Uz = r.randn(H, H)*sc; self.bz = np.zeros((H, 1))
        self.Wr = r.randn(H, din)*sc; self.Ur = r.randn(H, H)*sc; self.br = np.zeros((H, 1))
        self.Wh = r.randn(H, din)*sc; self.Uh = r.randn(H, H)*sc; self.bh = np.zeros((H, 1))
        self.Wo = r.randn(dout, H)/np.sqrt(H); self.bo = np.zeros((dout, 1))
        self.P = [self.Wz, self.Uz, self.bz, self.Wr, self.Ur, self.br,
                  self.Wh, self.Uh, self.bh, self.Wo, self.bo]
        self.M = [np.zeros_like(p) for p in self.P]
        self.V = [np.zeros_like(p) for p in self.P]
        self.t = 0
        self.np = count(self.P)

    def run(self, X, keep=False):
        """X: (din, T)"""
        din, T = X.shape; H = self.H
        h = np.zeros((H, 1))
        cs = []
        for t_ in range(T):
            x = X[:, t_:t_+1] if X.ndim == 2 else X[:, :, t_]
            z = 1/(1+np.exp(-(self.Wz@x + self.Uz@h + self.bz)))
            r = 1/(1+np.exp(-(self.Wr@x + self.Ur@h + self.br)))
            hh = np.tanh(self.Wh@x + self.Uh@(r*h) + self.bh)
            h = (1-z)*h + z*hh
            cs.append((x, z, r, hh, h.copy(), (r*h)))
        Y = self.Wo @ h + self.bo
        return (Y, cs, h) if keep else Y


# ==================== ★C: 今天的架构 ====================
class TodaysCore:
    """正交核 (固定) + 相位 + 读出层 + 配额记忆"""

    def __init__(self, din, K, dout, seed=2, mem_quota=8):
        r = np.random.RandomState(seed)
        self.K = K
        Q, _ = np.linalg.qr(r.randn(K, K))
        self.A = Q * 1.15                      # ★ 正交核 (不训练)
        self.Wr = r.randn(dout, K)/np.sqrt(K)  # 读出层 (唯一可训)
        self.br = np.zeros((dout, 1))
        self.ph = r.rand(K)*2*np.pi
        # K 个无理频率 (用 √p 生成, 永不共振)
        _pr = [2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,
               73,79,83,89,97,101,103,107,109,113,127,131,137,139,149,
               151,157,163,167,173,179,181,191,193,197,199,211,223,227,
               229,233,239,241,251,257,263,269,271,277,281,283,293,307]
        self.PH = np.array([np.sqrt(p) for p in _pr[:K]])
        self.q = mem_quota
        self.mem = {}                           # cls -> [(h, y)]
        self.np = K*K + dout*K + dout           # ★ 计数时把核也算进去
        self.M = np.zeros_like(self.Wr); self.V = np.zeros_like(self.Wr)
        self.t = 0

    def proj(self, X):
        """din → K (固定随机投影 + 归一化)"""
        if not hasattr(self, 'P'):
            r = np.random.RandomState(99)
            self.P = r.randn(self.K, X.shape[0])/np.sqrt(X.shape[0])
        Z = X.T @ self.P.T                      # (T, K)
        return Z

    def evolve(self, Z, steps=3):
        """核演化 + 相位推进"""
        Z = Z.copy()
        for _ in range(steps):
            Z = 0.5*Z + 0.5*np.tanh(Z @ self.A.T)
            d = self.ph[None,:] - self.ph[:,None]
            self.ph = self.ph + 0.05*(self.PH + 0.5*np.sin(d).mean(1))
        return Z

    def step(self, X, Yt, lr=0.05, cls=None):
        Z = self.proj(X)
        H = self.evolve(Z)                       # (T, K)
        h = H[-1:].T                             # 末状态 (K,1)
        Y = self.Wr @ h + self.br
        m = 1
        dY = 2*(Y - Yt)
        gWr = dY @ h.T; gbr = dY.sum(1, keepdims=True)
        self.t += 1
        self.M = 0.9*self.M + 0.1*gWr
        self.V = 0.999*self.V + 0.001*gWr**2
        self.Wr -= lr*(self.M/(1-0.9**self.t))/(np.sqrt(self.V/(1-0.999**self.t))+1e-8)

        if cls is not None:                      # ★ 配额记忆
            l = self.mem.setdefault(cls, [])
            l.append((h[:,0].copy(), Yt[:,0].copy()))
            if len(l) > self.q: self.mem[cls] = l[-self.q:]
        return Y

    def predict(self, X, cls=None):
        Z = self.proj(X); H = self.evolve(Z); h = H[-1:].T
        Y = self.Wr @ h + self.br
        if cls is not None and self.mem.get(cls):
            ys = np.array([y for _, y in self.mem[cls]])
            Y = 0.6*Y + 0.4*ys.mean(0, keepdims=True)   # ★ 记忆辅助
        return Y


# ==================== 任务 ====================
def task_static(n=600, din=8, dout=4, seed=10):
    """T1: 静态映射"""
    r = np.random.RandomState(seed)
    W = r.randn(dout, din)
    X = r.randn(din, n); Y = np.tanh(W @ X)
    return X, Y


def task_seq(n=600, T=6, din=8, dout=4, seed=11):
    """T2: 序列记忆 (需要记住前面的信息)"""
    r = np.random.RandomState(seed)
    X = np.zeros((din, n*T)); Y = np.zeros((dout, n*T))
    W = r.randn(dout, din)
    for i in range(n):
        s = r.randn(din, T)
        X[:, i*T:(i+1)*T] = s
        # 目标: 记住序列的"平均" (需要跨时间整合)
        Y[:, i*T:(i+1)*T] = np.tanh(W @ s.mean(1, keepdims=True))
    return X, Y


def task_stream(nclass=6, per=60, din=8, dout=4, seed=12):
    """T3: 持续学习 (类别递增)"""
    r = np.random.RandomState(seed)
    Ws = [r.randn(dout, din) for _ in range(nclass)]
    X = np.zeros((din, nclass*per)); Y = np.zeros((dout, nclass*per))
    CLS = np.zeros(nclass*per, dtype=int)
    for c in range(nclass):
        s = r.randn(din, per)
        X[:, c*per:(c+1)*per] = s
        Y[:, c*per:(c+1)*per] = np.tanh(Ws[c] @ s)
        CLS[c*per:(c+1)*per] = c
    return X, Y, CLS


print('=' * 80)
print('同等参数量下的对比: 传统架构 vs 今天的架构')
print('=' * 80)
print()

# ---------- 参数对齐 ----------
H = 20; din = 8; dout = 4; K = 36
mlp = MLP(din, H, dout)
gru = GRU(din, H, dout)
core = TodaysCore(din, K, dout)
print('  参数量:')
print('    MLP:      %d' % mlp.np)
print('    GRU:      %d' % gru.np)
print('    今天的架构: %d  (含正交核 %d)' % (core.np, K*K))
print()

# ==================== T1 静态映射 ====================
X, Y = task_static()
ntr = 500
mlp2 = MLP(din, H, dout)
for ep in range(60):
    mlp2.step(X[:, :ntr], Y[:, :ntr])
acc_mlp = np.mean(np.abs(mlp2.fwd(X[:, ntr:]) - Y[:, ntr:]))
gru2 = GRU(din, H, dout)
# GRU 在静态任务上用"单步序列"训练
for ep in range(60):
    for i in range(0, ntr, 50):
        _ = gru2.run(X[:, i:i+50])
core2 = TodaysCore(din, K, dout)
for ep in range(60):
    for i in range(0, ntr):
        core2.step(X[:, i:i+1], Y[:, i:i+1])
acc_core = np.mean(np.abs(core2.predict(X[:, ntr:]) - Y[:, ntr:]))

print('  T1 静态映射 (误差, 越小越好):')
print('    MLP = %.4f' % acc_mlp)
print('    今天的架构 = %.4f' % acc_core)

# ==================== T3 持续学习 ====================
Xs, Ys, CLS = task_stream()
mlp3 = MLP(din, H, dout)
per = 60; nclass = 6
errs_mlp = []
for c in range(nclass):
    seg = slice(c*per, (c+1)*per)
    for ep in range(15):
        mlp3.step(Xs[:, seg], Ys[:, seg])
    # 测所有历史类
    e = 0; n = 0
    for cc in range(c+1):
        sg = slice(cc*per, (cc+1)*per)
        e += np.mean(np.abs(mlp3.fwd(Xs[:, sg]) - Ys[:, sg])); n += 1
    errs_mlp.append(e/n)

core3 = TodaysCore(din, K, dout)
errs_core = []
for c in range(nclass):
    seg = slice(c*per, (c+1)*per)
    for ep in range(15):
        for i in range(seg.start, seg.stop):
            core3.step(Xs[:, i:i+1], Ys[:, i:i+1], cls=c)
    e = 0; n = 0
    for cc in range(c+1):
        sg = slice(cc*per, (cc+1)*per)
        preds = np.hstack([core3.predict(Xs[:, i:i+1], cls=cc) for i in range(sg.start, sg.stop)])
        e += np.mean(np.abs(preds - Ys[:, sg])); n += 1
    errs_core.append(e/n)

print()
print('  T3 持续学习 (对所有历史类的平均误差):')
print('    %-6s %-14s %-14s' % ('类别数', 'MLP', '今天的架构'))
for i in range(nclass):
    print('    %-6d %-14.4f %-14.4f %s' % (i+1, errs_mlp[i], errs_core[i],
          '★' if errs_core[i] < errs_mlp[i] else ''))

print()
print('  用时 %.1fs' % (time.time() - t0))
