#!/usr/bin/env python3
"""
V104 最小验证: 权重张量化 vs 普通MLP — 在"二阶交互任务"上的能力/参数效率
(验证"0.5B×0.5B章程空间"是否有戏的最小实验, 不改0.5B, 单层小网络)

任务: d=12 输入, 只含5对随机二阶交互的目标
      y = sign( Σ_{(i,j)∈S} c_ij · x_i · x_j )
      → 线性模型原理上不可解 (需要特征对 x_i·x_j)
对比:
  A. Linear        (一阶权重)            → 预期 ~50% (解不了, 铁证任务需要二阶)
  B. MLP 12→64→1   (普通一阶权重+非线性) → 看它要多少参数才能硬凑出交互
  C. Tensor2       (权重是张量: y=xᵀBx)  → 天然含二阶章程空间, 预期高acc且参数少
报告: 各模型 参数量 / 训练后测试acc
若 C 明显胜 B(同参数量下), 则"张量化章程空间"有真价值 → 值得改造0.5B
"""
import numpy as np
import torch
import torch.nn as nn

torch.manual_seed(0); np.random.seed(0)

D = 12
N_PAIRS = 5
N_TRAIN, N_TEST = 2000, 4000

# ---- 任务数据: 随机选5对交互 ----
rng = np.random.RandomState(0)
pairs = []
while len(pairs) < N_PAIRS:
    i, j = rng.randint(D), rng.randint(D)
    if i != j and (i, j) not in pairs and (j, i) not in pairs:
        pairs.append((i, j))
coefs = rng.randn(N_PAIRS)

def gen_y(X):
    y = np.zeros(len(X))
    for k, (i, j) in enumerate(pairs):
        y += coefs[k] * X[:, i] * X[:, j]
    return np.sign(y).astype(np.float32)

Xtr = rng.randn(N_TRAIN, D).astype(np.float32)
Xte = rng.randn(N_TEST, D).astype(np.float32)
ytr = gen_y(Xtr); yte = gen_y(Xte)

# ---- 模型 ----
class Linear(nn.Module):
    def __init__(self):
        super().__init__(); self.fc = nn.Linear(D, 1)
    def forward(self, x): return self.fc(x).squeeze(-1)

class MLP(nn.Module):
    def __init__(self, h=64):
        super().__init__(); self.fc1 = nn.Linear(D, h); self.fc2 = nn.Linear(h, 1)
    def forward(self, x):
        return self.fc2(torch.tanh(self.fc1(x))).squeeze(-1)

class Tensor2(nn.Module):
    """二阶章程: y = xᵀBx + wᵀx + b  (B = 张量化权重, 天然含 d² 特征组合)"""
    def __init__(self):
        super().__init__()
        self.B = nn.Parameter(torch.randn(D, D) / np.sqrt(D))
        self.w = nn.Parameter(torch.randn(D) / np.sqrt(D))
        self.b = nn.Parameter(torch.zeros(1))
    def forward(self, x):
        bilin = (x @ self.B * x).sum(-1)     # xᵀBx (二阶章程项)
        return bilin + x @ self.w + self.b

def train_eval(model, name):
    opt = torch.optim.Adam(model.parameters(), lr=5e-3)
    lossf = nn.BCEWithLogitsLoss()
    Xt = torch.tensor(Xtr); yt = torch.tensor(ytr)
    Xe = torch.tensor(Xte); ye = torch.tensor(yte)
    for ep in range(800):
        opt.zero_grad()
        loss = lossf(model(Xt), yt)
        loss.backward(); opt.step()
        if ep % 200 == 0:
            with torch.no_grad():
                acc = ((model(Xe) > 0).float() == (ye > 0).float()).float().mean().item()
    with torch.no_grad():
        acc = ((model(Xe) > 0).float() == (ye > 0).float()).float().mean().item()
    nparam = sum(p.numel() for p in model.parameters())
    print('  %-10s 参数量=%5d  测试acc=%.3f' % (name, nparam, acc), flush=True)
    return acc

print('[V104] 二阶交互任务 (5对特征组合, 线性不可解) | d=%d train=%d test=%d' % (D, N_TRAIN, N_TEST), flush=True)
print('  真实交互对:', pairs, flush=True)
print('=== 训练 800 epochs ===', flush=True)
train_eval(Linear(), 'Linear')
train_eval(MLP(32), 'MLP(h=32)')
train_eval(MLP(128), 'MLP(h=128)')
train_eval(MLP(512), 'MLP(h=512)')
train_eval(Tensor2(), 'Tensor2')
print('\n[V104] 完成', flush=True)
