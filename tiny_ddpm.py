#!/usr/bin/env python3
"""tiny DDPM: 8x8 手写数字扩散生成 (MNIST-like, 从噪声扩散出数字)
- 数据: sklearn load_digits (8x8, 1797张)
- 模型: 简单MLP去噪网络 (~40K参数) — 0.5B的零头
- 训练: 手机CPU 几分钟 (200 epochs 演示)
"""
import numpy as np
import torch
import torch.nn as nn
import time

torch.manual_seed(42)
np.random.seed(42)

# ── 数据: 8x8 手写数字 ──
from sklearn.datasets import load_digits
digits = load_digits()
X = digits.images.astype(np.float32) / 16.0   # 0~1
y = digits.target
print(f"数据: {X.shape} ({len(set(y))}类数字)")

# 只用 3 和 7 简化 (好训练, 好展示语义)
mask = (y == 3) | (y == 7)
X = X[mask]; y = y[mask]
print(f"筛选后(3和7): {X.shape}")

# ── DDPM 超参 (极小版) ──
T = 50              # 扩散步数
beta = np.linspace(1e-4, 0.02, T)
alpha = 1.0 - beta
alpha_bar = np.cumprod(alpha)
alpha_bar_t = torch.tensor(alpha_bar, dtype=torch.float32)
sqrt_abar = torch.sqrt(alpha_bar_t)
sqrt_omab = torch.sqrt(1 - alpha_bar_t)

def q_sample(x0, t, noise):
    """前向: 加噪 (热核扩散!)"""
    ab = alpha_bar_t[t].view(-1, 1)
    return torch.sqrt(ab) * x0 + torch.sqrt(1 - ab) * noise  # ab:(B,1)

# ── 去噪网络: MLP (8x8=64维输入) ──
class Denoiser(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(64 + 1, 256), nn.SiLU(),
            nn.Linear(256, 256), nn.SiLU(),
            nn.Linear(256, 64),
        )
    def forward(self, x, t):
        # x: (B,64), t: (B,1) 时间嵌入
        xt = torch.cat([x, t], dim=1)
        return self.net(xt)

model = Denoiser()
n_params = sum(p.numel() for p in model.parameters())
print(f"去噪网络参数: {n_params:,} (0.5B的 {n_params/5e8*100:.4f}%)")
opt = torch.optim.Adam(model.parameters(), lr=2e-3)
lossf = nn.MSELoss()

# ── 训练 ──
Xall = torch.tensor(X.reshape(-1, 64), dtype=torch.float32)
B = 64
EPOCHS = 300
t0 = time.time()
for ep in range(EPOCHS):
    idx = torch.randperm(len(Xall))[:B]
    x0 = Xall[idx]
    t_idx = torch.randint(0, T, (B, 1))
    t = t_idx.float() / T   # 归一化时间
    noise = torch.randn_like(x0)
    x_noisy = q_sample(x0, t_idx, noise)
    pred = model(x_noisy, t)
    loss = lossf(pred, noise)
    opt.zero_grad(); loss.backward(); opt.step()
    if ep % 50 == 0 or ep == EPOCHS-1:
        print(f"ep {ep:3d} loss={loss.item():.4f} ({time.time()-t0:.0f}s)")

# ── 采样: 从噪声扩散出数字 (逆热核!) ──
def sample(n=4):
    model.eval()
    x = torch.randn(n, 64)
    with torch.no_grad():
        for t in range(T-1, -1, -1):
            tt = torch.full((n,1), t/T)
            noise_pred = model(x, tt)
            ab = alpha_bar_t[t].item()
            a = alpha[t]; b = beta[t]
            x = (x - (1-a)/np.sqrt(1-ab) * noise_pred) / np.sqrt(a)
            if t > 0:
                x += np.sqrt(b) * torch.randn_like(x)
    return x.clamp(0, 1).reshape(n, 8, 8)

# ── 生成 + 保存 ──
import os
os.makedirs('/workspace/ddpm_out', exist_ok=True)
samples = sample(6)
for i in range(6):
    img = (samples[i].numpy() * 255).astype(np.uint8)
    from PIL import Image
    Image.fromarray(img, 'L').resize((64,64), Image.NEAREST).save(f'/workspace/ddpm_out/gen_{i}.png')
    # ASCII art 版 (给0.5B读的文本表示)
    ascii_chars = " .:-=+*#%@"
    s = samples[i].numpy()
    rows = []
    for r in range(8):
        rows.append(''.join(ascii_chars[int(s[r][c]*9)] for c in range(8)))
    open(f'/workspace/ddpm_out/gen_{i}.txt','w').write('\n'.join(rows))
    print(f"生成 {i}: saved png + ascii")
    for line in rows: print(f"   {line}")

# 大图拼版
imgs = [Image.open(f'/workspace/ddpm_out/gen_{i}.png') for i in range(6)]
W2, H2 = 64, 64
canvas = Image.new('L', (W2*6+20, H2+10), 255)
for i, im in enumerate(imgs):
    canvas.paste(im, (10+i*W2, 5))
canvas.save('/workspace/ddpm_out/all_6.png')
print(f"\n完成: /workspace/ddpm_out/ (png + ascii txt + all_6.png)")
