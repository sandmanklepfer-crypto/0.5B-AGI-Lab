#!/usr/bin/env python3
"""32B 几何显影: 用全层 dump 输出 32B 激活几何完整画像
输入: dump 目录 (war_L*/peace_L*/mix_L*, [n_layers,n_embd] 每文件)
输出: 层敏感性 / 层间相似度 / 有效维度 / 主题分离 / 聚类纯度
"""
import sys, glob, struct
import numpy as np

D = sys.argv[1] if len(sys.argv) > 1 else '/root/autodl-tmp/align2/32b/rn'

def load_all(pat):
    rows = []
    for fp in sorted(glob.glob(f'{D}/{pat}')):
        with open(fp, 'rb') as f:
            nl, ne = struct.unpack('<2i', f.read(8))
            a = np.fromfile(f, dtype=np.float32).reshape(nl, ne)
            rows.append(a)
    return np.stack(rows)  # (N, nl, ne)

print('loading...')
W = load_all('war_L*.bin')     # (30, 64, 5120)
P = load_all('peace_L*.bin')   # (30, 64, 5120)
M = load_all('mix_L*.bin')     # (98, 64, 5120)
NL, NE = W.shape[1], W.shape[2]
print(f'war {W.shape} peace {P.shape} mix {M.shape}')

# ── 1. 每层激活范数 (语料均值) ──
w_norm = np.linalg.norm(W, axis=2).mean(0)   # (64,)
p_norm = np.linalg.norm(P, axis=2).mean(0)
m_norm = np.linalg.norm(M, axis=2).mean(0)
print('\n=== 1. 层激活范数 (mean±std over corpus) ===')
for l in range(0, NL, 8):
    print(f'  L{l:02d}: war {w_norm[l]:6.1f}  peace {p_norm[l]:6.1f}  mix {m_norm[l]:6.1f}')

# ── 2. 层敏感性: war vs peace 分离度 (每层) ──
print('\n=== 2. 层敏感性剖面 (war/peace 分离度, 判别比) ===')
sep = np.zeros(NL)
for l in range(NL):
    mu_w = W[:, l].mean(0); mu_p = P[:, l].mean(0)
    s_w = W[:, l].std(0).mean(); s_p = P[:, l].std(0).mean()
    sep[l] = np.linalg.norm(mu_w - mu_p) / (s_w + s_p + 1e-9)
top = np.argsort(sep)[::-1]
print('  最高分离层:', [(int(t), round(float(sep[t]), 2)) for t in top[:8]])
print('  最低分离层:', [(int(t), round(float(sep[t]), 2)) for t in top[-4:]])
print('  前1/4层(0-15):', round(float(sep[:16].mean()), 3), ' 中(16-47):', round(float(sep[16:48].mean()), 3), ' 后(48-63):', round(float(sep[48:].mean()), 3))

# ── 3. 层间相似度矩阵 (样本均值激活的 cos) ──
print('\n=== 3. 层间结构 (64x64 cos 矩阵) ===')
A = np.zeros((NL, NL))
mu = np.stack([W[:, l].mean(0) for l in range(NL)])   # (64, 5120)
for i in range(NL):
    for j in range(NL):
        A[i, j] = np.dot(mu[i], mu[j]) / (np.linalg.norm(mu[i]) * np.linalg.norm(mu[j]) + 1e-9)
np.save(f'{D}/geom_layer_cos.npy', A)
# 相邻层 cos 序列
adj = [A[i, i+1] for i in range(NL-1)]
print(f'  相邻层 cos: mean {np.mean(adj):.3f} min {np.min(adj):.3f}@{np.argmin(adj)} max {np.max(adj):.3f}@{np.argmax(adj)}')
print('  相邻层 cos 序列 (每4层):', [round(float(adj[i]), 3) for i in range(0, 63, 4)])
# 块结构: 前16 vs 后48 的平均块间 cos
print(f'  块间 cos: L0-15<->L16-31 {A[:16,16:32].mean():.3f}  L16-31<->L32-47 {A[16:32,32:48].mean():.3f}  L32-47<->L48-63 {A[32:48,48:].mean():.3f}')

# ── 4. 有效维度 (每层 SVD 谱) ──
print('\n=== 4. 有效维度 (激活矩阵 SVD 能量) ===')
for l in [0, 15, 31, 47, 63]:
    Xl = np.vstack([W[:, l], P[:, l], M[:, l]])   # (158, 5120)
    Xc = Xl - Xl.mean(0)
    sv = np.linalg.svd(Xc, compute_uv=False)
    e = sv ** 2
    print(f'  L{l:02d}: 能量保留 pca32={e[:32].sum()/e.sum()*100:.1f}% pca128={e[:128].sum()/e.sum()*100:.1f}% pca512={e[:512].sum()/e.sum()*100:.1f}%  (有效秩@90%={int(np.argmax(e.cumsum()/e.sum()>0.9))})')

# ── 5. 主题分离结构 (最高分离层投影) ──
print('\n=== 5. 主题聚类 (最高分离层, PCA 投影 + KMeans) ===')
l_top = top[0]
Xl = np.vstack([W[:, l_top], P[:, l_top], M[:, l_top]])
Xc = Xl - Xl.mean(0)
U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
proj = Xc @ Vt[:2].T   # 2D 投影
# 类内/类间距离
def pair_d(g):
    g = proj[g]
    d = np.linalg.norm(g[:, None, :] - g[None, :, :], axis=2)
    iu = np.triu_indices(len(g), 1)
    return d[iu]
dw = pair_d(range(30)); dp = pair_d(range(30, 60)); dm = pair_d(range(60, 158))
dwp = np.linalg.norm(proj[:30, None] - proj[30:60][None], axis=2).ravel()
print(f'  层{l_top}: 类内距离 war {dw.mean():.2f} peace {dp.mean():.2f} mix {dm.mean():.2f} | 类间 war<->peace {dwp.mean():.2f}')
print(f'  分离比 (类间/类内): war-peace {dwp.mean()/((dw.mean()+dp.mean())/2):.2f}')
np.save(f'{D}/geom_proj_top.npy', proj)
print('\n=== DONE: geom_layer_cos.npy + geom_proj_top.npy 已保存 ===')
