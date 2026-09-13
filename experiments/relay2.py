#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
relay2.py — 接力并行 (公平对比: 同样墙钟时间)
================================================
上一版错在把预算除以N (独立链只给 T/N 轮)
本版严格公平: 两种模式都给【同样的墙钟时间 T】

测: 达到 90% 成功率 需要多少轮 (T90)
  T90 越小 = 越快

  ② 独立: N条链各自推进, 看 N 条里最深的
  ③ 接力: N核共享前沿, 每轮 N 个核同时试 N 个选项

★ 三个关键量
  ① 接力相对独立的加速比 (T90 之比)
  ② 加速比的上限 (能不能超过 K?)
  ③ "全压一条链"的代价
"""
import numpy as np, time

t0 = time.time()
L, K = 20, 10
M = 400                 # 试验次数
MAXT = 600

print('=' * 84)
print('接力 vs 独立: 达到 90% 成功率需要多少轮?')
print('=' * 84)
print('  链长 L=%d, 每步 %d 个候选 (正确率 1/%d)' % (L, K, K))
print()

rng = np.random.RandomState(0)


def t90_independent(N):
    """N 条独立链, 返回 90% 成功所需轮数"""
    depths = np.zeros((M, N), np.int32)
    T = np.full(M, -1, np.int32)
    for t in range(1, MAXT + 1):
        depths += (rng.rand(M, N) < 1.0 / K)
        done = depths.max(1) >= L
        newly = done & (T < 0)
        T[newly] = t
        if (T > 0).all(): break
    ok = T[T > 0]
    return np.percentile(ok, 90) if len(ok) > M * 0.5 else np.inf


def t90_relay(N, diversity=1.0):
    """N 核共享前沿, 返回 90% 成功所需轮数"""
    d = np.zeros(M, np.int32)
    T = np.full(M, -1, np.int32)
    eff = max(1, int(N * diversity))
    cover = min(eff, K)
    p_adv = cover / K if cover < K else 1.0
    for t in range(1, MAXT + 1):
        d += (rng.rand(M) < p_adv)
        done = d >= L
        newly = done & (T < 0)
        T[newly] = t
        if (T > 0).all(): break
    ok = T[T > 0]
    return np.percentile(ok, 90) if len(ok) > M * 0.5 else np.inf


print('  %-8s %-20s %-20s %-12s %s' % ('核数N', '②独立 T90', '③接力 T90', '加速比', '上限'))
print('  ' + '-' * 76)
for N in [1, 5, 20, 100, 500, 2000]:
    ti = t90_independent(N)
    tr = t90_relay(N)
    sp = ti / tr if (tr > 0 and np.isfinite(ti)) else float('nan')
    print('  %-8d %-20.0f %-20.0f %-12.2f %s' % (
        N, ti, tr, sp, '★ 超过 K(=10) 上限!' if sp > K * 1.1 else ('= K 上限' if sp > K*0.9 else '')))

print()
print('=' * 84)
print('★ 加速比上限: 接力最快也只能到 L 轮 (链长不能并行)')
print('=' * 84)
print('  理论: 接力 T90 → L = %d 轮 (每轮必进一步)' % L)
print('        独立 T90 → K×L = %d 轮 (单链期望)' % (K*L))
print('        加速比上限 = K = %d' % K)
print()
print('  实测最大加速比: %.2f  (在 N=%d 时)' % (
    max((t90_independent(n) / t90_relay(n)) for n in [100, 500, 2000]),
    2000))

print()
print('=' * 84)
print('★ "全压一条链"的代价 (多样性扫描, 预算收紧到 60 轮)')
print('=' * 84)
print()
print('  %-14s %-8s %-14s %-14s %s' % ('配置', '覆盖数', '每轮推进概率', 'T90', '判定'))
print('  ' + '-' * 70)
for N, div in [(100, 1.0), (100, 0.5), (100, 0.2), (100, 0.05), (100, 0.01), (10, 0.05)]:
    eff = max(1, int(N * div))
    cover = min(eff, K)
    p = cover / K if cover < K else 1.0
    tr = t90_relay(N, div)
    print('  %-14s %-8d %-14.2f %-14.0f %s' % (
        'N=%d div=%.2f' % (N, div), cover, p, tr,
        '✅' if tr <= 40 else ('⚠️ 变慢' if tr < 200 else '❌ 拥挤失效')))

print()
print('  用时 %.2fs' % (time.time() - t0))
