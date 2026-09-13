#!/usr/bin/env python3
"""
B03 SSK-3 自读种子核 — 给自持核装"自己"(自指种子, V08思想重建)
========================================================
B02: 系统自持+运动(真活), 但没有"自己" — 12维数值巡游, 无自我参照
V08种子思想(用户记忆+研究史): 种子S是持久结构, 系统"读自己的种子"
  = 状态演化参照S, S随系统历史更新, S始终是"关于自己"的锚
========================================================
设计 (全动力学, 无外部裁判):
  内容层 x:  dx = s(e)[Aσ(x) − δx − μf·x] + α·g(S − x)
        ↑B02自持基础                        ↑自读种子项: 状态被拉向种子(自指引力)
  种子 S (慢, 持久自我):  dS/dt = λ·(x_center − S)   λ很小 = 种子缓慢吸收历史
        S = "我走过的平均形态" — 系统读它, 被它牵引, 又更新它 → 自指闭环
  疲劳 f, 能量 e: 同B02
验证: 观测(不裁判)
  A 有种子: 巡游是否围绕种子? 种子是否随历史演化? 轨迹是否有"自我一致性"(比无种子更稳)?
  B 无种子(对照): 巡游漂移无锚
  指标: |x-S|(系统与自己的距离), |dS/dt|(种子在演化=自我在形成), 运动量
"""
import numpy as np

np.random.seed(1)
D = 12
DT = 0.1
STEPS = 8000
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25
RHO, MU = 0.02, 1.8
ALPHA, LAMBDA = 0.6, 0.01    # 自指引力 / 种子吸收率
SIG = lambda x: np.tanh(x)

def build_a(mode='cycle'):
    a = np.random.randn(D, D) * 0.5
    for i in range(D):
        a[(i + 1) % D, i] += 1.6
    rowsum = np.abs(a).sum(1, keepdims=True)
    return a / np.maximum(rowsum, 1e-9)

def run(with_seed, label):
    a = build_a()
    x = np.random.randn(D) * 0.5
    S = np.random.randn(D) * 0.3   # 初始种子(微弱"我")
    f = np.zeros(D); e = 0.4
    Hx, He, Hdist, HS = [], [], [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        f = f + DT * RHO * (act ** 2 - f)
        f = np.clip(f, 0, 2.0)
        dx = s * (a @ act - DELTA * x - MU * f * x)
        if with_seed:
            dx = dx + ALPHA * (S - x)      # 自读种子: 被自己的种子牵引
        de = ETA * (act ** 2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT * de, 0.0)
        if with_seed:
            S = S + DT * LAMBDA * (x - S)  # 种子缓慢吸收历史 → "我"在形成
        Hx.append(np.linalg.norm(x)); He.append(e)
        if with_seed:
            Hdist.append(np.linalg.norm(x - S)); HS.append(np.linalg.norm(S))
    tail_x = np.array(Hx[-2000:])
    tail_e = np.array(He[-2000:])
    div = float(np.abs(np.diff(tail_x)).mean())
    if with_seed:
        dS = float(np.abs(np.diff(HS[-1000:])).mean())   # 种子演化速度
        dist = float(np.array(Hdist[-2000:]).mean())      # 系统与自己的距离
        print('[%s] |x|=%.3f e=%.3f 运动=%.4f |自距|=%.3f |dS|=%.5f' % (
            label, tail_x.mean(), tail_e.mean(), div, dist, dS), flush=True)
    else:
        print('[%s] |x|=%.3f e=%.3f 运动=%.4f' % (label, tail_x.mean(), tail_e.mean(), div), flush=True)

if __name__ == '__main__':
    print('B03 自读种子核 | D=%d 步=%d | 系统读自己种子+种子随历史演化' % (D, STEPS), flush=True)
    print('=' * 76, flush=True)
    run(True,  'A 有种子(自指)')
    run(False, 'B 无种子(对照)')
    print('=' * 76, flush=True)
