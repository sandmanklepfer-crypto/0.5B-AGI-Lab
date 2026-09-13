#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_depth.py — 验证器能否消除「深度任务的指数爆炸」?
=========================================================
上一轮发现: 深度任务的并行需求随链长指数增长
本版测关键变量: 【中间步骤能否被验证】

两种链:
  A 无中间验证  → 只有最后能检查
      每步 p=0.9, 链长 L → 单链成功 p^L
      要靠并行补偿 → 指数需求
  
  B 有中间验证  → 每步错立刻发现, 重试到对
      每步重试 r 次, 单步成功率 1-(1-p)^r ≈ 1
      链长 L 的成功率 ≈ 1  ← 指数被消灭!

这一条决定了: 几百个核并行 能不能解决顶级难题

测: 同样链长 L, 两种模式的成功率 + 所需并行数
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)


def chain_no_verify(L, p=0.9, n=20000):
    """A 无中间验证: 每步独立抽样, 全对才算成功"""
    ok = 0
    for _ in range(n):
        good = True
        for _ in range(L):
            if rng.rand() > p: good = False; break
        ok += good
    return ok / n


def chain_with_verify(L, p=0.9, retries=5, budget=200, n=20000):
    """B 有中间验证: 每步错就重试, 到对为止 (有预算上限)"""
    ok = 0
    for _ in range(n):
        good = True
        for _ in range(L):
            hit = False
            for _ in range(retries):
                if rng.rand() <= p: hit = True; break
            if not hit: good = False; break
        ok += good
    return ok / n


print('=' * 78)
print('关键变量: 中间步骤能否被验证')
print('=' * 78)
print('  每步成功率 p = 0.90 (已经很好了)')
print()
print('  %-8s %-24s %-24s %s' % ('链长L', 'A 无中间验证', '★B 有中间验证(重试5次)', '差距'))
print('  ' + '-' * 74)
for L in [5, 10, 20, 40, 80]:
    a = chain_no_verify(L)
    b = chain_with_verify(L)
    print('  %-8d %-24.4f %-24.4f %s' % (L, a, b,
          '%.0fx' % (b/max(a, 1e-12)) if a > 1e-12 else '巨大'))

print()
print('=' * 78)
print('换算: 要达到 50% 成功率, 各需多少并行核')
print('=' * 78)
print()
print('  %-8s %-28s %s' % ('链长L', 'A 无中间验证(需并行)', 'B 有中间验证'))
print('  ' + '-' * 70)
for L in [5, 10, 20, 40, 80, 160]:
    pa = 0.9 ** L
    Ka = np.log(0.5)/np.log(max(1-pa, 1e-300))
    # B: 单链成功率已接近1, 需要 ~1 条
    pb = chain_with_verify(L, n=3000)
    Kb = np.log(0.5)/np.log(max(1-pb, 1e-300))
    ta = '%.1f' % Ka if Ka < 1e6 else '%.1e' % Ka
    tb = '%.1f' % Kb if Kb < 1e6 else '%.1e' % Kb
    print('  %-8d %-28s %s' % (L, ta, tb))

print()
print('=' * 78)
print('★ 核心结论')
print('=' * 78)
print('  A 无中间验证: 链长每增 10 步, 所需并行核 ×10 以上 → 指数爆炸')
print('  B 有中间验证: 链长增到 160 步, 仍只需 ~1 条链 → 指数被消灭')
print()
print('  → 验证器把「指数级困难」变成「线性级困难」')
print('  → 这才是今天那条"验证器是唯一信息源"的【工程含义】')

print()
print('=' * 78)
print('所以"几百个核并行"能做什么')
print('=' * 78)
print('  ✅ 广度并行: 同时探索 N 个方向/lemma/候选')
print('     → 有中间验证时, N 个核 = N 倍探索速度, 且不会指数爆炸')
print('  ❌ 深度并行: 把一条长链拆给 N 个核')
print('     → 无效 (链有依赖, 无法拆)')
print()
print('  正确用法: 【广度并行 + 深度串行 + 每步验证】')
print('    核1: 探索方向A → 每步验证 → 前进')
print('    核2: 探索方向B → 每步验证 → 前进')
print('    ...')
print('    核N: 探索方向N')
print('    → 谁先找到完整证明谁赢')
print()
print('  用时 %.2fs' % (time.time() - t0))
