#!/usr/bin/env python3
"""
B02 SSK-2 自持核v2 — 修 B01 的"假活"(能量自持但静止=固定点)
B01发现: 自持≠活. 环耦合+能量门控 → 停在固定点(多样性=0) = 假活
B02修法(动力学内建, 非外部裁判): 疲劳慢变量 f (时间尺度分离)
  df_i/dt = ρ·(σ(x_i)² − f_i)     ρ小=慢变量(疲劳积累/恢复)
  dx_i/dt = s(e)·[Σ a_ij σ(x_j) − δx_i − μ·f_i·x_i]
  持续高活的单元 → f 升 → 被抑制 → 活性被迫转移 → 固定点必然失稳
  → 巡游/振荡/混沌 (永不重复有结构) = 活 的涌现条件
其他修正: a 行归一化(防爆炸), e 代谢同前
验证三组:
  A 环+疲劳  → 期望: 自持 + 多样性>0 + e自持 = 真活
  B 竞争     → 期望: x→0, e→0 = 涌现死亡
  C 弱环     → 临界观察
"""
import numpy as np

np.random.seed(0)
D = 12
DT = 0.1
STEPS = 6000
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25
RHO, MU = 0.02, 1.8
SIG = lambda x: np.tanh(x)

def build_a(mode):
    a = np.random.randn(D, D) * 0.5
    if mode == 'cycle':
        for i in range(D):
            a[(i + 1) % D, i] += 1.6
    elif mode == 'weak':
        for i in range(D):
            a[(i + 1) % D, i] += 0.5
    elif mode == 'compete':
        np.fill_diagonal(a, -1.6)
    # 行归一化: 每行 |a| 和 = 1 → 平衡范数有界(防爆炸)
    rowsum = np.abs(a).sum(1, keepdims=True)
    a = a / np.maximum(rowsum, 1e-9)
    return a

def run(mode, label):
    a = build_a(mode)
    x = np.random.randn(D) * 0.5
    f = np.zeros(D)
    e = 0.4
    Hx, He, Hdiv = [], [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        # 疲劳慢变量 (先更新: 活性产生疲劳)
        f = f + DT * RHO * (act ** 2 - f)
        f = np.clip(f, 0, 2.0)
        dx = s * (a @ act - DELTA * x - MU * f * x)
        de = ETA * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT * de, 0.0)
        Hx.append(np.linalg.norm(x)); He.append(e)
        if t % 25 == 0:
            Hdiv.append(np.linalg.norm(x - np.array(Hx[-2] if len(Hx) > 1 else Hx[-1])))
    tail_x = np.array(Hx[-1500:])
    tail_e = np.array(He[-1500:])
    # 多样性: 每25步的位移均值 (尾段)
    div = float(np.array(Hdiv[-60:]).mean())
    alive = tail_x.mean() > 0.3 and tail_e.mean() > 0.05
    real_life = alive and div > 1e-3
    state = ('真活(自持+运动)' if real_life else
             '假活(自持但静止)' if alive else
             '死亡(涌现)' if tail_x.mean() < 0.03 else '临界')
    print('[%s] |x|=%.3f e=%.3f 运动量=%.5f → %s' % (
        label, tail_x.mean(), tail_e.mean(), div, state), flush=True)
    return Hx, He

if __name__ == '__main__':
    print('B02 SSK-2 | 疲劳慢变量+代谢自养 | D=%d 步=%d | 生死/动静全由动力学涌现' % (D, STEPS), flush=True)
    print('=' * 72, flush=True)
    run('cycle',   'A 环+疲劳')
    run('compete', 'B 竞争(无环)')
    run('weak',    'C 弱环')
    print('=' * 72, flush=True)
