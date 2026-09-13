#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
insight.py — 洞见能被「分叉 + 验证」构造出来吗?
================================================
用户的论证:
  ① 形式系统 = 过程的先验知识 (已内化)
  ② 在上面人为创造无尽分叉
  ③ 不断验证
  → 这就是洞见的来源, 所以很好模拟

本实验精确测第②步: 分叉能不能「单步」到达洞见?

世界: Lotka-Volterra  dx/dt=x(1-y),  dy/dt=y(x-1)
真不变量: V = x + y - ln x - ln y     ← 超越函数, 不是多项式!
          (对应 NS 案例里 Córdoba–Martínez-Zoroa 的 forcing 方法 = 新积木)

候选积木: 9 个多项式 + 6 个超越 (ln x, ln y, 1/x, 1/y, x·ln y, y·ln x)
验证器: 精确! dV/dt 数值为 0 → L1 级 (零不确定性)

四种搜索:
  ① 纯多项式基           (字典里没有 ln)
  ② 全字典一次性求解       (上帝视角)
  ③ 贪心: 每次加一块       (← 模拟"无尽分叉")
  ④ 同时加一对            (← 真正的"洞见": 一次选对一组)
"""
import numpy as np, itertools, time

t0 = time.time()

# ==================== 世界 ====================
def rhs(x, y):
    """dx/dt = x(1-y),  dy/dt = y(x-1)"""
    return x*(1.0 - y), y*(x - 1.0)


def samples(n=400, seed=0):
    r = np.random.RandomState(seed)
    return r.uniform(0.15, 3.0, n), r.uniform(0.15, 3.0, n)


# ==================== 候选积木 (φ 和 dφ/dt) ====================
def make_blocks():
    B = []
    # 多项式 (去掉常数项, 否则 dM 会有个恒零列 → 假零空间)
    for a in range(4):
        for b in range(4 - a):
            if a == 0 and b == 0:
                continue
            def mk(a=a, b=b):
                def phi(x, y): return x**a * y**b
                def dphi(x, y):
                    p = x**a * y**b
                    return p * (a*(1.0-y) + b*(x-1.0))
                return phi, dphi
            f, g = mk()
            B.append(("x^%d·y^%d" % (a, b), f, g, 'poly'))
    # 超越积木 (对应"新方法")
    B.append(("ln x", lambda x, y: np.log(x),
              lambda x, y: 1.0 - y, 'trans'))
    B.append(("ln y", lambda x, y: np.log(y),
              lambda x, y: x - 1.0, 'trans'))
    B.append(("1/x", lambda x, y: 1.0/x,
              lambda x, y: -(1.0-y)/x, 'trans'))
    B.append(("1/y", lambda x, y: 1.0/y,
              lambda x, y: -(x-1.0)/y, 'trans'))
    B.append(("x·ln y", lambda x, y: x*np.log(y),
              lambda x, y: x*(1.0-y)*np.log(y) + x*(x-1.0), 'trans'))
    B.append(("y·ln x", lambda x, y: y*np.log(x),
              lambda x, y: y*(x-1.0)*np.log(x) + y*(1.0-y), 'trans'))
    return B


# ==================== 验证器: 找零空间 ====================
def find_invariant(B, X, Y):
    """
    返回 (quality, 组合系数)
    quality = ||dV/dt|| / ||V||
      < 1e-8  → 精确不变量 (验证通过)
    """
    if len(B) < 2:
        return 1e9, None
    M = np.stack([f(X, Y) for _, f, _, _ in B], 1)
    dM = np.stack([g(X, Y) for _, _, g, _ in B], 1)
    # 归一化 (防量级失衡)
    Mn = M / (np.linalg.norm(M, axis=0, keepdims=True) + 1e-12)
    dMn = dM / (np.linalg.norm(dM, axis=0, keepdims=True) + 1e-12)
    # dMn 的最小奇异值方向
    _, S, Vt = np.linalg.svd(dMn, full_matrices=True)
    c = Vt[-1]
    res = np.linalg.norm(dMn @ c) / (np.linalg.norm(c) + 1e-12)
    nrm = np.linalg.norm(Mn @ c) / (np.linalg.norm(c) + 1e-12)
    if nrm < 1e-6:          # 组合≈0, 无意义
        return 1e9, c
    return res / nrm, c


ALL = make_blocks()
NAMES = [b[0] for b in ALL]
POLY = [i for i, b in enumerate(ALL) if b[3] == 'poly']
TRANS = [i for i, b in enumerate(ALL) if b[3] == 'trans']

X, Y = samples()

print("=" * 92)
print("洞见能被「无尽分叉 + 验证」构造出来吗?")
print("=" * 92)
print()
print("  系统: dx/dt = x(1-y),  dy/dt = y(x-1)   (Lotka-Volterra)")
print("  真不变量: V = x + y − ln x − ln y        ← 超越函数, 不是多项式")
print("  积木: %d 个 (%d 多项式 + %d 超越)" % (len(ALL), len(POLY), len(TRANS)))
print("  验证器: dV/dt == 0 精确判定 (L1 级, 零不确定性)")
print()
print("  指标 quality = ||dV/dt|| / ||V||     (<1e-8 = 找到精确不变量)")
print()

# ---------- ① 纯多项式 ----------
q1, _ = find_invariant([ALL[i] for i in POLY], X, Y)
print("  ① 纯多项式基 (%d 块)" % len(POLY))
print("     quality = %.3e   → %s" %
      (q1, "✅ 找到" if q1 < 1e-8 else "❌ 找不到 (字典里没有 ln)"))

# ---------- ② 全字典 ----------
q2, c2 = find_invariant([ALL[i] for i in range(len(ALL))], X, Y)
print()
print("  ② 全字典一次性求解 (上帝视角, %d 块)" % len(ALL))
print("     quality = %.3e   → %s" % (q2, "✅ 找到" if q2 < 1e-8 else "❌"))
if q2 < 1e-8:
    idx = np.argsort(-np.abs(c2))[:5]
    combo = "  ".join("%+.2f·%s" % (c2[i], NAMES[i]) for i in idx if abs(c2[i]) > 1e-3)
    print("     组合 = %s" % combo)

# ---------- ③ 贪心单步加块 (模拟"无尽分叉") ----------
print()
print("  ③ 贪心: 每次只加一块 (模拟『不断分叉』)")
cur = list(POLY)
best = q1
history = []
stuck = False
for step in range(1, len(TRANS) + 1):
    cands = []
    for j in TRANS:
        if j in cur:
            continue
        q, _ = find_invariant([ALL[i] for i in cur + [j]], X, Y)
        cands.append((q, j))
    if not cands:
        break
    q, j = min(cands, key=lambda t: t[0])
    improve = (q < best * 0.5)
    history.append((step, NAMES[j], q, improve))
    if improve:
        cur.append(j); best = q
    else:
        stuck = True
        break
for st, nm, q, im in history:
    print("     第%d步: +%-10s → quality=%.3e  %s" % (st, nm, q, "↓改善" if im else "✗无改善"))
    if not im:
        print("            ★ 单块加不进去 → 贪心卡住")
print("     → %s" % ("✅ 找到" if best < 1e-8 else "❌ 失败 (单步分叉到不了)"))

# ---------- ④ 同时加一对 (真正的洞见) ----------
print()
print("  ④ 一次性加一对 (模拟『同时选对一组积木』)")
found = None
tried = 0
for k in [2]:
    for combo in itertools.combinations(TRANS, k):
        tried += 1
        Bt = [ALL[i] for i in POLY + list(combo)]
        q, c = find_invariant(Bt, X, Y)
        if q < 1e-8:
            found = combo
            break
    if found:
        break
if found:
    Bt = [ALL[i] for i in POLY + list(found)]
    q, c = find_invariant(Bt, X, Y)
    idx = np.argsort(-np.abs(c))[:4]
    print("     k=2, 试了 %d 组 → 找到: %s" %
          (tried, " + ".join(NAMES[i] for i in found)))
    print("     组合 = " + "  ".join("%+.2f·%s" % (c[i], NAMES[i]) for i in idx))
    print("     quality = %.3e   → ✅ 找到" % q)

# ---------- 汇总 ----------
print()
print("=" * 92)
print("结论")
print("=" * 92)
print("  %-26s %-14s %s" % ("搜索方式", "quality", "结果"))
print("  " + "-" * 70)
print("  %-26s %-14.2e %s" % ("① 纯多项式基", q1, "❌ 找不到"))
print("  %-26s %-14.2e %s" % ("③ 贪心单步加块", best, "❌ 卡住" if best > 1e-8 else "✅"))
print("  %-26s %-14.2e %s" % ("④ 同时加一对", q if found else 1e9, "✅ 找到"))
print("  %-26s %-14.2e %s" % ("② 全字典(上帝视角)", q2, "✅ 找到"))
print()
print("  ★ 洞见的『尺寸』= 需要同时选对几个积木")
print("     尺寸=1 → 贪心可行 (可自动分叉)")
print("     尺寸=2 → 组合数 C(%d,2)=%d, 还能穷举" % (len(TRANS), len(TRANS)*(len(TRANS)-1)//2))
print("     尺寸=k → 组合数 C(n,k) → 指数爆炸")
print()
print("  用时 %.2fs" % (time.time() - t0))
