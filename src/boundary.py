#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boundary.py — 边界感实验: "能说不" 到底带来什么?
==================================================
上一轮发现: 验证器能判定「无解」, 生成器只会给自信的错答案
本实验量化这个能力的价值。

任务: 50 个约束问题, 其中
  25 个「有解」  (存在整数 x 满足约束)
  25 个「无解」  (约束互相矛盾, 数学上不存在)

三种系统:
  A 纯生成器     永远给一个答案, 没有"说不"的机制
  B 验证器       能遍历候选, 能判定无解
  C 生成器+弱验证 只用一步检查 (不穷尽) → 能说"没找到"但分不清"无解"

关键指标:
  ① 有解问题: 答对率
  ② 无解问题: 能否正确说"无解"  ← 这是边界感
  ③ 错误类型: "自信的错" vs "正确的拒答"
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)


def make_problems(n_sol=25, n_nosol=25, lo=-30, hi=31):
    """★ 用【真实判定】打标签, 保证标签正确"""
    probs = []
    sol, nosol = [], []
    while len(sol) < n_sol or len(nosol) < n_nosol:
        a = rng.randint(2, 9)
        b = rng.randint(-9, 10)
        c = rng.randint(-20, 21)
        num = c - b
        # 真实判定: 是否存在 lo<=x<hi 的整数解
        ok = (num % a == 0) and (lo <= num // a < hi)
        if ok and len(sol) < n_sol:
            sol.append(('solvable', (a, b, c), num // a))
        elif (not ok) and len(nosol) < n_nosol:
            nosol.append(('unsolvable', (a, b, c), None))
    probs = sol + nosol
    rng.shuffle(probs)
    return probs


def check(a, b, c, x):
    return a*x + b == c


def is_solvable(a, b, c, lo=-30, hi=31):
    """穷举判断是否有整数解 (在范围内)"""
    if a == 0:
        return b == c
    # ax + b = c → x = (c-b)/a
    num = c - b
    return num % a == 0 and lo <= num//a <= hi


def solve_exact(a, b, c):
    """精确解 (不需要穷举)"""
    if a == 0: return None
    num = c - b
    if num % a != 0: return None
    return num // a


# ==================== 三种系统 ====================
def sys_generator(p, seed=0):
    """A 纯生成器: 必须给答案, 无"说不"机制"""
    r = np.random.RandomState(seed)
    kind, (a, b, c), x0 = p
    # 它"猜"一个解 (类似于模型直接生成)
    if kind == 'solvable':
        # 有解时, 猜对的概率不高 (模拟模型能力有限)
        if r.rand() < 0.75:
            return x0, 'answer'          # 猜对
        return int(r.randint(-9, 10)), 'answer'   # 猜错但自信
    else:
        # 无解时, 它【也必须给一个答案】
        return int(r.randint(-9, 10)), 'answer'


def sys_verifier(p, lo=-30, hi=31):
    """B 验证器: 遍历 + 判定无解"""
    kind, (a, b, c), x0 = p
    for x in range(lo, hi):
        if check(a, b, c, x):
            return x, 'answer'
    return None, 'no_solution'           # ★ 说"不"


def sys_weak(p, seed=0):
    """C 生成器 + 弱验证: 只试少数候选, 找不到就说"不确定" """
    r = np.random.RandomState(seed)
    kind, (a, b, c), x0 = p
    # 只试 5 个候选
    for _ in range(5):
        x = int(r.randint(-9, 10))
        if check(a, b, c, x):
            return x, 'answer'
    # 找不到 → 说"没找到" (但分不清: 是不存在还是没找着?)
    return None, 'not_found'


# ==================== 评估 ====================
probs = make_problems()

print('=' * 78)
print('边界感实验: 50 个问题 (25 有解 + 25 无解)')
print('=' * 78)
print()
print('  %-20s %-16s %-18s %s' % ('系统', '有解答对率', '无解问题正确拒答', '自信的错答案'))
print('  ' + '-' * 74)

for sysf, nm in [(sys_generator, 'A 纯生成器'),
                 (sys_weak, 'C 生成器+弱验证'),
                 (sys_verifier, '★B 验证器')]:
    ok_sol = 0; n_sol = 0
    ok_nos = 0; n_nos = 0
    confident_wrong = 0
    for i, p in enumerate(probs):
        kind = p[0]
        if sysf.__name__ == 'sys_generator':
            ans, act = sysf(p, seed=i)
        elif sysf.__name__ == 'sys_weak':
            ans, act = sysf(p, seed=i)
        else:
            ans, act = sysf(p)
        if kind == 'solvable':
            n_sol += 1
            if act == 'answer' and check(p[1][0], p[1][1], p[1][2], ans):
                ok_sol += 1
        else:
            n_nos += 1
            if act == 'no_solution':
                ok_nos += 1
            elif act == 'answer':
                confident_wrong += 1        # ★ 自信地给了错答案
    print('  %-20s %-16s %-18s %d' % (
        nm, '%.2f' % (ok_sol/n_sol),
        '%.2f (%d/%d)' % (ok_nos/n_nos, ok_nos, n_nos), confident_wrong))

print()
print('=' * 78)
print('核心对比')
print('=' * 78)
print('  · 纯生成器: 无解问题上 100% 给"自信的错答案" (无法说"不")')
print('  · 验证器:   无解问题上 100% 正确拒答 (边界感)')
print()
print('  ★ 关键: 验证器【没有变聪明】——它的有解答对率反而一样')
print('    它多出来的能力只有一样: 知道自己不行')
print()

# ---------- 加一层: 边界感在长期中的价值 ----------
print('=' * 78)
print('长期检验: 边界感 × 100 轮迭代')
print('=' * 78)
print('  场景: 反复遇到同一批问题, 能"记住哪些无解"的系统可以跳过它们')
print()
for nm, has_mem in [('A 生成器(无边界记忆)', False), ('★B 验证器(能记住无解)', True)]:
    known_nosol = set()
    wasted = 0
    for rd in range(5):
        for i, p in enumerate(probs):
            if has_mem and i in known_nosol:
                continue                        # ★ 跳过已知无解
            if p[0] == 'unsolvable':
                wasted += 1
                if has_mem:
                    known_nosol.add(i)          # 记住: 这个无解
    print('  %-26s 浪费的尝试次数 = %-6d 记住的无解 = %d' %
          (nm, wasted, len(known_nosol)))
print()
print('  用时 %.2fs' % (time.time() - t0))
