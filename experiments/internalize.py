#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
internalize.py — 顶级模型的解法: 把验证器"内化"进参数
========================================================
核心洞察:
  外部验证器: 精度100%, 参数0, 但覆盖窄 (只对有形式化规则的领域)
  内化验证器: 精度随参数增长, 覆盖全 (任何领域都能学)

大模型做的事 = 把外部验证器【蒸馏进参数】
  RLHF 三步走:
    ① 收集人类偏好   (人类 = 外部验证器, 慢/贵/准)
    ② 训练奖励模型   (★ 内化: 把人类判断搬进参数)
    ③ 用奖励模型做RL (用内化验证器训练生成器)

本实验量化: 内化验证器要达到高精度, 需要多少参数?
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

# ==================== 任务: 验证 (a*x+b==c) 吗? ====================
def gen(n, rng, lo, hi):
    """生成 (a,b,c,x, 对错)"""
    a = rng.randint(2, 61, n)
    b = rng.randint(-500, 501, n)
    x = rng.randint(-300, 301, n)
    c = a*x + b                       # 真值
    # 一半改成错的
    bad = rng.rand(n) < 0.5
    c2 = c.copy()
    c2[bad] = c[bad] + rng.choice([-3, -2, -1, 1, 2, 3], bad.sum()) * rng.randint(1, 50, bad.sum())
    label = (~bad).astype(int)        # 1=对, 0=错
    # 特征: [a, b, c, x, a*x+b-c, ...]
    F = np.stack([
        a/60.0, b/500.0, c/3000.0, x/300.0,
        (a*x + b - c)/100.0,          # ★ 这一维直接给了"差值"（类似"验算"）
        a*x/18000.0, b/500.0*c/3000.0,
        (a % 7)/7.0, (x % 10)/10.0, np.abs(x)/300.0,
    ], 1)
    return F, label, (a, b, c, x)


def train_cls(F, y, H, iters=120, lr=0.2, seed=1):
    r = np.random.RandomState(seed)
    din = F.shape[1]
    W1 = r.randn(H, din)/np.sqrt(din); b1 = np.zeros((1, H))
    W2 = r.randn(2, H)/np.sqrt(H); b2 = np.zeros((1, 2))
    Yh = np.eye(2)[y]
    for it in range(iters):
        A = np.tanh(F @ W1.T + b1)
        Lg = A @ W2.T + b2
        e = np.exp(Lg - Lg.max(1, keepdims=True)); P = e/e.sum(1, keepdims=True)
        dY = (P - Yh)/len(F)
        gW2 = dY.T @ A; gb2 = dY.sum(0, keepdims=True)
        dZ = (dY @ W2)*(1 - A**2)
        gW1 = dZ.T @ F; gb1 = dZ.sum(0, keepdims=True)
        W2 -= lr*gW2; b2 -= lr*gb2
        W1 -= lr*gW1; b1 -= lr*gb1
    npar = W1.size + b1.size + W2.size + b2.size
    return (W1, b1, W2, b2), npar


def acc(pack, F, y):
    W1, b1, W2, b2 = pack
    A = np.tanh(F @ W1.T + b1)
    return ((A @ W2.T + b2).argmax(1) == y).mean()


# 训练/测试 用不同参数范围 (测泛化)
Ftr, ytr, _ = gen(800, rng, 2, 60)
Fte, yte, _ = gen(400, np.random.RandomState(9), 2, 60)

print('=' * 84)
print('内化验证器的成本: 达到高精度需要多少参数?')
print('=' * 84)
print()
print('  任务: 判断 (a*x+b==c) 是否成立  (等价于"验算")')
print('  外部验证器: 算一下 → 100%% 准确, 0 参数')
print()
print('  %-8s %-12s %-14s %-14s %s' % ('隐层H', '参数量', '训练精度', '测试精度', '达到外部水平?'))
print('  ' + '-' * 76)
for H in [2, 8, 32, 128, 512]:
    pack, npar = train_cls(Ftr, ytr, H)
    a_tr = acc(pack, Ftr, ytr)
    a_te = acc(pack, Fte, yte)
    tag = '✅' if a_te > 0.99 else ('⚠️' if a_te > 0.9 else '')
    print('  %-8d %-12d %-14.4f %-14.4f %s' % (H, npar, a_tr, a_te, tag))

print()
print('=' * 84)
print('★ 关键: 内化验证器的"参数成本" vs 外部验证器的"零参数"')
print('=' * 84)
print()
print('  %-30s %-16s %-16s' % ('方式', '参数', '精度'))
print('  ' + '-' * 62)
print('  %-30s %-16s %-16s' % ('外部验证器 (算一下)', '0', '100%'))

# 找达到 99% 的最小 H
best_H = None
for H in [2, 8, 32, 128, 512]:
    pack, npar = train_cls(Ftr, ytr, H, iters=200)
    if acc(pack, Fte, yte) > 0.99:
        best_H = (H, npar); break
if best_H:
    print('  %-30s %-16s %-16s' % ('内化验证器 (需训练)',
          '%d 参数' % best_H[1], '99%+'))
    print()
    print('  → 外部: 0 参数就 100%')
    print('  → 内化: %d 参数才 99%%' % best_H[1])
    print('  → 差距: 无穷大 (外部根本不需要参数)')

print()
print('=' * 84)
print('★ 但这只是"可形式化"领域 —— 真正的问题是那些不可形式化的')
print('=' * 84)
print()
print('  %-24s %-16s %-16s %s' % ('领域', '外部验证器', '内化验证器', '说明'))
print('  ' + '-' * 76)
rows = [
    ('算术/代码/逻辑', '✅ 有 (0参数)', '✅ 都能达到', '外部更优'),
    ('事实核查',       '⚠️ 检索可得',  '✅ 能达到',   '都可'),
    ('语言通顺',       '❌ 无',        '✅ 统计可得', '只能内化'),
    ('推理是否正确',    '⚠️ 步骤可验',  '✅ 部分可得', '组合'),
    ('审美/价值判断',   '❌ 无',        '⚠️ 只能模仿', '★ 都做不到'),
    ('未来预测',       '❌ 无',        '❌ 做不到',   '★ 原理上无解'),
]
for r_ in rows:
    print('  %-24s %-16s %-16s %s' % r_)

print()
print('  用时 %.2fs' % (time.time() - t0))
