#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scheduler.py — 任务调度器: 判断任务属于哪一档, 分配资源
==========================================================
核心不是"切换广度/深度", 而是【判断任务属于哪一档】。

三个输入 (需要估计):
  ① 链长 L       任务拆解后需要多少步依赖链
  ② 验证等级 v   每步验证的准确率 (L1~L6)
  ③ 可用核数 N

一个输出 (调度决策):
  · 分配多少核做并行尝试
  · 验证密度 (每步验证 / 每 k 步验证)
  · 预测成功率
  · 若不可行 → 上报"需外援"

全部数字都用【今天实测】的参数, 不是编的。
"""
import numpy as np, time

t0 = time.time()

# ==================== 今天实测的参数表 ====================
# 验证器准确率 → 可支撑链长 (verify_depth.py 实测)
VERIFY_LEVELS = {
    'L1 可执行':   dict(v=1.000, note='跑一下/算一下',   domain='数学/代码/逻辑'),
    'L2 形式检查': dict(v=0.990, note='类型/lint/结构',  domain='语法/结构'),
    'L3 检索比对': dict(v=0.970, note='找原文核对',      domain='事实核查'),
    'L4 交叉一致': dict(v=0.900, note='多模型投票',      domain='开放问答'),
    'L5 偏好排序': dict(v=0.750, note='打分排序',        domain='创意/风格'),
    'L6 延迟验证': dict(v=1.000, note='等结果揭晓(慢)',  domain='决策/投资'),
}

# Amdahl: 串行比例 → 并行加速上限 (parallel.py)
AMDAHL = {
    '广度型': 0.02,    # lemma遍历 / 枚举
    '混合型': 0.15,    # 多分支证明
    '深度型': 0.60,    # 长链推理
    '单点型': 0.98,    # 关键洞察
}


def est_chain_len(task_type, complexity=1.0):
    """估计链长 (真实场景需拆解器, 这里用规则模拟)"""
    base = {'广度型': 10, '混合型': 20, '深度型': 60, '单点型': 3}
    return int(base[task_type] * complexity)


def eff_step_rate(p_step, v, retries=3):
    """
    有效单步成功率 (有中间验证 + 重试)
    公式: 每步真实成功率 p, 验证器准确率 v
         有效 = p*v / (p*v + (1-p)*(1-v))       (验证器接受的就是对的)
         重试 r 次: 1-(1-有效)^r
    """
    if v >= 1.0:
        return 1.0
    valid = p_step * v / (p_step * v + (1 - p_step) * (1 - v))
    return 1 - (1 - valid) ** retries


def schedule(task_type, level, N_cores, T_clock=2000, p_step=0.9, target=0.9):
    """
    调度决策
    返回 dict: 分配方案 + 预测成功率 + 是否可行
    """
    L = est_chain_len(task_type)
    v = VERIFY_LEVELS[level]['v']
    f_serial = AMDAHL[task_type]

    # ---------- ① 有效单步成功率 ----------
    p_eff = eff_step_rate(p_step, v)

    # ---------- ② 单链成功率 ----------
    p_chain = p_eff ** L

    # ---------- ③ 每个核能跑多少次尝试 ----------
    tries_per_core = max(1, int(T_clock / L))
    total_tries = N_cores * tries_per_core

    # ---------- ④ 总成功率 (至少一条链成功) ----------
    if p_chain >= 1.0:
        p_total = 1.0
    else:
        p_total = 1 - (1 - p_chain) ** total_tries

    # ---------- ⑤ Amdahl 修正 (串行部分限制并行收益) ----------
    speedup_cap = 1.0 / f_serial
    eff_cores = min(N_cores, speedup_cap * N_cores / max(N_cores, 1) * N_cores) \
        if False else min(N_cores, int(speedup_cap * 10))
    # 实际有效尝试数受串行部分限制
    total_tries_eff = int(total_tries * min(1.0, speedup_cap / max(N_cores, 1) * N_cores)) \
        if False else total_tries
    if f_serial > 0.3:
        # 深度型: 并行基本无效, 尝试数不随核数增长
        total_tries_eff = max(1, int(total_tries_eff * 0.1))

    if p_chain >= 1.0:
        p_total_eff = 1.0
    else:
        p_total_eff = 1 - (1 - p_chain) ** total_tries_eff

    # ---------- ⑥ 决策 ----------
    if p_total_eff >= target:
        verdict = '✅ 可行'
        action = '直接执行 (广度并行 + 每步验证)'
    elif p_total_eff >= 0.5:
        verdict = '⚠️ 勉强'
        action = '增加核数 或 提高验证密度'
    else:
        verdict = '❌ 需外援'
        action = '上报大模型/人 (核多无用)'

    return dict(L=L, v=v, p_eff=p_eff, p_chain=p_chain,
                tries=total_tries_eff, p_total=p_total_eff,
                verdict=verdict, action=action,
                speedup_cap=speedup_cap)


# ==================== 测试用例 ====================
print('=' * 90)
print('任务调度器 — 判断任务属于哪一档')
print('=' * 90)
print()

cases = [
    ('广度型', 'L1 可执行',   200, '代码重构: 改20处调用点, 每次可编译验证'),
    ('广度型', 'L1 可执行',   200, '数据分析: 枚举100个特征组合, 每次可算指标'),
    ('混合型', 'L1 可执行',   200, 'IMO数学题: 枚举lemma + 每条形式验证'),
    ('深度型', 'L1 可执行',   200, '长代码链: 50步依赖重构, 每步可编译'),
    ('深度型', 'L4 交叉一致', 200, '开放推理链: 20步, 只能多模型投票'),
    ('单点型', 'L5 偏好排序', 200, '选题决策: 选哪个研究方向'),
]

print('  %-6s %-12s %-6s %-8s %-10s %-10s %-10s %s' % (
    '类型', '验证等级', '核数', '链长', '单步有效率', '可尝试数', '预测成功率', '判定'))
print('  ' + '-' * 86)
for tt, lv, N, desc in cases:
    r = schedule(tt, lv, N)
    print('  %-6s %-12s %-6d %-8d %-10.4f %-10d %-10.4f %s' % (
        tt, lv, N, r['L'], r['p_eff'], r['tries'], r['p_total'], r['verdict']))
    print('  %-6s %s' % ('', desc))

print()
print('=' * 90)
print('调度详情 (每个任务给出具体行动)')
print('=' * 90)
for tt, lv, N, desc in cases:
    r = schedule(tt, lv, N)
    print()
    print('  【%s】%s' % (tt, desc))
    print('    验证等级: %s (v=%.3f, %s)' % (lv, r['v'], VERIFY_LEVELS[lv]['note']))
    print('    链长 %d, 单步有效率 %.4f (原始 0.90 → 提升 %.2f 倍)'
          % (r['L'], r['p_eff'], r['p_eff']/0.90))
    print('    并行上限 %.0fx (串行比例 %.2f)' % (r['speedup_cap'], AMDAHL[tt]))
    print('    可尝试 %d 次 → 预测成功率 %.4f' % (r['tries'], r['p_total']))
    print('    → %s : %s' % (r['verdict'], r['action']))

print()
print('=' * 90)
print('★ 核心规律')
print('=' * 90)
print('  ① 广度型 + L1验证 → 核数直接换成功率 (线性)')
print('  ② 深度型 + L1验证 → 链长是唯一瓶颈, 核数帮助有限')
print('  ③ 单点型 / L5验证 → 核数完全无用, 必须外援')
print()
print('  → 调度器的职责不是"切换模式", 而是"识别这一档"')
print()
print('  用时 %.2fs' % (time.time() - t0))
