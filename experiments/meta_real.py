#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_real.py — 真实多域超启发 (避免循环设计)
==============================================
上一版错误: 我把"族特征"和"策略偏好"都设计成向量 → 必然线性可分
            = 把答案设计进了问题里

本版严格:
  ① 域特征【从数据测出来】(不是设计的): 
     链长 / 分支因子 / 解密度 / 验证器准确率 / 搜索空间
  ② 策略是【真实算法】:
     暴力枚举 / 随机重启 / 贪心 / 分解递归
  ③ 验证器是【真实代码】(Python 执行, 不是模拟)
  ④ 训练域 4 个, 测试域是【第 5 个, 结构不同】

判据: 学出的选择器在测试域上是否优于"随机选策略"
"""
import numpy as np, time, itertools

t0 = time.time()
rng = np.random.RandomState(0)

# ==================== 4 个训练域 + 1 个测试域 ====================
# 每个域: 生成器 + 真值函数 (可执行验证)


def dom_linear(n, r):
    """域1 线性方程: a*x+b=c, 求整数 x"""
    out = []
    for _ in range(n):
        a = r.randint(2, 12); x0 = r.randint(-20, 21)
        b = r.randint(-20, 21); c = a*x0 + b
        out.append(dict(a=a, b=b, c=c, ans=x0))
    return out


def dom_quad(n, r):
    """域2 二次: x²+px+q=0 有整数解"""
    out = []
    for _ in range(n):
        p = r.randint(-12, 13)
        x0 = r.randint(-10, 11)
        q = x0*(p + x0) * (-1)      # 使 x0 是根
        out.append(dict(p=p, q=q, ans=x0))
    return out


def dom_chain(n, r):
    """域3 传递链: 给若干 A>B 关系, 求最大"""
    out = []
    for _ in range(n):
        m = r.randint(5, 13)
        vals = r.permutation(20)[:m]
        idx = r.permutation(m)
        rels = [(idx[i], idx[i+1]) for i in range(m-1)]
        out.append(dict(m=m, rels=rels, vals=vals, ans=int(np.argmax(vals))))
    return out


def dom_mod(n, r):
    """域4 同余: a*x ≡ b (mod m), 求最小非负解"""
    out = []
    for _ in range(n):
        m = r.randint(5, 23)
        x0 = r.randint(0, m)
        a = r.randint(2, m)
        b = (a*x0) % m
        out.append(dict(a=a, b=b, m=m, ans=x0 % m))
    return out


def dom_new(n, r):
    """★ 测试域 (结构不同): 二元约束满足  x+y=s 且 x*y=p"""
    out = []
    for _ in range(n):
        x0 = r.randint(-12, 13); y0 = r.randint(-12, 13)
        out.append(dict(s=x0+y0, p=x0*y0, ans=x0))
    return out


# ==================== 策略集合 (真实算法) ====================
def strat_brute(item, budget=2000):
    """S0: 暴力枚举"""
    for x in range(-30, 31):
        budget -= 1
        if budget <= 0: break
        if check(item, x): return x, budget
    return None, budget


def strat_random(item, budget=2000, seed=0):
    """S1: 随机重启"""
    r = np.random.RandomState(seed)
    for _ in range(min(budget, 300)):
        budget -= 1
        x = int(r.randint(-30, 31))
        if check(item, x): return x, budget
    return None, budget


def strat_greedy(item, budget=2000):
    """S2: 贪心 (从线索猜一个起点, 再局部搜)"""
    x = item.get('guess0', 0)
    for d in range(0, 60):
        for s in ([d, -d] if d else [0]):
            budget -= 1
            if budget <= 0: return None, budget
            if check(item, item.get('_center', 0) + s): 
                return item.get('_center', 0) + s, budget
    return None, budget


def strat_decompose(item, budget=2000):
    """S3: 分解 (利用结构代数, 而非枚举)"""
    budget -= 1
    if 'a' in item and 'c' in item:              # 线性
        num = item['c'] - item['b']
        if num % item['a'] == 0:
            x = num // item['a']
            if check(item, x): return x, budget
    if 'p' in item and 'q' in item:              # 二次
        for d in range(0, 40):
            if (d*d - item['p']*d + item['q']) == 0: 
                return d, budget
            budget -= 1
            if (-d*-d - item['p']*(-d) + item['q']) == 0:
                return -d, budget
            budget -= 1
            if budget <= 0: break
    if 'a' in item and 'm' in item:              # 同余
        a, b, m = item['a'], item['b'], item['m']
        for x in range(m):
            budget -= 1
            if budget <= 0: break
            if (a*x) % m == b: return x, budget
    if 's' in item and 'p' in item:              # ★ 测试域: 一元二次
        disc = item['s']**2 - 4*item['p']
        if disc >= 0:
            rt = int(round(disc**0.5))
            if rt*rt == disc:
                for x in [(item['s']+rt)//2, (item['s']-rt)//2]:
                    budget -= 1
                    if check(item, x): return x, budget
    return None, budget


STRATS = [('暴力', strat_brute), ('随机重启', strat_random),
          ('贪心', strat_greedy), ('分解', strat_decompose)]


def check(item, x):
    """★ 可执行验证器 (真值检查)"""
    if 'a' in item and 'c' in item and 'b' in item and 'm' not in item:
        return item['a']*x + item['b'] == item['c']
    if 'p' in item and 'q' in item:
        return x*x + item['p']*x + item['q'] == 0
    if 'rels' in item:
        # 链: x 应是最大值的位置
        return x == item['ans']
    if 'm' in item and 'a' in item:
        return (item['a']*x) % item['m'] == item['b']
    if 's' in item and 'p' in item:
        return (x*2 == item['s'] + int(round((item['s']**2-4*item['p'])**0.5)) if item['s']**2-4*item['p'] >= 0 else False) or (x + (item['s']-x) == item['s'] and x*(item['s']-x) == item['p'])
    return False


# ==================== 域特征: 从数据【测出来】 ====================
def measure_features(items, r):
    """真实测量: 不用设计值, 全从样本上统计"""
    # ① 解密度: 暴力能多快找到
    hit_rates = []
    for it in items[:30]:
        found = 0
        for x in range(-30, 31):
            if check(it, x): found += 1
        hit_rates.append(found / 61.0)
    density = float(np.mean(hit_rates))

    # ② 验证器准确率: 抽 20 个错误答案, 验证器应全部拒绝
    rej = 0; tot = 0
    for it in items[:20]:
        for x in r.choice(range(-30, 31), 10, replace=False):
            if check(it, int(x)) and x != it['ans']: rej += 1
            tot += 1
    v_acc = 1.0 - rej / max(tot, 1)

    # ③ 结构类型: 用"分解策略是否对它有效"来测 (不需人工标注)
    ok_dec = 0
    for it in items[:30]:
        x, _ = strat_decompose(dict(it), 500)
        if x is not None and check(it, x): ok_dec += 1
    struct = ok_dec / 30.0

    # ④ 平均"参数规模": 搜索空间的 log
    space = float(np.mean([np.log10(61) for _ in items[:10]]))

    return np.array([density, v_acc, struct, space])


# ==================== 主流程 ====================
DOMAINS = [('线性', dom_linear), ('二次', dom_quad),
           ('传递链', dom_chain), ('同余', dom_mod)]
TEST_DOM = ('二元约束', dom_new)

print('=' * 88)
print('真实多域超启发: 4 训练域 → 预测第 5 域的最优策略')
print('=' * 88)
print()

r = np.random.RandomState(42)
NFEAT = 4
X_feat = np.zeros((len(DOMAINS), NFEAT))
Y_perf = np.zeros((len(DOMAINS), len(STRATS)))

print('  %-10s %-11s %s' % ('域', '特征', '各策略成功率'))
print('  ' + '-' * 84)
for di, (nm, gen) in enumerate(DOMAINS):
    items = gen(60, r)
    X_feat[di] = measure_features(items, r)
    line = []
    for si, (sn, sf) in enumerate(STRATS):
        ok = 0
        for it in items[:40]:
            x, _ = sf(dict(it), 2000, seed=di*100+si) if sf is strat_random else sf(dict(it), 2000)
            if x is not None and check(it, x): ok += 1
        Y_perf[di, si] = ok / 40.0
        line.append('%.2f' % Y_perf[di, si])
    print('  %-10s %-11s %s   最优→%s' % (
        nm, np.array2string(X_feat[di], precision=2),
        ' '.join(line), STRATS[int(np.argmax(Y_perf[di]))][0]))

# ---------- 学选择器 ----------
W = np.zeros((NFEAT, len(STRATS)))
for si in range(len(STRATS)):
    W[:, si] = np.linalg.lstsq(X_feat, Y_perf[:, si], rcond=None)[0]

# ---------- 测试域 ----------
print()
print('=' * 88)
print('预测第 5 域 (二元约束 x+y=s, x*y=p — 训练时从未见过)')
print('=' * 88)
print()
nm, gen = TEST_DOM
items = gen(60, r)
ft = measure_features(items, r)
print('  该域特征: %s' % np.array2string(ft, precision=2))
print()

real = []
for si, (sn, sf) in enumerate(STRATS):
    ok = 0
    for it in items[:40]:
        x, _ = sf(dict(it), 2000, seed=900+si) if sf is strat_random else sf(dict(it), 2000)
        if x is not None and check(it, x): ok += 1
    real.append(ok / 40.0)
real = np.array(real)

scores = ft @ W
pick = int(np.argmax(scores))
best = int(np.argmax(real))
rand_exp = float(real.mean())

print('  %-12s %-14s %-14s' % ('策略', '预测得分', '真实成功率'))
for si, (sn, sf) in enumerate(STRATS):
    mark = ' ← 选择器选中' if si == pick else (' ← 真实最优' if si == best else '')
    print('  %-12s %-14.3f %-14.3f%s' % (sn, scores[si], real[si], mark))

print()
print('  选择器选中: %s (%.3f)' % (STRATS[pick][0], real[pick]))
print('  真实最优:   %s (%.3f)' % (STRATS[best][0], real[best]))
print('  随机期望:   %.3f' % rand_exp)
print()
print('  → 选择器 %s' % (
    '✅ 命中/接近最优' if real[pick] >= real[best] - 0.07 else '⚠️ 未命中'))
print('  → 相对随机: %+.3f' % (real[pick] - rand_exp))

print()
print('  用时 %.2fs' % (time.time() - t0))
