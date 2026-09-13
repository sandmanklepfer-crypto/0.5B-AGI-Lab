#!/usr/bin/env python3
"""碎片绑定压缩实验 — 300个内容能被几个碎片状态绑定补齐?
验证: 内容 = 碎片的稀疏组合; 压缩率; 补齐误差
"""
import numpy as np

def main():
    rng = np.random.RandomState(0)
    N_CONTENT = 300       # 300个内容
    D = 64                # 内容维度 (模拟高维)
    # 生成300个"内容" (高维向量, 模拟真实内容的高维形态)
    contents = rng.randn(N_CONTENT, D).astype(np.float32)
    contents /= np.linalg.norm(contents, axis=1, keepdims=True) * 0.1  # 归一缩放
    
    print(f'=== 碎片绑定实验: {N_CONTENT}个内容, 维度{D} ===')
    
    # 方法: 用K个碎片(基), 每个内容 = 稀疏组合(取最近碎片+残差)
    for K in [1, 3, 5, 10, 20, 50]:
        # K-means 找K个碎片中心
        idx = rng.choice(N_CONTENT, K, replace=False)
        centers = contents[idx].copy()
        for _ in range(30):
            d2 = ((contents[:, None, :] - centers[None, :, :])**2).sum(-1)
            lab = d2.argmin(1)
            for k in range(K):
                m = contents[lab == k]
                if len(m):
                    centers[k] = m.mean(0)
            centers /= (np.linalg.norm(centers, axis=1, keepdims=True) + 1e-9)
        # 补齐: 每个内容 = 最近碎片 + 残差(残差作为"补齐信息")
        # 只存: 碎片中心 + 每个内容的 (碎片id, 残差投影)
        # 压缩率 = 存的维度 / 原始
        # 方案A: 纯碎片(零残差) — 极端压缩但误差大
        d2 = ((contents[:, None, :] - centers[None, :, :])**2).sum(-1)
        lab = d2.argmin(1)
        recon_0 = centers[lab]
        err_0 = np.linalg.norm(contents - recon_0, axis=1).mean()
        # 方案B: 碎片id + 残差一维方向(每内容只存1个残差方向强度)
        resid = contents - centers[lab]
        rnorm = np.linalg.norm(resid, axis=1)
        recon_1 = centers[lab] + resid  # 全残差(不压缩)
        # 方案C: 碎片id + 残差方向只存前P维主成分
        P = 2
        U, S, Vt = np.linalg.svd(resid, full_matrices=False)
        recon_p = centers[lab] + (resid @ Vt[:P].T) @ Vt[:P]
        err_p = np.linalg.norm(contents - recon_p, axis=1).mean()
        # 报告
        stored_K = K  # 碎片数
        print(f'\nK={K}个碎片:')
        print(f'  纯碎片补齐误差={err_0:.4f} (极端压缩: 300内容→{K}碎片)')
        print(f'  碎片+2维残差补齐误差={err_p:.4f} (压缩: 300×64 → {K}×64 + 300×2)')
        print(f'  压缩率(存储维度比)≈ {(K*64 + N_CONTENT*2)/(N_CONTENT*64)*100:.1f}%')

if __name__ == '__main__':
    main()
