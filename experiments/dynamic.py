#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dynamic.py — 广度/深度动态转换: 是不是免费午餐?
==================================================
用户想法: 需要广度时并行, 需要深度时把 N 个核串起来变成链长
本实验测: 这个转换是否有代价, 代价是什么

模型:
  总预算 = N × T  (N个核, 每个能跑T步)
  分配方式:
    A 广度模式: N 条路并行, 每条长 T
    B 深度模式: 1 条路, 长 N×T
    C 混合:     B1 条路, 每条长 N×T/B1
    
关键: 深度模式下, "把N个核串起来"能真的延长链吗?
问题: 核之间传递状态有损耗 (今天测过: 每步表示损失)

设计:
  · 每条链每步有成功率 p (受"传递损耗"影响)
  · 深度模式下, 核间传递导致 p 下降
  · 测: 深度模式的实际收益 vs 损耗
"""
import numpy as np, time

t0 = time.time()


def success_broad(N, T, p):
    """广度: N条独立路, 每条长T. 至少一条成功"""
    ps = p ** T
    return 1 - (1 - ps) ** N


def success_deep(NT, p_per_handoff, p_step):
    """
    深度: 一条链总长 NT
    但每跨一个核边界 (共 N-1 次交接), 有 p_per_handoff 的概率不丢失
    """
    p_total = (p_step ** NT) * (p_per_handoff ** max(0, 0))
    return p_total


def success_deep_lossy(N, T, p_step, p_handoff):
    """深度: 链长 N*T, 但每 T 步跨一次核, 交接成功率 p_handoff"""
    p = p_step ** (N * T)
    p *= p_handoff ** (N - 1)
    return p


print('=' * 78)
print('广度 vs 深度: 同样预算 N×T 下, 谁更容易成功?')
print('=' * 78)
print('  设定: 每步成功率 p_step=0.95, 核间交接成功率 p_handoff 变化')
print()
print('  %-8s %-8s %-14s %-14s %-14s %s' % ('N', 'T', '广度模式', '深度(无损耗)',
                                            '深度(交接0.99)', '胜者'))
print('  ' + '-' * 76)

for N, T in [(10, 10), (100, 10), (100, 30), (1000, 10)]:
    p_step = 0.95
    sb = success_broad(N, T, p_step)
    # 深度: 总链长 N*T (理论)
    sd_ideal = p_step ** (N * T)
    # 深度: 每 T 步交接, 交接成功率 0.99
    sd_real = (p_step ** (N * T)) * (0.99 ** (N - 1))
    win = '广度 ✅' if sb > max(sd_ideal, sd_real) else '深度'
    print('  %-8d %-8d %-14.2e %-14.2e %-14.2e %s' % (
        N, T, sb, sd_ideal, sd_real, win))

print()
print('=' * 78)
print('★ 关键: 深度模式需要的链长是多少?')
print('=' * 78)
print()
print('  %-14s %-20s %-20s' % ('目标成功率', '广度(100核x10步)', '深度(需多长链)'))
print('  ' + '-' * 58)
p = 0.95
for target in [0.5, 0.9, 0.99]:
    # 广度: N条T步
    N, T = 100, 10
    sb = success_broad(N, T, p)
    # 深度: 1条链需要多长
    L = np.log(target) / np.log(p)
    print('  %-14.2f %-20.2e 需 %.0f 步' % (target, sb, L))

print()
print('=' * 78)
print('★ 动态转换的真实代价 (决定可行性)')
print('=' * 78)
print()
print('  场景: 100个核 × 10步预算')
print('  %-24s %-18s %-18s %s' % ('模式', '广度成功率', '深度成功率', '对比'))
print('  ' + '-' * 70)
for h in [1.0, 0.999, 0.99, 0.95, 0.9]:
    sb = success_broad(100, 10, 0.95)
    sd = (0.95 ** 1000) * (h ** 99)
    r = sb / max(sd, 1e-300)
    print('  %-24s %-18.2e %-18.2e %s' % (
        '交接成功率 %.3f' % h, sb, sd, '广度赢 %.0e 倍' % r if r > 1 else '深度赢'))

print()
print('=' * 78)
print('结论')
print('=' * 78)
print('  ① 同样预算下, 广度的成功率远高于堆深度 (指数差异)')
print('  ② 深度模式有【交接损耗】: 每跨一个核损失一点, N个核损失 N-1 次')
print('     → 交接 0.99 时, 100核的交接损耗 = 0.99^99 ≈ 0.37 (损失 63%!)')
print('  ③ 所以"把N个核串起来"不是免费的: 串得越长, 损耗越大')
print()
print('  用时 %.2fs' % (time.time() - t0))
