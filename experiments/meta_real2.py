#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_real2.py — 真实多域超启发 (有区分度版)
=============================================
上一版失败: 所有策略 1.00 → 任务太简单, 无区分度

本版关键:
  · 搜索空间巨大 (±10^6) → 暴力枚举必然失败
  · 但部分域有【代数结构】→ 某些策略能一击命中
  · 传递链域是【组合结构】→ 需要"遍历比较"而不是代数

  → 每个策略在不同域上表现【真的不同】

4 训练域 × 4 策略, 测第 5 域
"""
import numpy as np, time

t0 = time.time()

# ==================== 域 ====================
def dom_algebra(n, r):
    """域1 代数方程: a*x+b=c, 空间巨大但可代数解"""
    out = []
    for _ in range(n):
        a = r.randint(2, 1001)
        x0 = r.randint(-10**6, 10**6)
        b = r.randint(-10**6, 10**6)
        out.append(dict(kind='alg', a=a, b=b, c=a*x0+b, a_val=x0))
    return out


def dom_mod(n, r):
    """域2 同余: a*x≡b (mod m)  — 可代数解 (扩展欧几里得近似)"""
    out = []
    for _ in range(n):
        m = r.randint(1000, 100000)
        a = r.randint(2, m)
        x0 = r.randint(0, m)
        out.append(dict(kind='mod', a=a, m=m, b=(a*x0) % m, a_val=x0))
    return out


def dom_chain(n, r):
    """域3 传递链: 给关系, 求最大 — 组合结构, 需遍历比较"""
    out = []
    for _ in range(n):
        m = r.randint(20, 60)
        vals = r.permutation(10000)[:m]
        out.append(dict(kind='chain', vals=vals, a_val=int(np.argmax(vals))))
    return out


def dom_dioph(n, r):
    """域4 丢番图: 3x+5y=c, 求最小非负 x — 线性代数"""
    out = []
    for _ in range(n):
        x0 = r.randint(0, 2000); y0 = r.randint(0, 2000)
        out.append(dict(kind='dio', c=3*x0+5*y0, a_val=x0))
    return out


def dom_quad_big(n, r):
    """★ 测试域: x²+bx+c=0, 大范围 — 结构接近域1但有平方项"""
    out = []
    for _ in range(n):
        x0 = r.randint(-10**5, 10**5)
        b = r.randint(-10**5, 10**5)
        out.append(dict(kind='quadbig', b=b, c=-(x0*x0 + b*x0), a_val=x0))
    return out


# ==================== 验证器 (可执行) ====================
def check(it, x):
    k = it['kind']
    if k == 'alg':      return it['a']*x + it['b'] == it['c']
    if k == 'mod':      return (it['a']*x) % it['m'] == it['b']
    if k == 'chain':    return x == it['a_val']
    if k == 'dio':      return 3*x + 5*0 == it['c'] - 5*0 if False else (it['c'] - 3*x) % 5 == 0 and (it['c'] - 3*x) >= 0
    if k == 'quadbig':  return x*x + it['b']*x + it['c'] == 0
    return False


# ==================== 4 个策略 (都是真实算法) ====================
def s_enum_small(it, B=400):
    """S0 小范围枚举: 只在 [-200,200] 找"""
    for x in range(-200, 201):
        B -= 1
        if B <= 0: break
        if check(it, x): return x
    return None


def s_algebra(it, B=400):
    """S1 代数解: 直接解方程 (考验结构性)"""
    k = it['kind']
    if k == 'alg':
        num = it['c'] - it['b']
        if num % it['a'] == 0: return num // it['a']
    if k == 'mod':
        a, m, b = it['a'], it['m'], it['b']
        g = np.gcd(a, m)
        if b % g == 0:
            for x in range(0, min(m, B)):
                if (a*x) % m == b: return x
    if k == 'dio':
        c = it['c']
        for x in range(0, min(200000, B*100)):
            if (c - 3*x) % 5 == 0 and (c - 3*x) >= 0: return x
    if k == 'quadbig':
        b, c = it['b'], it['c']
        disc = b*b - 4*c
        if disc >= 0:
            rt = int(round(disc ** 0.5))
            if rt*rt == disc:
                for x in (( -b+rt)//2, (-b-rt)//2):
                    if check(it, x): return x
    return None


def s_enumerate_all(it, B=400):
    """S2 全遍历比较: 对链有效, 对其他域无效 (空间太大)"""
    if it['kind'] == 'chain':
        return int(np.argmax(it['vals']))
    return None


def s_random_wide(it, B=400, seed=0):
    """S3 大范围随机: 对中等密度有效"""
    r = np.random.RandomState(seed)
    for _ in range(B):
        x = int(r.randint(-10**6, 10**6))
        if check(it, x): return x
    return None


STRATS = [('小范围枚举', s_enum_small), ('代数解', s_algebra),
          ('遍历比较', s_enumerate_all), ('大范围随机', s_random_wide)]
DOMS = [('代数方程', dom_algebra), ('同余', dom_mod),
        ('传递链', dom_chain), ('丢番图', dom_dioph)]
TEST = ('大二次方程', dom_quad_big)


# ==================== 域特征: 从数据测 ====================
def features(items, r):
    # ① 小范围枚举的成功率 (测"解是否在近处")
    ok = sum(1 for it in items[:25] if s_enum_small(dict(it)) is not None)
    f1 = ok / 25.0
    # ② 代数解的成功率 (测"是否有代数结构")
    ok = sum(1 for it in items[:25] if s_algebra(dict(it)) is not None)
    f2 = ok / 25.0
    # ③ 随机命中的概率 (测"解密度")
    hits = 0
    for it in items[:15]:
        for _ in range(20):
            x = int(r.randint(-10**6, 10**6))
            if check(it, x): hits += 1
    f3 = hits / (15 * 20.0)
    # ④ 值的量级 (测"搜索空间规模")
    f4 = np.log10(1 + np.mean([abs(it.get('c', 0)) + abs(it.get('b', 0)) + abs(it.get('m', 0))
                               for it in items[:15]]))
    return np.array([f1, f2, f3, f4])


r = np.random.RandomState(7)
print('=' * 92)
print('真实多域超启发 (有区分度): 4 训练域 → 预测第 5 域')
print('=' * 92)
print()

X = np.zeros((len(DOMS), 4))
Y = np.zeros((len(DOMS), 4))
print('  %-10s %-22s %s' % ('域', '特征[f1 f2 f3 f4]', '各策略成功率'))
print('  ' + '-' * 88)
for di, (nm, gen) in enumerate(DOMS):
    items = gen(60, r)
    X[di] = features(items, r)
    row = []
    for si, (sn, sf) in enumerate(STRATS):
        ok = 0
        for i, it in enumerate(items[:40]):
            x = sf(dict(it), 400, seed=i) if sf is s_random_wide else sf(dict(it), 400)
            if x is not None: ok += 1
        Y[di, si] = ok / 40.0
        row.append('%.2f' % Y[di, si])
    print('  %-10s %-22s %s  最优→%s' % (
        nm, np.array2string(X[di], precision=2), ' '.join(row),
        STRATS[int(np.argmax(Y[di]))][0]))

W = np.zeros((4, 4))
for si in range(4):
    W[:, si] = np.linalg.lstsq(X, Y[:, si], rcond=None)[0]

print()
print('=' * 92)
print('预测第 5 域: 大范围二次方程 (训练时未见, 结构介于域1和域4之间)')
print('=' * 92)
nm, gen = TEST
items = gen(60, r)
ft = features(items, r)
print('  特征: %s' % np.array2string(ft, precision=2))
print()

real = []
for si, (sn, sf) in enumerate(STRATS):
    ok = 0
    for i, it in enumerate(items[:40]):
        x = sf(dict(it), 400, seed=500 + i) if sf is s_random_wide else sf(dict(it), 400)
        if x is not None: ok += 1
    real.append(ok / 40.0)
real = np.array(real)
sc = ft @ W
pick = int(np.argmax(sc)); best = int(np.argmax(real))

print('  %-14s %-14s %-16s' % ('策略', '预测得分', '真实成功率'))
for si, (sn, sf) in enumerate(STRATS):
    tag = ' ←选择器' if si == pick else (' ←真实最优' if si == best else '')
    print('  %-14s %-14.3f %-16.3f%s' % (sn, sc[si], real[si], tag))
print()
print('  选择器选: %s (%.3f)' % (STRATS[pick][0], real[pick]))
print('  真实最优: %s (%.3f)' % (STRATS[best][0], real[best]))
print('  随机期望: %.3f' % real.mean())
print()
print('  → 相对最优: %+.3f    相对随机: %+.3f' % (
    real[pick] - real[best], real[pick] - real.mean()))
print('  → %s' % ('✅ 超启发成立 (选到/接近最优)' if real[pick] >= real[best] - 0.08
                 else '❌ 未命中'))
print()
print('  用时 %.2fs' % (time.time() - t0))
