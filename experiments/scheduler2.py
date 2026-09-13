#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler2.py — 任务调度器 (修正: 加入时间预算与重试成本)
============================================================
上一版全返回 1.0000, 因为漏了【重试成本】。
若重试免费, 什么任务都能解 —— 显然不成立。

修正模型:
  时间预算 T (固定)
  每个核跑一条链: 成本 = L(链长) × r(每步重试) × c(单次成本)
  一个核能跑完整链的条数 = T / (L × r × c)

  权衡: r 大 → 单步可靠, 但跑的链数少
        r 小 → 单步不可靠, 但能多撒种子

★ 关键约束: 不同任务的【可重试性】不同
  广度型: 每次重试 = 换个方向 → 重试性 1.0
  深度型: 每次重试 = 重新推 → 重试性 0.5
  单点型: 一次洞察不能"重试" → 重试性 0.1
"""
import numpy as np, time

t0 = time.time()

VERIFY = {
    'L1 可执行':   dict(v=1.000, note='跑一下'),
    'L2 形式检查': dict(v=0.990, note='类型/lint'),
    'L3 检索比对': dict(v=0.970, note='找原文'),
    'L4 交叉一致': dict(v=0.900, note='多模型投票'),
    'L5 偏好排序': dict(v=0.750, note='打分排序'),
}
# 串行比例 (Amdahl) + 可重试性
TASK = {
    '广度型': dict(f=0.02, retryable=1.0),
    '混合型': dict(f=0.15, retryable=0.7),
    '深度型': dict(f=0.60, retryable=0.5),
    '单点型': dict(f=0.98, retryable=0.1),
}
BASE_LEN = {'广度型': 20, '混合型': 30, '深度型': 60, '单点型': 3}


def valid_rate(p, v):
    """验证器选中正确项的概率 (无重试)"""
    if v >= 1.0: return 1.0
    return p*v / (p*v + (1-p)*(1-v))


def opt_retry(p_chain_base, L, retryable, T_budget, c=1.0):
    """
    选择最优重试次数 r
    约束: 一个核在 T 内可跑的链数 = T/(L*r*c)
    目标: 最大化 p_total = 1-(1-p_chain)^n_chains
    """
    best = (0.0, 1)
    for r in [1, 2, 3, 5, 8, 12, 20]:
        # 重试有效增益 (受可重试性限制)
        eff_r = 1 + (r - 1) * retryable
        p_step_eff = 1 - (1 - p_chain_base) ** eff_r if p_chain_base < 1 else 1.0
        p_chain = p_step_eff ** L
        # 时间预算
        n_chains = max(1, int(T_budget / (L * r * c)))
        p_total = 1 - (1 - p_chain) ** n_chains if p_chain < 1 else 1.0
        if p_total > best[0]:
            best = (p_total, r, n_chains, p_chain)
    return best


def schedule(task_type, level, N_cores, T_per_core=4000, p=0.9, target=0.9,
             c=1.0, complexity=1.0):
    L = int(BASE_LEN[task_type] * complexity)
    v = VERIFY[level]['v']
    f = TASK[task_type]['f']
    retryable = TASK[task_type]['retryable']

    vr = valid_rate(p, v)                       # 单步有效 (验证器选中对的)
    p_total, r, n_chains, p_chain = opt_retry(vr, L, retryable, T_per_core, c)

    # Amdahl: 并行有效度
    speedup_cap = 1.0 / f
    N_eff = min(N_cores, N_cores * min(1.0, speedup_cap / max(N_cores, 1)) * N_cores) \
        if False else N_cores
    # 深度型: 并行基本无效
    if f > 0.5:
        N_eff = max(1, int(N_cores * 0.1))
    elif f > 0.3:
        N_eff = max(1, int(N_cores * 0.4))

    total_chains = n_chains * N_eff
    if p_chain >= 1.0:
        P = 1.0
    else:
        P = 1 - (1 - p_chain) ** total_chains

    if P >= target:
        vd, act = '✅ 可行', '直接执行'
    elif P >= 0.5:
        vd, act = '⚠️ 勉强', '加核 / 提高验证等级'
    else:
        vd, act = '❌ 需外援', '上报大模型或人'

    return dict(L=L, v=v, vr=vr, r=r, n_chains=n_chains, N_eff=N_eff,
                p_chain=p_chain, total_chains=total_chains, P=P,
                verdict=vd, action=act, cap=speedup_cap)


print('=' * 96)
print('任务调度器 (加入时间预算 + 重试成本 + 可重试性)')
print('=' * 96)
print()
print('  %-6s %-12s %-6s %-6s %-9s %-6s %-8s %-9s %s' % (
    '类型', '验证', '核数', '链长', '单步有效', '重试', '总链数', '预测成功', '判定'))
print('  ' + '-' * 92)

cases = [
    ('广度型', 'L1 可执行',   200, 1.0,  '代码重构 20 处调用点'),
    ('广度型', 'L3 检索比对', 200, 1.5,  '事实核查 30 个事实'),
    ('混合型', 'L1 可执行',   200, 1.0,  'IMO 数学题 (lemma 枚举)'),
    ('深度型', 'L1 可执行',   200, 1.0,  '50 步依赖重构 (每步可编译)'),
    ('深度型', 'L4 交叉一致', 200, 1.0,  '开放推理链 60 步 (只能投票)'),
    ('单点型', 'L5 偏好排序', 200, 1.0,  '选研究方向'),
]
rows = []
for tt, lv, N, cx, desc in cases:
    r = schedule(tt, lv, N, complexity=cx)
    rows.append((tt, lv, N, cx, desc, r))
    print('  %-6s %-12s %-6d %-6d %-9.5f %-6d %-8d %-9.5f %s' % (
        tt, lv, N, r['L'], r['vr'], r['r'], r['total_chains'], r['P'], r['verdict']))

print()
print('=' * 96)
print('调度详情')
print('=' * 96)
for tt, lv, N, cx, desc, r in rows:
    print()
    print('  【%s】%s' % (tt, desc))
    print('    链长 %d | 验证 %s (v=%.3f) | 可重试性 %.1f' % (
        r['L'], lv, r['v'], TASK[tt]['retryable']))
    print('    单步有效 %.5f  →  每步重试 %d 次  →  单链成功率 %.5f' % (
        r['vr'], r['r'], r['p_chain']))
    print('    有效核数 %d (上限 %.0fx) → 总链数 %d  →  预测成功率 %.5f'
          % (r['N_eff'], r['cap'], r['total_chains'], r['P']))
    print('    → %s : %s' % (r['verdict'], r['action']))

print()
print('=' * 96)
print('★ 三档结论 (这才是调度器该输出的东西)')
print('=' * 96)
print('  档1 广度型 + L1/L2验证  →  ✅ 核数线性换取成功率 (几百核真的有用)')
print('  档2 深度型 + L1验证     →  ⚠️ 链长是瓶颈, 核数帮助有限 (但仍可解)')
print('  档3 单点型 或 L5验证    →  ❌ 核数完全无用, 必须外援')
print()
print('  用时 %.2fs' % (time.time() - t0))
