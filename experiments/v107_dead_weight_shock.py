#!/usr/bin/env python3
"""
V107 最小验证: 活权重冲击冻结死权重 (方案3: 激活冲击冲开 → 通道写活)
模拟:
  死权重 D = 训练在任务A(线性)后冻结的 MLP  → 对应预训练0.5B(死)
  任务B    = 二阶交互任务(死权重结构解不了) → 对应"需要0.5B×0.5B章程空间的难题"
  活权重   = 自组织张量空间: 滚动产生巨大高维激活(含x, x², x_i*x_j交叉)
           → 灌入死权重隐藏层 (激活冲击, 冲开死结构)
  写活     = 沿冲击激活通道, anti-Hebbian 干净写 D 的隐藏层
判据:
  B_acc: 冲击+写活后 死权重能否解B (从~50%→高)
  A_acc: 原任务A几乎不崩 (几乎无损挤压)
"""
import numpy as np
import torch
import torch.nn as nn

torch.manual_seed(0); np.random.seed(0)
DIN, DH = 8, 32
NA, NB = 1500, 3000

# ---------- 数据 ----------
# 任务A: 线性 (第1维符号)
XA = np.random.randn(NA, DIN).astype(np.float32); yA = np.sign(XA[:, 0]).astype(np.float32)
# 任务B: 二阶交互 (线性解不了)
rng = np.random.RandomState(1)
pairs = [(0, 1), (2, 3), (4, 5), (6, 7), (1, 7)]
coefs = rng.randn(len(pairs))
XB = rng.randn(NB, DIN).astype(np.float32)
yB = np.zeros(NB)
for k, (i, j) in enumerate(pairs): yB += coefs[k] * XB[:, i] * XB[:, j]
yB = np.sign(yB).astype(np.float32)
XAt = torch.tensor(XA); yAt = torch.tensor(yA)
XBt = torch.tensor(XB); yBt = torch.tensor(yB)

# ---------- 死权重 (先训A, 冻结) ----------
class DeadMLP(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(DIN, DH)
        self.fc2 = nn.Linear(DH, 1)
    def forward(self, x):
        h = torch.tanh(self.fc1(x))
        return self.fc2(h).squeeze(-1), h

D = DeadMLP()
opt = torch.optim.Adam(D.parameters(), lr=5e-3)
lossf = nn.BCEWithLogitsLoss()
for _ in range(1200):
    opt.zero_grad(); out, _ = D(XAt); loss = lossf(out, (yAt > 0).float()); loss.backward(); opt.step()
with torch.no_grad():
    A0 = ((D(XAt)[0] > 0).float() == (yAt > 0).float()).float().mean().item()
    B0 = ((D(XBt)[0] > 0).float() == (yBt > 0).float()).float().mean().item()
print('[V107] 死权重: 任务A acc=%.3f (训好) | 任务B acc=%.3f (结构解不了)' % (A0, B0), flush=True)
W1_0 = D.fc1.weight.data.clone()   # 冻结基准

# ---------- 冻结死权重 ----------
for p in D.parameters(): p.requires_grad = False

# ---------- 活权重: 自组织张量冲击 (随机但固定的大高维映射, 含二阶) ----------
# 冲击空间: h(32) -> 巨大张量激活(500): 含h, h², 随机交叉对 → "0.5B×0.5B章程"的玩具版
R_lin  = torch.tensor(rng.randn(500, DH) / np.sqrt(DH), dtype=torch.float32)
R_pair = torch.tensor(rng.randn(500, 16) / 4, dtype=torch.float32)  # 16对候选交叉
PAIRIDX = [(i % DH, (i * 7 + 3) % DH) for i in range(16)]

def shock(h):
    """巨大张量冲击: 从隐藏态生成500维高阶特征 (活权重自组织产物)"""
    h = h.float()
    h2 = h * h
    cross = torch.stack([h[:, i] * h[:, j] for i, j in PAIRIDX], -1)   # (B,16)
    return torch.cat([h @ R_lin.T, h2 @ R_lin[:500].T * 0.3, cross @ R_pair.T], -1)  # (B,1500) 叠加宽

# ---------- 1) 激活冲击: 只注入运行状态, 不改权重 ----------
def forward_with_shock(model, x, alpha=0.6):
    """前向时在隐藏层后注入活权重的巨大激活(投影回32维), 冲开死结构的运行状态"""
    h1 = torch.tanh(model.fc1(x))
    S = shock(h1)                                    # 巨大张量空间 (B,1500)
    h1s = h1 + alpha * torch.tanh(S @ shock_proj * 0.1)   # 冲击回流(投影回32维, 小步)
    return model.fc2(h1s).squeeze(-1), h1s

rng2 = np.random.RandomState(2)
shock_proj = torch.tensor(rng2.randn(1500, DH) / np.sqrt(1500), dtype=torch.float32)  # (1500,32)
with torch.no_grad():
    B_shock = ((forward_with_shock(D, XBt)[0] > 0).float() == (yBt > 0).float()).float().mean().item()
print('  纯激活冲击(不改权重) 任务B acc=%.3f (看运行状态是否被冲开)' % B_shock, flush=True)

# ---------- 2) 沿通道写活: anti-Hebbian 把B结构干净写进死权重 ----------
# 让死权重(冻结解除fc1)沿"冲击通道"学B, 但只做小步干净写(不动任务A方向)
for p in D.parameters(): p.requires_grad = True
# 训练时用冲击前向 → 梯度只沿"冲击激活"方向改 fc1 (anti-Hebbian式: 幅度小, 沿新通道)
opt2 = torch.optim.SGD(D.fc1.parameters(), lr=0.05, momentum=0.9)
# 关键: fc2 保持冻结(任务A输出头不动), 只调 fc1 且加 L2 拉住不飘远 (受控写活)
prev = None
for ep in range(150):
    opt2.zero_grad()
    out, h = forward_with_shock(D, XBt)
    loss = lossf(out, (yBt > 0).float())
    # L2 拉住: 不许离开死权重太远 (几乎无损挤压 = 允许小偏移, 不许重构)
    reg = 0.05 * ((D.fc1.weight.data - W1_0) ** 2).sum()
    (loss + reg).backward()
    opt2.step()
with torch.no_grad():
    B_fin = ((D(XBt)[0] > 0).float() == (yBt > 0).float()).float().mean().item()
    A_fin = ((D(XAt)[0] > 0).float() == (yAt > 0).float()).float().mean().item()
drift = (D.fc1.weight.data - W1_0).norm().item() / W1_0.norm().item()
print('  冲击+写活后: 任务B acc=%.3f (应↑) | 任务A acc=%.3f (应≈%.3f 不崩) | fc1漂移=%.3f' % (B_fin, A_fin, A0, drift), flush=True)

# ---------- 对照: 不冲击直接写活 (看冲击是不是必须的) ----------
D2 = DeadMLP()
opt = torch.optim.Adam(D2.parameters(), lr=5e-3)
for _ in range(1200):
    opt.zero_grad(); out, _ = D2(XAt); loss = lossf(out, (yAt > 0).float()); loss.backward(); opt.step()
opt3 = torch.optim.SGD(D2.fc1.parameters(), lr=0.05, momentum=0.9)
W1_02 = D2.fc1.weight.data.clone()
for ep in range(150):
    opt3.zero_grad()
    out, h = D2(XBt)
    loss = lossf(out, (yBt > 0).float())
    reg = 0.05 * ((D2.fc1.weight.data - W1_02) ** 2).sum()
    (loss + reg).backward()
    opt3.step()
with torch.no_grad():
    B_noshock = ((D2(XBt)[0] > 0).float() == (yBt > 0).float()).float().mean().item()
    A_noshock = ((D2(XAt)[0] > 0).float() == (yAt > 0).float()).float().mean().item()
print('  对照(无冲击直接写活): 任务B acc=%.3f | 任务A acc=%.3f' % (B_noshock, A_noshock), flush=True)
print('\n[V107] 结论: 若 冲击+写活 的B显著高于 无冲击写活 → "活权重冲击是必要且有效的"', flush=True)
