#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
insight2.py — 正确设计: 关键信息只存在于提示里
================================================
上一版失败: MLP 能从 x 自己学到全部信息 → 提示冗余

本版:
  x (64维) 只包含 【部分】信息 (proj4)
  类别 = argmax([proj4, proj5, 0])   ← 需要 proj4 和 proj5 的比较
  proj5 【不在 x 里】, 只能从提示获得

  → 无提示时, 无论多少算力都只能靠 proj4, 准确率有上限
  → 有 proj5 的提示时, 才能完全分类

四种提示:
  A 自己投影   = P@x     (x 的低维投影, 不含新信息)
  B 外部真信息 = proj5   (x 里没有的关键量) ★ 这才是"灵光"
  C 随机
  D 无提示
"""
import numpy as np, time

t0 = time.time()
D, DH, N, IT = 64, 24, 1500, 300
rng = np.random.RandomState(0)

# ==================== 数据构造 ====================
w4 = rng.randn(D) / np.sqrt(D)
X = np.zeros((N, D))
for i in range(N):
    p4 = rng.randn(); p5 = rng.randn()
    # ★ x 只含 proj4 的信息 (w4 方向), 不含 proj5
    X[i] = p4 * w4 + rng.randn(D) * 0.5
proj4 = X @ w4
# proj5 独立生成, 和 x 无关
proj5 = rng.randn(N)
# 类别: 需要比较 proj4 和 proj5
y = np.stack([proj4, proj5, np.zeros(N)], 1).argmax(1)   # 0: proj4最大, 1: proj5最大, 2: 都负

# 训练/测试划分
ntr = 1000
Xtr, Xte = X[:ntr], X[ntr:]
p5tr, p5te = proj5[:ntr], proj5[ntr:]
ytr, yte = y[:ntr], y[ntr:]


def hint(kind, X, p5, n):
    """4 维提示"""
    if kind == 'none': return np.zeros((n, 4))
    if kind == 'self':                     # A: x 自己的低维投影 (无新信息)
        Wp = rng.randn(4, D)/np.sqrt(D)
        return X @ Wp.T
    if kind == 'world':                    # B: 外部关键信息 proj5
        return np.stack([p5, np.abs(p5), np.sign(p5), np.zeros(n)], 1)
    if kind == 'rand':
        return np.random.RandomState(7).randn(n, 4)


def run(kind, seed=0):
    r = np.random.RandomState(seed)
    Hh = DH
    W1 = r.randn(Hh, D+4)/np.sqrt(D+4); b1 = np.zeros((Hh, 1))
    W2 = r.randn(3, Hh)/np.sqrt(Hh); b2 = np.zeros((3, 1))
    P = [W1, b1, W2, b2]
    M = [np.zeros_like(p) for p in P]; V = [np.zeros_like(p) for p in P]

    Ztr = np.hstack([Xtr, hint(kind, Xtr, p5tr, ntr)]).T
    Zte = np.hstack([Xte, hint(kind, Xte, p5te, N-ntr)]).T
    Ytr = np.zeros((ntr, 3)); Ytr[np.arange(ntr), ytr] = 1

    for it in range(IT):
        A1 = np.tanh(W1 @ Ztr + b1)
        Yp = W2 @ A1 + b2
        e = np.exp(Yp - Yp.max(0, keepdims=True)); Pp = e/e.sum(0, keepdims=True)
        dY = (Pp - Ytr.T)/ntr
        gW2 = dY @ A1.T; gb2 = dY.sum(1, keepdims=True)
        dZ = (W2.T @ dY)*(1 - A1**2)
        gW1 = dZ @ Ztr.T; gb1 = dZ.sum(1, keepdims=True)
        for i, g in enumerate([gW1, gb1, gW2, gb2]):
            M[i] = 0.9*M[i] + 0.1*g; V[i] = 0.999*V[i] + 0.001*g**2
            P[i] -= 0.1*(M[i]/(1-0.9**(it+1)))/(np.sqrt(V[i]/(1-0.999**(it+1)))+1e-8)
    A1 = np.tanh(W1 @ Zte + b1); Yp = W2 @ A1 + b2
    return float((Yp.argmax(0) == yte).mean())


print('=' * 76)
print('灵光一闪测试 (修正): 关键信息只存在于提示里')
print('=' * 76)
print('  x 含 proj4; 类别需比较 proj4 和 proj5;  proj5 只在提示中')
print()
print('  %-30s %-12s %s' % ('提示 (只有4维)', '测试准确率', '说明'))
print('  ' + '-' * 70)
res = {}
for kind, nm in [('none', 'D 无提示 (基线)'),
                 ('self', 'A 自己投影 (无新信息)'),
                 ('world', '★B 外部真信息 (proj5)'),
                 ('rand', 'C 随机 4 维')]:
    a = run(kind)
    res[kind] = a
    print('  %-30s %-12.3f' % (nm, a))

print()
print('=' * 76)
print('提升幅度 (相对无提示)')
print('=' * 76)
for kind, nm in [('self', 'A 自己投影'), ('world', '★B 外部真信息'), ('rand', 'C 随机')]:
    d = res[kind] - res['none']
    print('  %-16s %+.3f  %s' % (nm, d,
          '★★ 巨大提升' if d > 0.15 else ('✅ 有效' if d > 0.05 else '❌ 无效')))

print()
print('  随机猜测 = 0.333')
print('  用时 %.2fs' % (time.time() - t0))
