#!/usr/bin/env python3
"""碎片绑定实验 v2 — 有潜结构的内容 (真实世界模拟)
真实内容不是随机: 由少量"潜因子"组合而成 (像语言由语义基元组合)
验证: 300个"由潜因子生成"的内容, 能否被极少碎片高精度绑定/补齐?
"""
import numpy as np

def main():
    rng = np.random.RandomState(0)
    N_CONTENT = 300
    D = 64
    N_TRUE_FACTOR = 8    # 真正的潜因子数 (生成内容的"真相")

    # 8个真实潜因子 (模拟世界的真实基元)
    true_factors = rng.randn(N_TRUE_FACTOR, D).astype(np.float32)
    true_factors /= np.linalg.norm(true_factors, axis=1, keepdims=True)
    # 300个内容 = 8因子的稀疏组合 (每个内容用2-3个因子按随机权重组合)
    contents = []
    for i in range(N_CONTENT):
        n_use = rng.randint(2, 4)
        facs = rng.choice(N_TRUE_FACTOR, n_use, replace=False)
        w = rng.rand(n_use).astype(np.float32) + 0.5
        c = (true_factors[facs].T @ w) / w.sum()
        contents.append(c)
    contents = np.array(contents).astype(np.float32)
    print(f'=== 碎片绑定 v2: {N_CONTENT}内容, 真潜因子={N_TRUE_FACTOR}, 维度{D} ===')

    for K in [1, 2, 4, 8, 16]:
        # K-means 碎片
        idx = rng.choice(N_CONTENT, K, replace=False)
        centers = contents[idx].copy()
        for _ in range(50):
            d2 = ((contents[:, None, :] - centers[None, :, :])**2).sum(-1)
            lab = d2.argmin(1)
            for k in range(K):
                m = contents[lab == k]
                if len(m):
                    centers[k] = m.mean(0)
        # 补齐: 碎片 + 少量残差方向
        d2 = ((contents[:, None, :] - centers[None, :, :])**2).sum(-1)
        lab = d2.argmin(1)
        # 纯碎片误差
        recon0 = centers[lab]
        err0 = np.linalg.norm(contents - recon0, axis=1).mean()
        # 残差SVD每内容存P维
        resid = contents - centers[lab]
        for P in [1, 2, 4]:
            U, S, Vt = np.linalg.svd(resid, full_matrices=False)
            reconP = centers[lab] + (resid @ Vt[:P].T) @ Vt[:P]
            errP = np.linalg.norm(contents - reconP, axis=1).mean()
        rel0 = err0 / np.linalg.norm(contents, axis=1).mean()
        relP = errP / np.linalg.norm(contents, axis=1).mean()
        print(f'K={K:2d}: 纯碎片相对误差={rel0:.3f} | +4维残差={relP:.3f} | 压缩率≈{(K*D+N_CONTENT*4)/(N_CONTENT*D)*100:.1f}%')

if __name__ == '__main__':
    main()
