#!/usr/bin/env python3
"""方向隔离度分析: 身份/攻击/拒绝方向的几何正交性
用法: dir_isolation.py <d_identity> <d_attack> <d_reject>
输出: cos 矩阵 + 隔离度解读 (|cos|<0.1 强隔离, <0.3 隔离, >0.3 纠缠)
"""
import sys
import numpy as np

def load(p):
    d = np.fromfile(p, dtype=np.float32)
    return d / np.linalg.norm(d)

names = ['身份', '攻击', '拒绝']
dirs = [load(p) for p in sys.argv[1:4]]
n = len(dirs)
print('=== 方向隔离度 (cos 矩阵) ===')
print(f'{"":8s}' + ''.join(f'{nm:>10s}' for nm in names))
C = np.zeros((n, n))
for i in range(n):
    row = f'{names[i]:8s}'
    for j in range(n):
        C[i, j] = float(dirs[i] @ dirs[j])
        row += f'{C[i,j]:+10.4f}'
    print(row)
print()
for i in range(n):
    for j in range(i+1, n):
        c = C[i, j]
        tag = '强隔离' if abs(c) < 0.1 else '隔离' if abs(c) < 0.3 else '纠缠' if abs(c) < 0.6 else '高度纠缠'
        print(f'{names[i]} ⊥ {names[j]}: cos={c:+.4f} → {tag}')
# 正交补投影强度: 身份方向在攻击/拒绝张成空间之外的残留
if n >= 3:
    B = np.stack([dirs[1], dirs[2]]).T  # (d, 2)
    proj = B @ np.linalg.pinv(B.T @ B) @ B.T @ dirs[0]
    resid = np.linalg.norm(dirs[0] - proj)
    print(f'\n身份方向在(攻击,拒绝)空间外的残留: {resid:.4f} (1=完全独立, 0=被张成)')
