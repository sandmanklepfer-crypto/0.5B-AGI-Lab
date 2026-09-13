#!/usr/bin/env python3
# B04 SSK-4 种子调制核 — 修B03"种子把系统钉死"
# B03问题: 自指引力 α(S-x) 中心力 → x被吸到S静止 → 假自指
# B04: 种子是"参照系调制器"不是陷阱: 沿种子轴旋转调制(align*J@x), 非位移牵引
import numpy as np
np.random.seed(2)
D, DT, STEPS = 12, 0.1, 8000
ETA, GAMMA, KAPPA, DELTA = 0.5, 0.15, 0.6, 0.25
RHO, MU, C_ROT, BETA, LAMBDA = 0.02, 1.8, 0.9, 3.0, 0.015
SIG = lambda x: np.tanh(x)

def build_a():
    a = np.random.randn(D, D) * 0.5
    for i in range(D): a[(i+1) % D, i] += 1.6
    return a / np.maximum(np.abs(a).sum(1, keepdims=True), 1e-9)

def rot_gen():
    J = np.zeros((D, D))
    for i in range(D-1): J[i, i+1] = 1; J[i+1, i] = -1
    J[0, D-1] = 1; J[D-1, 0] = -1
    return J

def run(with_seed, label):
    a, J = build_a(), rot_gen()
    x = np.random.randn(D) * 0.5
    S = np.random.randn(D) * 0.3
    f, e = np.zeros(D), 0.4
    Hx, He, Hdist, HS, Hal = [], [], [], [], []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = SIG(x)
        f = f + DT * RHO * (act**2 - f); f = np.clip(f, 0, 2)
        dx = s * (a @ act - DELTA*x - MU*f*x)
        if with_seed:
            Shat = S / (np.linalg.norm(S) + 1e-9)
            align = np.tanh(BETA * (x @ Shat))
            dx = dx + C_ROT * align * (J @ x)
            S = S + DT * LAMBDA * (x - S)
        de = ETA * (act**2).sum() - GAMMA * e
        x = x + DT * dx
        e = max(e + DT*de, 0.0)
        Hx.append(np.linalg.norm(x)); He.append(e)
        if with_seed:
            Hdist.append(np.linalg.norm(x-S)); HS.append(np.linalg.norm(S))
            Hal.append(float(np.tanh(BETA*(x@(S/(np.linalg.norm(S)+1e-9))))))
    tx, te = np.array(Hx[-2000:]), np.array(He[-2000:])
    div = float(np.abs(np.diff(tx)).mean())
    if with_seed:
        dS = float(np.abs(np.diff(HS[-1000:])).mean())
        dist = float(np.array(Hdist[-2000:]).mean())
        av = float(np.std(Hal[-2000:]))
        print('[%s] |x|=%.3f e=%.3f 运动=%.4f 自距=%.3f dS=%.5f 对齐变化=%.4f' % (
            label, tx.mean(), te.mean(), div, dist, dS, av), flush=True)
    else:
        print('[%s] |x|=%.3f e=%.3f 运动=%.4f' % (label, tx.mean(), te.mean(), div), flush=True)

if __name__ == '__main__':
    print('B04 种子调制核 | D=%d 步=%d | 种子=转轴非陷阱' % (D, STEPS), flush=True)
    print('='*80, flush=True)
    run(True, 'A 种子调制(自指)')
    run(False, 'B 无种子(对照)')
    print('='*80, flush=True)
