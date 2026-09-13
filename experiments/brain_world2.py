#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_world2.py — 修: 脑必须收到 (模式,成败) 的配对
======================================================
v1 病因: 脑只收到 [成败, 成败轨迹] → 不知道成败对应哪个模式 → 无法信用分配
v2 修法: 输入 = [选0的成败痕迹, 选1的成败痕迹] → 脑能比较"哪个模式在管用"
先做「线性探针」验证: 季节能否从脑状态 x 解码出来? (决定架构是否可行)
"""
import numpy as np, time
t0 = time.time()
DT = 0.05; ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8; SIG = np.tanh
D, NB = 24, 6; d = D // NB
NC = 16
STEPS = 20000
SWITCH_P = 1.0 / 150.0
EPS_IN = 1.5

r = np.random.RandomState(0)
A = np.zeros((D, D))
for b in range(NB):
    s = b * d; e = s + d
    sub = r.randn(d, d); w = np.abs(np.linalg.eigvals(sub)).max()
    A[s:e, s:e] = sub * (1.15 / w)
A = A * 2.5
W_in = r.randn(D, 2) / np.sqrt(2)

C0 = np.arange(0, 8); C1 = np.arange(8, 16)
Pc = np.zeros((2, NC)); Pc[0, C0] = 0.70/8; Pc[0, C1] = 0.30/8
Pc[1, C1] = 0.70/8; Pc[1, C0] = 0.30/8
Pc += 1e-9; Pc /= Pc.sum(1, keepdims=True)


def run(mode='brain_fb', seed=1, steps=STEPS, lr=0.15):
    rng = np.random.RandomState(seed)
    x = rng.randn(D, 1) * 0.5
    F = np.zeros_like(x); E = np.full((1, 1), 0.4)
    W_out = np.zeros((2, D))
    tr0 = tr1 = 0.0                 # 两个模式各自的成败痕迹
    season = 0
    ok_h, seas_h, mod_h, x_h = [], [], [], []
    base = 0.0
    for t in range(steps):
        if mode == 'oracle':
            m = season
        elif mode == 'nogate':
            m = 0
        else:
            lg = W_out @ x
            z = lg - lg.max(); p = np.exp(z); p /= p.sum()
            m = int(rng.rand() < p[1])
        c = int(rng.choice(NC, p=Pc[m]))
        ok = int((c in C0) if season == 0 else (c in C1))
        # ★ 关键: 输入 = 两个模式各自的成败痕迹
        if mode == 'brain_fb':
            inp = np.array([[tr0], [tr1]])
        elif mode == 'brain_nofb':
            inp = np.zeros((2, 1))
        else:
            inp = np.zeros((2, 1))
        act = SIG(x)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        x = x + DT * (g * (A @ act - MU * F * x + EPS_IN * (W_in @ inp)) - G0 * x)
        E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        # 痕迹更新 (只更新被选中的那个)
        if m == 0: tr0 = 0.97 * tr0 + 0.03 * ok
        else:      tr1 = 0.97 * tr1 + 0.03 * ok
        if mode in ('brain_fb', 'brain_nofb'):
            base = 0.995 * base + 0.005 * ok
            lg = W_out @ x; z = lg - lg.max(); p = np.exp(z); p /= p.sum()
            onehot = np.array([[1.0 - m], [float(m)]])
            W_out += lr * (ok - base) * ((onehot - p) @ x.T)
        if rng.rand() < SWITCH_P: season = 1 - season
        ok_h.append(ok); seas_h.append(season); mod_h.append(m)
        if t % 20 == 0: x_h.append(x[:, 0].copy())
    return (np.array(ok_h), np.array(seas_h), np.array(mod_h), np.array(x_h))


print("=" * 96)
print("v2: 脑收到 (模式,成败) 配对 | %d 步" % STEPS)
print("=" * 96)
print()
print("  %-22s %-12s %-12s %s" % ("配置", "总准确率", "稳态准确率", "切换后恢复"))
res = {}
for mode, name in [('brain_fb', 'A ★有脑+有反馈'), ('brain_nofb', 'B 有脑+无反馈'),
                   ('nogate', 'C 无脑'), ('oracle', 'D 神谕')]:
    ok, seas, mods, X = run(mode)
    sw = np.where(np.diff(seas) != 0)[0]
    rec = []
    for s in sw:
        if s + 400 < len(ok):
            seg = ok[s:s+400]
            k = np.where(np.convolve(seg, np.ones(30)/30, 'valid') > 0.6)[0]
            rec.append(k[0]+15 if len(k) else 400)
    rmed = int(np.median(rec)) if rec else -1
    res[mode] = (ok.mean(), ok[3000:].mean(), rmed)
    print("  %-22s %-12.3f %-12.3f %s"
          % (name, res[mode][0], res[mode][1], ("%d 步" % rmed) if rmed > 0 else "—"))

# ★ 线性探针: 季节能否从脑状态解码?
ok, seas, mods, X = run('brain_fb')
n = min(len(X), len(seas)//20)
Xs = X[:n]; ys = seas[:n*20:20][:n]
ntr = int(n*0.7)
W = np.linalg.lstsq(Xs[:ntr], (ys[:ntr]*2-1).astype(float), rcond=None)[0]
pred = np.sign(Xs[ntr:] @ W)
acc = float((pred == (ys[ntr:]*2-1)).mean())
print()
print("-" * 96)
print("线性探针: 季节能否从脑状态 x 解码?")
print("  解码准确率 = %.3f   %s" % (acc, "✅ 脑状态里有季节信息" if acc > 0.6 else "❌ 脑状态里没有季节信息"))
print()
print("-" * 96)
print("结论")
print("-" * 96)
a, b, c, d_ = res['brain_fb'], res['brain_nofb'], res['nogate'], res['oracle']
print("  A vs B(无反馈): %+.1f%%" % (100*(a[1]-b[1])))
print("  A vs C(无脑):   %+.1f%%" % (100*(a[1]-c[1])))
print("  A vs D(神谕):   %+.1f%%" % (100*(a[1]-d_[1])))
if a[1] > max(b[1], c[1]) + 0.05:
    print("  ★ 成立! 脑+世界缺一不可")
else:
    print("  ✗ 仍不成立")
print()
print("总耗时 %.1fs" % (time.time()-t0))
