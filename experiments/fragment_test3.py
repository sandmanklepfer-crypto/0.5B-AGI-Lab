#!/usr/bin/env python3
"""碎片绑定 v3 — 潜因子提取 (真正的压缩: 找生成源, 不是聚类)
300个内容由8个潜因子组合 → 用NMF/稀疏编码反推8个因子
→ 压缩率 = 8因子 + 每内容组合系数 (极小) + 高精度
"""
import numpy as np

def main():
    rng = np.random.RandomState(0)
    N, D, F = 300, 64, 8
    true_f = rng.randn(F, D).astype(np.float32)
    true_f /= np.linalg.norm(true_f, axis=1, keepdims=True)
    # 300内容 = 稀疏组合 (每内容只用2-3因子, 非负权重)
    H_true = np.zeros((N, F), np.float32)
    for i in range(N):
        facs = rng.choice(F, rng.randint(2, 4), replace=False)
        H_true[i, facs] = rng.rand(len(facs)).astype(np.float32) + 0.5
    X = H_true @ true_f   # (300,64) 内容
    X += rng.randn(N, D).astype(np.float32) * 0.001  # 微噪
    print(f'=== 潜因子提取: {N}内容×{D}维, 真因子{F} ===')

    # NMF 提取 F 个因子
    W = rng.rand(N, F).astype(np.float32) + 0.1
    H = rng.rand(F, D).astype(np.float32) + 0.1
    Xc = X - X.min() + 1e-3   # NMF需非负
    for it in range(300):
        # 乘性更新
        H = H * (W.T @ Xc) / (W.T @ W @ H + 1e-9)
        W = W * (Xc @ H.T) / (W @ H @ H.T + 1e-9)
    # 补齐: X ≈ W@H
    recon = W @ H
    # 归一误差
    err = np.linalg.norm(Xc - recon) / np.linalg.norm(Xc)
    print(f'NMF 提取{F}因子: 重建相对误差={err:.4f}')
    print(f'压缩率: ({F*D + N*F})/({N*D}) = {(F*D+N*F)/(N*D)*100:.1f}%')
    print(f'→ 若误差<0.05: 300内容被{F}个因子高精度绑定(2.7%存储)')

if __name__ == '__main__':
    main()
