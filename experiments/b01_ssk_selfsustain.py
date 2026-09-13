#!/usr/bin/env python3
"""
B01 SSK-1 自持核 — B线(AGI/自主性)第一块砖
====================================================
戒律(用户哲学):
  1. 无外部裁判: 不写 if塌缩→惩罚. 生死必须从动力学涌现
  2. 能量自养: 能量流由系统自身结构维持 (V30缺点=E是外参, 此处内生化)
  3. 死要真死: 状态塌缩到零 (V30式 |x|→0), 不是"停止输出"
设计(仿自催化化学网络 + 资源代谢):
  内容层 x∈R^d:  dx_i/dt = s(e)·[ Σ_j a_ij σ(x_j) − δ·x_i ]
    a = 非对称耦合矩阵 (谁激活谁). σ=tanh (有界非线性)
    含自催化环(i→j→k→i) → 非平衡自持; 无环 → 必然衰减
  能量层 e>0:    de/dt = η·Σ_i σ(x_i)² − γ·e
    活性平方 = 代谢产能 (结构换能量); γ = 耗散
  生死涌现:
    s(e)=e/(κ+e) 能量门控. 活性高→产能>耗散→e自持→s≈1→活
    活性塌→e耗尽→s→0→x永远冻结在0 = 真死 (涌现, 无人判)
验证: 三组参数
  A 自催化环     → 应自持巡游(活): |x|不塌, 轨迹不重复, e自持
  B 纯竞争无环   → 应涌现死亡: |x|→0, e→0 (真死)
  C 弱耦合有环   → 中间态: 活着但落入低复杂度 (观测, 不裁判)
输出: 轨迹观测 (范数/e/复杂度) — 仅观测, 不是判据
"""
import numpy as np

np.random.seed(0)
D = 12
DT = 0.1
STEPS = 2000
SIG = lambda x: np.tanh(x)
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25

def build_a(mode):
    a = np.random.randn(D, D) * 0.4
    if mode == 'cycle':   # 加自催化环: 1→2→3→...→D→1 正环
        for i in range(D):
            a[(i + 1) % D, i] += 1.6
    elif mode == 'weak':  # 弱环(可能不足自持)
        for i in range(D):
            a[(i + 1) % D, i] += 0.5
    elif mode == 'compete':  # 竞争: 对角负(自己抑制自己), 无正环
        np.fill_diagonal(a, -1.5)
    # 保持非对称(非平衡)
    return a

def run(mode, label):
    a = build_a(mode)
    x = np.random.randn(D) * 0.8       # 初始扰动(自发起点)
    e = 0.5                            # 初始能量
    hist_x, hist_e = [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)            # 能量门控
        act = SIG(x)
        dx = s * (a @ act - DELTA * x)
        de = ETA * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = e + DT * de
        e = max(e, 0.0)
        hist_x.append(np.linalg.norm(x))
        hist_e.append(e)
    # 观测(仅观测): 尾段范数/能量/轨迹多样性(相邻差)
    tail_x = np.array(hist_x[-500:])
    tail_e = np.array(hist_e[-500:])
    diversity = np.abs(np.diff(tail_x)).mean()
    state = ('自持' if tail_x.mean() > 0.3 and tail_e.mean() > 0.05 else
             '死亡(涌现)' if tail_x.mean() < 0.02 else '临界')
    print('[%s] |x|尾均值=%.4f | e尾均值=%.4f | 轨迹多样性=%.5f → %s' % (
        label, tail_x.mean(), tail_e.mean(), diversity, state), flush=True)
    return hist_x, hist_e

if __name__ == '__main__':
    print('B01 SSK-1 自持核 | D=%d dt=%.2f 步=%d | 无外部裁判, 生死涌现' % (D, DT, STEPS), flush=True)
    print('=' * 70, flush=True)
    r1 = run('cycle',   'A 自催化环')
    r2 = run('compete', 'B 纯竞争(无环)')
    r3 = run('weak',    'C 弱环(临界)')
    # 存观测
    np.savez('/workspace/b01_ssk_obs.npz',
             a_cycle=np.array(r1[0]), a_compete=np.array(r2[0]), a_weak=np.array(r3[0]))
    print('=' * 70, flush=True)
    print('观测已存 /workspace/b01_ssk_obs.npz (仅观测, 生死由动力学涌现)', flush=True)
