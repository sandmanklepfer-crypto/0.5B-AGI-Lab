#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler3.py — 调度器 (正确模型: 候选生成是有限资源)
========================================================
之前全返回 1.0 的原因: 我把"重试"当成免费的。
真实约束: 每一步生成候选都要花算力。

正确的资源账:
  总候选预算 B = 核数 N × 每核产出 T
  一条链需要 L 步, 每步生成 K 个候选 → 消耗 L×K
  能跑的链数 n = B / (L×K)

  ★ 关键权衡 (K 的两面):
    K 大 → 每步更容易命中正确候选 → 单链成功率高, 但链数少
    K 小 → 每步更易出错 → 但能多撒种子

  单步命中率 = 1-(1-q·v)^K     (q=生成器给对的概率, v=验证器认可率)
  单链成功率 = 单步命中率^L
  总成功率   = 1-(1-单链成功率)^n

这样 K 有最优值, 不同任务会给出真实差异。
"""
import numpy as np, time

t0 = time.time()

VERIFY = {'L1 可执行': 1.000, 'L2 形式检查': 0.990, 'L3 检索比对': 0.970,
          'L4 交叉一致': 0.900, 'L5 偏好排序': 0.750}
# 可重试性 = 每步能生成多少【有意义的不同】候选
#   广度型: 换方向就是新候选 → 高
#   深度型: 每步换个做法 → 中
#   单点型: 一步洞察无法"多生成" → 极低
RETRYABLE = {'广度型': 1.0, '混合型': 0.6, '深度型': 0.35, '单点型': 0.08}
BASE_LEN = {'广度型': 20, '混合型': 30, '深度型': 60, '单点型': 3}


def simulate(task_type, level, N, T, q=0.9, complexity=1.0, verbose=False):
    L = int(BASE_LEN[task_type] * complexity)
    v = VERIFY[level]
    retryable = RETRYABLE[task_type]
    B = N * T                                   # 总候选预算

    best = None
    for K in [1, 2, 3, 5, 8, 13, 21, 34]:       # 每步候选数
        K_eff = 1 + (K - 1) * retryable         # 可重试性折减
        p_step = 1 - (1 - q * v) ** K_eff       # 单步命中率
        p_chain = p_step ** L                   # 单链成功率
        n_chains = max(1.0, B / (L * K))        # 能跑的链数
        if p_chain >= 1.0:
            P = 1.0
        else:
            P = 1 - (1 - p_chain) ** n_chains
        if best is None or P > best[0]:
            best = (P, K, p_step, p_chain, n_chains)

    P, K, p_step, p_chain, n = best
    if P >= 0.9:   vd, act = '✅ 可行',    '直接执行'
    elif P >= 0.5: vd, act = '⚠️ 勉强',   '加核 / 提验证等级'
    else:          vd, act = '❌ 需外援', '上报大模型或人'
    return dict(L=L, v=v, K=K, p_step=p_step, p_chain=p_chain,
                n=n, P=P, verdict=vd, action=act)


print('=' * 100)
print('任务调度器 (正确模型: 候选预算有限, 重试有成本)')
print('=' * 100)
print('  预算: 每核产出 %d 候选, 生成器 q=0.90' % 300)
print()
print('  %-6s %-12s %-6s %-6s %-9s %-7s %-9s %-11s %-9s %s' % (
    '类型', '验证', '核数', '链长', '单步命中', '最优K', '单链成功', '可跑链数', '总成功', '判定'))
print('  ' + '-' * 96)

cases = [
    ('广度型', 'L1 可执行',   200, 1.0, '代码重构 20 处调用点'),
    ('广度型', 'L2 形式检查', 200, 1.5, '语法/结构修复 30 处'),
    ('混合型', 'L1 可执行',   200, 1.0, 'IMO 数学题 (lemma 枚举)'),
    ('深度型', 'L1 可执行',   200, 1.0, '50 步依赖重构 (每步可编译)'),
    ('深度型', 'L4 交叉一致', 200, 1.0, '开放推理链 60 步 (只能投票)'),
    ('单点型', 'L5 偏好排序', 200, 1.0, '选研究方向'),
]
R = []
for tt, lv, N, cx, desc in cases:
    r = simulate(tt, lv, N, 300, complexity=cx)
    R.append((tt, lv, N, cx, desc, r))
    print('  %-6s %-12s %-6d %-6d %-9.5f %-7d %-9.5f %-11.0f %-9.5f %s' % (
        tt, lv, N, r['L'], r['p_step'], r['K'], r['p_chain'], r['n'], r['P'], r['verdict']))

print()
print('=' * 100)
print('★ 三档分类 (调度器真正的输出)')
print('=' * 100)
buckets = {'✅ 可行': [], '⚠️ 勉强': [], '❌ 需外援': []}
for tt, lv, N, cx, desc, r in R:
    buckets[r['verdict']].append((desc, r['P']))
for k in ['✅ 可行', '⚠️ 勉强', '❌ 需外援']:
    print()
    print('  %s' % k)
    for d, p in buckets[k]:
        print('    · %-32s 预测成功率 %.4f' % (d, p))

print()
print('=' * 100)
print('★ 核数的作用 (同一任务, 扫核数)')
print('=' * 100)
print('  %-14s %-30s %s' % ('核数', '50步重构(L1)', '开放推理60步(L4)'))
for N in [1, 10, 50, 200, 1000]:
    a = simulate('深度型', 'L1 可执行', N, 300, complexity=1.0)
    b = simulate('深度型', 'L4 交叉一致', N, 300, complexity=1.0)
    print('  %-14d %-30.4f %.4f' % (N, a['P'], b['P']))

print()
print('  ★ 关键: 核数对 L1 验证的任务几乎无用 (链长是瓶颈)')
print('          核数对 L4 验证的任务有用 (需要多撒种子)')
print()
print('  用时 %.2fs' % (time.time() - t0))
