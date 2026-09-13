#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_world.py — 路线: 脑 + 世界 + 成败(标量) + 嘴
====================================================
核心: 意义不来自脑, 来自「做成事」。脑只吃标量(不碰梯度), 嘴出语言。

世界(有隐藏状态):
  季节 s ∈ {0,1}, 随机切换(平均每150步)。只有成败(1bit)能推断它。
  任务: 说一个"词"(字符), 落在当季的正确集合里 → 成功。
  ★ 关键: 季节不可见, 只能从最近的成败里推出来 → 必须有记忆

嘴(固定, 语言通路):
  模式 m → 字符分布 P(c|m)。m=0 偏向集合A, m=1 偏向集合B (带噪声)。

脑(自持核, f 冻结, 只吃标量):
  x_{t+1} = f(x_t) + eps * W_in @ reward_history   ← 世界通过状态通道约束脑
  模式 m = argmax(W_out @ x)                        ← 只读头, 用标量学(REINFORCE)

对照(核心):
  A 有脑+有反馈   世界约束脑 → 应能推断季节
  B 有脑+无反馈   脑收不到成败 → 应失败 (证明"世界"是必需的)
  C 无脑(无记忆)  只看当前 → 应失败 (证明"记忆"是必需的)
  D 神谕          直接知道季节 → 上界

指标: 准确率 / 切换后恢复需要的步数
"""
import numpy as np, time
t0 = time.time()

DT = 0.05; ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8; SIG = np.tanh
D, NB = 24, 6; d = D // NB
NC = 16                      # 字符集大小(嘴的输出空间)
STEPS = 20000
SWITCH_P = 1.0 / 150.0       # 季节切换概率
EPS_IN = 0.6                 # 世界→脑 的强度

# ---------- 脑 (f 冻结) ----------
r = np.random.RandomState(0)
A = np.zeros((D, D))
for b in range(NB):
    s = b * d; e = s + d
    sub = r.randn(d, d); w = np.abs(np.linalg.eigvals(sub)).max()
    A[s:e, s:e] = sub * (1.15 / w)
A = A * 2.5
W_in = r.randn(D, 2) / np.sqrt(2)      # 输入: [reward, reward_trace]

# ---------- 嘴 (固定映射: 模式→字符分布) ----------
C0 = np.arange(0, 8)                    # 集合A
C1 = np.arange(8, 16)                   # 集合B
Pc = np.zeros((2, NC))
Pc[0, C0] = 0.70 / 8; Pc[0, C1] = 0.30 / 8
Pc[1, C1] = 0.70 / 8; Pc[1, C0] = 0.30 / 8
Pc += 1e-9; Pc /= Pc.sum(1, keepdims=True)

def run(mode='brain_fb', seed=1, steps=STEPS):
    rng = np.random.RandomState(seed)
    x = rng.randn(D, 1) * 0.5
    F = np.zeros_like(x); E = np.full((1, 1), 0.4)
    W_out = np.zeros((2, D))            # 只读头(标量学)
    trace = 0.0
    season = 0
    hist, seasons, modes = [], [], []
    base = 0.0
    for t in range(steps):
        # --- 脑读出头 → 模式 ---
        if mode == 'oracle':
            m = season
        elif mode == 'nogate':
            m = 0
        else:
            lg = W_out @ x
            z = lg - lg.max(); p = np.exp(z); p /= p.sum()
            m = int(rng.rand() < p[1])
        # --- 嘴说一个词 ---
        c = int(rng.choice(NC, p=Pc[m]))
        # --- 世界判定 ---
        ok = int((c in C0) if season == 0 else (c in C1))
        # --- 脑的状态演化 (世界只给一个标量!) ---
        if mode == 'brain_fb':
            inp = np.array([[float(ok), trace]]).reshape(2, 1)
        elif mode == 'brain_nofb':
            inp = np.array([[0.0, 0.0]]).reshape(2, 1)   # 收不到成败
        else:
            inp = np.zeros((2, 1))
        act = SIG(x)
        F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
        g = E / (KAPPA + E)
        core = A @ act - MU * F * x + EPS_IN * (W_in @ inp)
        x = x + DT * (g * core - G0 * x)
        E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
        trace = 0.9 * trace + 0.1 * ok
        # --- 只读头: 标量学 (REINFORCE, 脑动力学不碰梯度) ---
        if mode in ('brain_fb', 'brain_nofb'):
            base = 0.99 * base + 0.01 * ok
            lg = W_out @ x; z = lg - lg.max(); p = np.exp(z); p /= p.sum()
            onehot = np.array([[1.0 - m], [float(m)]])
            W_out += 0.03 * (ok - base) * (onehot - p) @ x.T
        # --- 世界演化 ---
        if rng.rand() < SWITCH_P:
            season = 1 - season
        hist.append(ok); seasons.append(season); modes.append(m)
    return np.array(hist), np.array(seasons), np.array(modes)


print("=" * 96)
print("脑+世界+成败+嘴 | 世界有隐藏季节(不可见, 只能从成败推断) | %d 步" % STEPS)
print("=" * 96)
print("  判据: 准确率(越高=越能做成事) + 切换后恢复步数(越短=越快跟上世界)")
print()
print("  %-22s %-12s %-14s %-14s %s"
      % ("配置", "总准确率", "稳态准确率", "切换后恢复", "说明"))

results = {}
for mode, name, note in [
    ('brain_fb',  'A ★有脑+有反馈', '世界约束脑'),
    ('brain_nofb','B 有脑+无反馈',  '证明世界必需'),
    ('nogate',    'C 无脑(固定模式)', '证明记忆必需'),
    ('oracle',    'D 神谕(知道季节)', '上界'),
]:
    ok, seas, mods = run(mode)
    acc = ok.mean()
    steady = ok[3000:].mean()
    # 切换后恢复: 找切换点, 看之后多少步内准确率回到0.6
    sw = np.where(np.diff(seas) != 0)[0]
    rec = []
    for s in sw:
        if s + 400 < len(ok):
            seg = ok[s:s + 400]
            k = np.where(np.convolve(seg, np.ones(30) / 30, 'valid') > 0.6)[0]
            rec.append(k[0] + 15 if len(k) else 400)
    rmed = int(np.median(rec)) if rec else -1
    results[mode] = (acc, steady, rmed)
    print("  %-22s %-12.3f %-14.3f %-14s %s"
          % (name, acc, steady, ("%d 步" % rmed) if rmed > 0 else "—", note))

print()
print("-" * 96)
print("核心结论")
print("-" * 96)
a, b, c, d_ = results['brain_fb'], results['brain_nofb'], results['nogate'], results['oracle']
print("  A(有脑+反馈) vs B(无反馈):  %+.1f%%   → 世界约束脑 有没有用?"
      % (100 * (a[1] - b[1])))
print("  A(有脑+反馈) vs C(无记忆):  %+.1f%%   → 记忆(脑的状态)有没有用?"
      % (100 * (a[1] - c[1])))
print("  A(有脑+反馈) vs D(神谕):    %+.1f%%   → 离上界还有多远"
      % (100 * (a[1] - d_[1])))
print()
if a[1] > max(b[1], c[1]) + 0.05:
    print("  ★ 成立: 脑(记忆) + 世界(标量) 缺一不可 —— 意义从交互中产生")
    if a[2] > 0 and a[2] < (b[2] if b[2] > 0 else 999):
        print("    且切换后恢复更快 (%d 步 vs %s 步)" % (a[2], b[2]))
else:
    print("  ✗ 不成立: 脑+世界没有带来增益")
print()
print("总耗时 %.1fs" % (time.time() - t0))
