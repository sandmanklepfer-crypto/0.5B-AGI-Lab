#!/usr/bin/env python3
"""跨尺寸几何对比: 任意 dump 目录 → 层间cos/有效维度/层敏感性/激活结构
用法: geom_compare.py <dump_dir> <tag>
"""
import sys, glob, struct
import numpy as np

D = sys.argv[1]
TAG = sys.argv[2] if len(sys.argv) > 2 else 'model'

def load_all(pat):
    rows = []
    for fp in sorted(glob.glob(f'{D}/{pat}')):
        with open(fp, 'rb') as f:
            nl, ne = struct.unpack('<2i', f.read(8))
            a = np.fromfile(f, dtype=np.float32).reshape(nl, ne)
            rows.append(a)
    return np.stack(rows)

W = load_all('war_L*.bin')
P = load_all('peace_L*.bin')
M = load_all('mix_L*.bin')
NL, NE = W.shape[1], W.shape[2]
print(f'[{TAG}] layers={NL} embd={NE}  war={W.shape[0]} peace={P.shape[0]} mix={M.shape[0]}')

# ── 层间 cos (样本均值激活) ──
mu = np.stack([W[:, l].mean(0) for l in range(NL)])
A = np.zeros((NL, NL))
for i in range(NL):
    for j in range(NL):
        A[i, j] = np.dot(mu[i], mu[j]) / (np.linalg.norm(mu[i]) * np.linalg.norm(mu[j]) + 1e-9)
adj = [A[i, i+1] for i in range(NL-1)]
print(f'  [层间] 相邻层cos: mean {np.mean(adj):+.3f} min {np.min(adj):+.3f} max {np.max(adj):+.3f}')
print(f'  [层间] 全部非对角cos: mean {np.mean(A[np.triu_indices(NL,1)]):+.3f} |abs|mean {np.mean(np.abs(A[np.triu_indices(NL,1)])):.3f}')
# 相邻层 cos 剖面 (每 NL/8 取一点)
step = max(1, NL//8)
print('  相邻cos序列:', [round(float(adj[i]), 3) for i in range(0, NL-1, step)])
np.save(f'{D}/geom_{TAG}_cos.npy', A)

# ── 有效维度剖面 (每层激活 SVD 90%能量) ──
eff = []
for l in range(NL):
    Xl = np.vstack([W[:, l], P[:, l], M[:, l]])
    Xc = Xl - Xl.mean(0)
    sv = np.linalg.svd(Xc, compute_uv=False)
    e = sv**2
    k90 = int(np.argmax(e.cumsum()/e.sum() > 0.9)) + 1
    eff.append(k90)
eff = np.array(eff)
print(f'  [有效维] L0={eff[0]} Lmid={eff[NL//2]} Llast={eff[-1]}  mean={eff.mean():.0f} min={eff.min()}@{np.argmin(eff)} max={eff.max()}@{np.argmax(eff)}')
print(f'  有效维序列(每{step}层):', [int(eff[i]) for i in range(0, NL, step)])

# ── 层敏感性 (war/peace 判别比) ──
sep = np.zeros(NL)
for l in range(NL):
    mu_w = W[:, l].mean(0); mu_p = P[:, l].mean(0)
    s_w = W[:, l].std(0).mean(); s_p = P[:, l].std(0).mean()
    sep[l] = np.linalg.norm(mu_w - mu_p) / (s_w + s_p + 1e-9)
top = np.argsort(sep)[::-1]
print(f'  [敏感] top5层: {[(int(t), round(float(sep[t]),1)) for t in top[:5]]}  bottom2: {[(int(t), round(float(sep[t]),1)) for t in top[-2:]]}')
print(f'  [敏感] 前1/4 mean {sep[:NL//4].mean():.1f} 中半 mean {sep[NL//4:3*NL//4].mean():.1f} 后1/4 mean {sep[3*NL//4:].mean():.1f}')

# ── 激活范数剖面 ──
norms = np.linalg.norm(W, axis=2).mean(0)
print(f'  [范数] L0={norms[0]:.1f} Lmid={norms[NL//2]:.1f} Llast={norms[-1]:.1f}  mean={norms.mean():.1f} max={norms.max():.1f}@{np.argmax(norms)}')
