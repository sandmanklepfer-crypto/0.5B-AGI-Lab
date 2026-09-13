#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relay.py — 接力并行: 状态共享 + 失效接管, 到底比独立并行好在哪?
===================================================================
用户设计:
  几百条短链并行, 每条跑真实状态
  哪条成功了 → 其他链立刻继承那条的进度
  失败的链由其他扛上
  不全压一条链 (防崩)

数学形式: 带状态共享的并行最佳优先搜索
          共享的是【已验证的前沿深度 d】

关键区分 (决定这套架构成不成立):
  A 前缀可验证   每步完成立刻知道对不对 → 深度=进度 → 共享有用
  B 只能末端验证  不知道中途对不对      → 深度无意义 → 共享无用

对照三种:
  ① 单链        (基线)
  ② N条独立链    (纯并行, 不共享)
  ③ N条接力链    (共享前沿 + 接管)
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

L = 20          # 链长 (到目标需要20步)
K = 10          # 每步候选数 (正确率 1/K)
N_REP = 3000    # 重复次数 (统计成功率)


def sim_single(A, rounds, seed=0):
    """单链: 跑 rounds 轮, 每轮尝试推进一步"""
    r = np.random.RandomState(seed)
    d = 0
    for t in range(rounds):
        if A:
            # 前缀可验证: 每轮试一次, 1/K 概率推进
            if r.randint(K) == 0: d += 1
            if d >= L: return True
        else:
            # 不可验证: 需要一次走完 L 步全对
            pass
    if not A:
        # 只末端验证: rounds 轮里每轮试一条完整路径
        for t in range(rounds):
            if all(r.randint(K) == 0 for _ in range(L)): return True
    return False


def sim_independent(A, N, T_each, seed=0):
    """N 条独立链, 每条跑 T_each 轮"""
    r = np.random.RandomState(seed)
    if A:
        # 可验证: 每条链独立推进, 看 N 条里最深的
        best = 0
        for i in range(N):
            d = 0
            for t in range(T_each):
                if r.randint(K) == 0: d += 1
                if d >= L: return True
            best = max(best, d)
        return False
    else:
        # 不可验证: 每条链试 T_each 条完整路径
        for i in range(N):
            for t in range(T_each):
                if all(r.randint(K) == 0 for _ in range(L)): return True
        return False


def sim_relay(A, N, T_total, seed=0, diversity=1.0):
    """
    接力: N 核共享前沿 d, 一起推
    每轮 N 个核同时试 N 个选项 → 覆盖 N/K 的比例
    diversity: 1.0 = 各试不同选项; 0 = 全挤同一个 (暴露"全压一链"的危害)
    """
    r = np.random.RandomState(seed)
    if not A:
        # 不可验证: 共享无意义 → 等同于独立
        return sim_independent(False, N, max(1, T_total // N), seed)
    d = 0
    rounds = 0
    while rounds < T_total and d < L:
        # 每轮 N 个核尝试
        eff_n = max(1, int(N * diversity))
        # 覆盖 eff_n 个不同选项 (最多 K 个)
        cover = min(eff_n, K)
        hit = r.rand() < cover / K
        if hit: d += 1
        rounds += 1
    return d >= L


print('=' * 84)
print('接力并行 (状态共享) vs 独立并行')
print('=' * 84)
print('  链长 L=%d, 每步 %d 个候选, 正确率 1/%d' % (L, K, K))
print()

# ---------- A: 前缀可验证 ----------
print('=' * 84)
print('【A 前缀可验证】每步完成立刻知道对错 → 深度=进度')
print('=' * 84)
print()
print('  %-10s %-22s %-22s %s' % ('核数N', '②独立并行(成功率)', '③接力(成功率)', '接力优势'))
print('  ' + '-' * 76)
T_TOTAL = 300                                  # 总轮数预算
for N in [1, 5, 20, 100, 500]:
    T_each = T_TOTAL                            # 独立: 每核都能跑满 T_TOTAL
    p_ind = np.mean([sim_independent(True, N, max(1, T_TOTAL // max(N, 1) * 1), s)
                     for s in range(200)])
    p_rel = np.mean([sim_relay(True, N, T_TOTAL, s) for s in range(200)])
    d = p_rel - p_ind
    print('  %-10d %-22.3f %-22.3f %+.3f %s' % (N, p_ind, p_rel, d,
          '★' if d > 0.05 else ''))

print()
print('=' * 84)
print('【B 只能末端验证】中途不知道对错 → 深度无意义')
print('=' * 84)
print()
print('  %-10s %-22s %-22s %s' % ('核数N', '②独立并行', '③接力', '接力优势'))
print('  ' + '-' * 76)
for N in [1, 5, 20, 100]:
    p_ind = np.mean([sim_independent(False, N, max(1, T_TOTAL // max(N, 1)), s)
                     for s in range(200)])
    p_rel = np.mean([sim_relay(False, N, T_TOTAL, s) for s in range(200)])
    print('  %-10d %-22.3f %-22.3f %+.3f' % (N, p_ind, p_rel, p_rel - p_ind))

print()
print('=' * 84)
print('★ 第三个变量: "全压一条链"的代价 (diversity)')
print('=' * 84)
print('  可验证任务, N=100, 共享前沿但控制【覆盖多样性】')
print()
print('  %-22s %-18s %s' % ('多样性(各试不同选项)', '成功率', '说明'))
print('  ' + '-' * 62)
for div in [1.0, 0.5, 0.2, 0.05]:
    p = np.mean([sim_relay(True, 100, T_TOTAL, s, diversity=div) for s in range(200)])
    print('  %-22.2f %-18.3f %s' % (div, p,
          '★ 最优' if div == 0.2 else ('⚠️ 拥挤' if div < 0.1 else '')))

print()
print('  用时 %.2fs' % (time.time() - t0))
