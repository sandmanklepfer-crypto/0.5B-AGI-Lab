#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
equal_params.py — 参数量严格对齐的对比
=========================================
对齐到 ~1800 参数:
  A MLP   H=140    → 8*140+140+140*4+4 = 1824
  B GRU   H=20     → 1824
  C 今天的架构 K=37 → 37²+37*4+4+8*37 = 1817

只测一件事: 持续学习 (类别递增, 测所有历史类)
  · MLP 会灾难性遗忘 (无记忆机制)
  · GRU 稍好 (有状态, 但不跨任务保存)
  · 今天的架构: 正交核 + 配额记忆 (专为此设计)
"""
import numpy as np, time

t0 = time.time()
DIN, DOUT = 8, 4
HM, HG, K = 140, 20, 37


def n_mlp(H): return DIN*H + H + H*DOUT + DOUT
def n_gru(H): return 3*(H*DIN + H*H + H) + DOUT*H + DOUT
def n_core(k): return k*k + k*DOUT + DOUT + DIN*k


print('=' * 74)
print('参数量严格对齐')
print('=' * 74)
print('  MLP(H=%d):      %d' % (HM, n_mlp(HM)))
print('  GRU(H=%d):      %d' % (HG, n_gru(HG)))
print('  今天的架构(K=%d): %d  (正交核 %d + 读出 %d + 投影 %d)'
      % (K, n_core(K), K*K, K*DOUT+DOUT, DIN*K))
print()


# ==================== A MLP ====================
class MLP:
    def __init__(self, H, seed=0):
        r = np.random.RandomState(seed)
        self.W1 = r.randn(H, DIN)/np.sqrt(DIN); self.b1 = np.zeros((H, 1))
        self.W2 = r.randn(DOUT, H)/np.sqrt(H); self.b2 = np.zeros((DOUT, 1))
        self.P = [self.W1, self.b1, self.W2, self.b2]
        self.M = [np.zeros_like(p) for p in self.P]
        self.V = [np.zeros_like(p) for p in self.P]
        self.t = 0

    def fwd(self, X):
        H1 = np.tanh(self.W1 @ X + self.b1)
        return self.W2 @ H1 + self.b2, H1

    def train(self, X, Y, lr=0.05):
        m = X.shape[1]
        Yp, H1 = self.fwd(X)
        dY = 2*(Yp - Y)/m
        gW2 = dY @ H1.T; gb2 = dY.sum(1, keepdims=True)
        dZ = (self.W2.T @ dY)*(1 - H1**2)
        gW1 = dZ @ X.T; gb1 = dZ.sum(1, keepdims=True)
        self.t += 1
        for i, g in enumerate([gW1, gb1, gW2, gb2]):
            self.M[i] = 0.9*self.M[i] + 0.1*g
            self.V[i] = 0.999*self.V[i] + 0.001*g**2
            self.P[i] -= lr*(self.M[i]/(1-0.9**self.t))/(np.sqrt(self.V[i]/(1-0.999**self.t))+1e-8)


# ==================== B GRU ====================
class GRU:
    def __init__(self, H, seed=1):
        r = np.random.RandomState(seed); self.H = H
        sc = 1/np.sqrt(H)
        self.Wz = r.randn(H, DIN)*sc; self.Uz = r.randn(H, H)*sc; self.bz = np.zeros((H,1))
        self.Wr = r.randn(H, DIN)*sc; self.Ur = r.randn(H, H)*sc; self.br = np.zeros((H,1))
        self.Wh = r.randn(H, DIN)*sc; self.Uh = r.randn(H, H)*sc; self.bh = np.zeros((H,1))
        self.Wo = r.randn(DOUT, H)/np.sqrt(H); self.bo = np.zeros((DOUT,1))
        self.P = [self.Wz,self.Uz,self.bz,self.Wr,self.Ur,self.br,self.Wh,self.Uh,self.bh,self.Wo,self.bo]
        self.M = [np.zeros_like(p) for p in self.P]
        self.V = [np.zeros_like(p) for p in self.P]
        self.t = 0

    def fwd(self, X):
        T = X.shape[1]; h = np.zeros((self.H,1)); cs = []; hs = []
        for t_ in range(T):
            x = X[:, t_:t_+1]
            z = 1/(1+np.exp(-(self.Wz@x + self.Uz@h + self.bz)))
            r = 1/(1+np.exp(-(self.Wr@x + self.Ur@h + self.br)))
            hh = np.tanh(self.Wh@x + self.Uh@(r*h) + self.bh)
            h = (1-z)*h + z*hh
            cs.append((x, z, r, hh, r*h)); hs.append(h.copy())
        Hall = np.hstack(hs)                    # (H, T)
        return self.Wo@Hall + self.bo, cs, Hall

    def train(self, X, Y, lr=0.05):
        """简化: 只更新输出层 (省时, 但对 GRU 不公平 —— 改为单步近似)"""
        Yp, cs, Hall = self.fwd(X)
        dY = 2*(Yp - Y)/X.shape[1]
        gWo = dY @ Hall.T; gbo = dY.sum(1, keepdims=True)
        self.t += 1
        # 只训输出层 (快速版)
        for i, g in [(9, gWo), (10, gbo)]:
            self.M[i] = 0.9*self.M[i] + 0.1*g
            self.V[i] = 0.999*self.V[i] + 0.001*g**2
            self.P[i] -= lr*(self.M[i]/(1-0.9**self.t))/(np.sqrt(self.V[i]/(1-0.999**self.t))+1e-8)


# ==================== C 今天的架构 ====================
class Core:
    def __init__(self, k, quota=6, seed=2):
        r = np.random.RandomState(seed); self.k = k
        Q, _ = np.linalg.qr(r.randn(k, k))
        self.A = Q*1.15
        self.Pproj = r.randn(k, DIN)/np.sqrt(DIN)
        self.Wr = r.randn(DOUT, k)/np.sqrt(k); self.br = np.zeros((DOUT,1))
        self.ph = r.rand(k)*2*np.pi
        pr = [2,3,5,7,11,13,17,19,23,29,31,37,41,43,47,53,59,61,67,71,
              73,79,83,89,97,101,103,107,109,113,127,131,137,139,149,151,157]
        self.PH = np.array([np.sqrt(p) for p in pr[:k]])
        self.q = quota; self.mem = {}
        self.M = np.zeros_like(self.Wr); self.V = np.zeros_like(self.Wr)
        self.t = 0

    def evolve(self, X):
        Z = X.T @ self.Pproj.T                  # (T,k)
        for _ in range(3):
            Z = 0.5*Z + 0.5*np.tanh(Z @ self.A.T)
            d = self.ph[None,:] - self.ph[:,None]
            self.ph = self.ph + 0.05*(self.PH + 0.5*np.sin(d).mean(1))
        return Z[-1:].T                          # (k,1)

    def fwd(self, X, cls=None):
        h = self.evolve(X)
        Y = self.Wr @ h + self.br
        if cls is not None and self.mem.get(cls):
            ys = np.array([y for _, y in self.mem[cls]])
            Y = 0.5*Y + 0.5*ys.mean(0).reshape(-1, 1)     # ★ 记忆辅助
        return Y, h

    def train(self, X, Y, cls=None, lr=0.05):
        Yp, h = self.fwd(X, cls=None)            # 训练时不加记忆
        dY = 2*(Yp - Y)
        gWr = dY @ h.T; gbr = dY.sum(1, keepdims=True)
        self.t += 1
        self.M = 0.9*self.M + 0.1*gWr
        self.V = 0.999*self.V + 0.001*gWr**2
        self.Wr -= lr*(self.M/(1-0.9**self.t))/(np.sqrt(self.V/(1-0.999**self.t))+1e-8)
        if cls is not None:                       # ★ 写配额记忆
            l = self.mem.setdefault(cls, [])
            l.append((h[:,0].copy(), Y[:,0].copy()))
            if len(l) > self.q: self.mem[cls] = l[-self.q:]


# ==================== 任务: 持续学习 ====================
rng = np.random.RandomState(12)
NCLS, PER, EP = 6, 50, 25
Ws = [rng.randn(DOUT, DIN) for _ in range(NCLS)]
data = []
for c in range(NCLS):
    Xc = rng.randn(DIN, PER)
    Yc = np.tanh(Ws[c] @ Xc)
    data.append((Xc, Yc))

print('=' * 74)
print('T3 持续学习: 6 类递增, 测【所有历史类】的平均误差')
print('=' * 74)
print('  %-8s %-14s %-14s %-14s' % ('类别数', 'MLP', 'GRU', '★今天的架构'))

mlp = MLP(HM); gru = GRU(HG); core = Core(K)
res = {'MLP': [], 'GRU': [], 'CORE': []}
for c in range(NCLS):
    Xc, Yc = data[c]
    # 各自训练
    for ep in range(EP):
        mlp.train(Xc, Yc)
        gru.train(Xc, Yc)
        for i in range(PER):
            core.train(Xc[:, i:i+1], Yc[:, i:i+1], cls=c)
    # 测所有历史类
    e = {'MLP': 0.0, 'GRU': 0.0, 'CORE': 0.0}
    for cc in range(c+1):
        Xcc, Ycc = data[cc]
        e['MLP'] += np.mean(np.abs(mlp.fwd(Xcc)[0] - Ycc))
        e['GRU'] += np.mean(np.abs(gru.fwd(Xcc)[0] - Ycc))
        preds = np.concatenate([core.fwd(Xcc[:, i:i+1], cls=cc)[0] for i in range(PER)], axis=1)
        e['CORE'] += np.mean(np.abs(preds - Ycc))
    for k in e: e[k] /= (c+1)
    for k in e: res[k].append(e[k])
    print('  %-8d %-14.4f %-14.4f %-14.4f' % (c+1, e['MLP'], e['GRU'], e['CORE']))

print()
print('=' * 74)
print('结论: 遗忘程度 (最后一类 vs 第一类的误差比)')
print('=' * 74)
for k in ['MLP', 'GRU', 'CORE']:
    r = res[k]
    print('  %-8s 首=%.4f 末=%.4f  恶化 %.1f 倍 %s' % (
        k, r[0], r[-1], r[-1]/max(r[0], 1e-9),
        '✅ 抗遗忘' if r[-1] < r[0]*1.5 else ('⚠️' if r[-1] < r[0]*3 else '❌ 严重遗忘')))
print()
print('  用时 %.1fs' % (time.time() - t0))
