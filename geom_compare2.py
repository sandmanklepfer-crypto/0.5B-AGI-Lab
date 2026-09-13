#!/usr/bin/env python3
"""跨尺寸几何对比 v2: 自动探测目录内所有 *_L*.bin (按前缀分组)
用法: geom_compare2.py <dump_dir> <tag>
输出: 层间cos / 有效维度 / 范数剖面 / 层敏感性(若 war+peace 存在)
"""
import sys, glob, struct, os
import numpy as np

D = sys.argv[1]
TAG = sys.argv[2] if len(sys.argv) > 2 else 'model'
FILTER = sys.argv[3] if len(sys.argv) > 3 else ''

files = sorted(glob.glob(f'{D}/{FILTER}*_L*.bin'))
if not files:
    print('no L*.bin found'); sys.exit(1)

# 前缀分组
groups = {}
for fp in files:
    base = os.path.basename(fp)
    pref = base.split('_L')[0]
    groups.setdefault(pref, []).append(fp)

print(f'[{TAG}] dir={D}')
print(f'  组: { {k: len(v) for k, v in groups.items()} }')

# 加载全部
allrows = []
for fp in files:
    with open(fp, 'rb') as f:
        nl, ne = struct.unpack('<2i', f.read(8))
        allrows.append(np.fromfile(f, dtype=np.float32).reshape(nl, ne))
X = np.stack(allrows)  # (N, nl, ne)
NL, NE = X.shape[1], X.shape[2]
print(f'  {X.shape[0]}样本 × {NL}层 × {NE}维')

# ── 1. 层间 cos (均值激活) ──
mu = X.mean(0)  # (NL, NE)
An = np.linalg.norm(mu, axis=1, keepdims=True)
A = (mu @ mu.T) / (An @ An.T + 1e-9)
adj = np.array([A[i, i+1] for i in range(NL-1)])
off = A[np.triu_indices(NL, 1)]
print(f'  [层间cos] 相邻: mean {adj.mean():+.3f} min {adj.min():+.3f}@{np.argmin(adj)} max {adj.max():+.3f}@{np.argmax(adj)}')
print(f'  [层间cos] 非对角: mean {off.mean():+.3f} |abs|mean {np.abs(off).mean():.3f} |abs|max {np.abs(off).max():.3f}')
step = max(1, NL//8)
print(f'  相邻cos序列: {[round(float(adj[i]),3) for i in range(0, NL-1, step)]}')
np.save(f'{D}/cmp_{TAG}_cos.npy', A)

# ── 2. 有效维度剖面 ──
eff = np.zeros(NL, dtype=int)
for l in range(NL):
    Xc = X[:, l] - X[:, l].mean(0)
    sv = np.linalg.svd(Xc, compute_uv=False)
    e = sv**2
    eff[l] = int(np.argmax(e.cumsum()/e.sum() > 0.9)) + 1
print(f'  [有效维@90%] L0={eff[0]} mid={eff[NL//2]} last={eff[-1]} | mean={eff.mean():.0f} min={eff.min()}@{np.argmin(eff)} max={eff.max()}@{np.argmax(eff)}')
print(f'  序列: {[int(eff[i]) for i in range(0, NL, step)]}')
print(f'  相对维度(有效/全维): L0 {eff[0]/NE:.3f} mid {eff[NL//2]/NE:.3f} last {eff[-1]/NE:.3f}')

# ── 3. 范数剖面 ──
norms = np.linalg.norm(X, axis=2).mean(0)
print(f'  [范数] L0={norms[0]:.1f} mid={norms[NL//2]:.1f} last={norms[-1]:.1f} | mean={norms.mean():.1f} max={norms.max():.1f}@{np.argmax(norms)}')

# ── 4. 层敏感性 (若 war+peace 组存在) ──
if 'war' in groups and 'peace' in groups:
    sep = np.zeros(NL)
    for l in range(NL):
        gw = [groups['war'], groups['peace']]
        rows = []
        for gname in ['war', 'peace']:
            for fp in groups[gname]:
                with open(fp, 'rb') as f:
                    nl2, ne2 = struct.unpack('<2i', f.read(8))
                    f.seek(8 + l*ne2*4)
                    rows.append(np.fromfile(f, dtype=np.float32, count=ne2))
        rows = np.array(rows)
        nw = len(groups['war'])
        mu_w = rows[:nw].mean(0); mu_p = rows[nw:].mean(0)
        s_w = rows[:nw].std(0).mean(); s_p = rows[nw:].std(0).mean()
        sep[l] = np.linalg.norm(mu_w - mu_p) / (s_w + s_p + 1e-9)
    top = np.argsort(sep)[::-1]
    print(f'  [敏感] top5: {[(int(t), round(float(sep[t]),1)) for t in top[:5]]} bottom: {[(int(t), round(float(sep[t]),1)) for t in top[-2:]]}')
    print(f'  [敏感] 前1/4 {sep[:NL//4].mean():.1f} | 中 {sep[NL//4:3*NL//4].mean():.1f} | 后1/4 {sep[3*NL//4:].mean():.1f}')
