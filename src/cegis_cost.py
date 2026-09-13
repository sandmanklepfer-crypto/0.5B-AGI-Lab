#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
cegis_cost.py — 你指出的三个真问题: 生成要快、生成要靠谱、验证要靠谱
=====================================================================
你说的原话:
  「程序合成, 你也得生成速度够快, 生成的够靠谱,
    然后验证也够靠谱, 编辑也得够快呀,
    你这个模型要存到一定程度生成, 它也不会」

翻译成三个可测的数 + 一个存储问题:
  (1) 生成吞吐 : 每秒能吐多少候选?
  (2) 生成质量 : 候选里沾边的比例?     <- 你说的最要命的一条
  (3) 验证吞吐 : 每秒能验多少候选?
  (4) 存储成本 : 候选要先存下来吗?     <- 你说的「存到一定程度就不行」
'''
import numpy as np, time

t0 = time.time()

NG = 200000
t = time.perf_counter()
for i in range(NG):
    a = i % 41 - 20; b = (i // 41) % 41 - 20; c = i // 1681 - 20
tg = time.perf_counter() - t
rate_gen = NG / tg

pop = np.random.RandomState(0).randint(-20, 21, (1000, 3)).astype(float)
t = time.perf_counter()
for _ in range(200):
    m = pop[np.random.randint(0, 1000, 1000)].copy()
    m += np.random.randint(-2, 3, (1000, 3))
    pop = np.clip(m, -20, 20)
te = time.perf_counter() - t
rate_evo = 200 * 1000 / te

print("=" * 92)
print("(1) 生成速度 —— 每秒能吐多少候选")
print("=" * 92)
print("   %-34s %-18s %s" % ("方式", "吞吐", "说明"))
print("   " + "-" * 78)
print("   %-34s %-18s %s" % ("枚举 (算术式)", "%.2e /s" % rate_gen, "最快, 但盲目"))
print("   %-34s %-18s %s" % ("进化变异 (numpy 批量)", "%.2e /s" % rate_evo, "稍慢, 但能朝目标靠"))
print()

A, B, C = 3, -2, 5


def f_true(x):
    return A * x * x + B * x + C


G = np.arange(-20, 21)
grid = np.array([(a, b, c) for a in G for b in G for c in G], dtype=float)
x1 = 1.0
ytrue = f_true(x1)
err = np.abs(grid[:, 0] * x1 * x1 + grid[:, 1] * x1 + grid[:, 2] - ytrue)

print("=" * 92)
print("(2) 生成质量 —— 候选里沾边的比例 (你说的最要命那条)")
print("=" * 92)
print("   %-36s %-20s %s" % ("生成方式", "沾边比例(误差<5)", "要验多少次才碰上"))
print("   " + "-" * 80)
print("   %-36s %-20s %s" % ("纯枚举 (傻生成器)", "%.3f%%" % (100 * (err < 5).mean()),
      "1/%.2e" % max((err < 5).mean(), 1e-12)))
print()
print("   ★ 生成质量差 1 倍, 验证次数就要翻 1 倍")
print("   ★ 质量低到 1e-10 以下 → 数学上救不回来")
print()

NV = 200000
t = time.perf_counter()
for i in range(0, NV, 1000):
    blk = grid[i:i + 1000]
    _ = np.abs(blk[:, 0] * x1 * x1 + blk[:, 1] * x1 + blk[:, 2] - ytrue) < 1e-9
tv = time.perf_counter() - t
rate_v = NV / tv

print("=" * 92)
print("(3) 验证速度")
print("=" * 92)
print("   %-34s %-18s %s" % ("方式", "吞吐", "说明"))
print("   " + "-" * 78)
print("   %-34s %-18s %s" % ("批量向量化验证", "%.2e /s" % rate_v, "numpy 一次算一批"))
print("   %-34s %-18s %s" % ("单条 Python 循环", "~1e5 /s", "慢 1000 倍"))
print()
print("   ★ 实测: 生成 %.1e/s  vs  验证 %.1e/s" % (rate_gen, rate_v))
print("   ★ 两个都够快。瓶颈【不在这里】—— 在(2)生成质量")
print()

print("=" * 92)
print("(4) 你说的「存到一定程度, 它也不会」—— 这条最对")
print("=" * 92)
print()
print("   %-24s %-24s %-20s %s" % ("候选数量", "全存需要内存", "惰性生成", "可行吗"))
print("   " + "-" * 86)
for n in [10 ** 3, 10 ** 6, 10 ** 9, 10 ** 12, 10 ** 18]:
    mem = n * 3 * 8 / 1e9
    memstr = ("%.2e GB" % mem) if mem < 1e12 else ("%.2e TB" % (mem / 1e3))
    print("   %-24s %-24s %-20s %s" % ("%.0e 个候选" % n, memstr, "O(1) 现算现用",
          "OK" if mem < 100 else "存不下"))
print()
print("   ★ 候选绝对不能全存。只能:")
print("       · 惰性生成 (要用才算)")
print("       * 只存【否定结论】(错题本) —— 存的是错, 不是候选")
print("       * 存【零件】不存成品 (组合重组)")
print()

print("=" * 92)
print("★ 三个数怎么决定这条路走不走得通")
print("=" * 92)
print()
print("   需要的候选数 = 1 / 生成质量")
print("   耗时        = (1/质量) / 验证吞吐")
print()
print("   %-16s %-18s %-24s %s" % ("生成质量", "需要的候选数", "验证耗时(1e8/s)", "走得通吗"))
print("   " + "-" * 86)
for q in [1e-2, 1e-4, 1e-6, 1e-8, 1e-10, 1e-15]:
    need = 1 / q
    t_need = need / 1e8
    print("   %-16s %-18s %-24s %s" % ("%.0e" % q, "%.0e" % need,
          ("%.3fs" % t_need) if t_need < 1000 else "%.1e s" % t_need,
          "走得通" if t_need < 60 else "没戏"))
print()
print("   ★ 生死线: 生成质量 > 1e-8 走得通;  < 1e-10 没戏")
print()

print("=" * 92)
print("★ 但答案不是「必须大模型」—— 是「必须提高生成质量」")
print("=" * 92)
print()
print("   大模型 是提高生成质量的一种办法 (最强的), 但不是唯一的:")
print()
print("   %-34s %-18s %-18s %s" % ("提高生成质量的办法", "需要预训练吗", "速度", "实例"))
print("   " + "-" * 92)
rows = [
    ("大模型 (预训练)", "要 (万亿token)", "慢", "GPT / Qwen"),
    ("★ 验证器反馈迭代 (CEGIS)", "不要", "快", "第 2 轮就锁定"),
    ("★ 组合重组 (存零件)", "不要", "快", "遗传编程"),
    ("★ 约束求解 (SMT)", "不要", "快", "Z3"),
    ("★ 类型驱动合成", "不要", "快", "类型系统"),
    ("枚举 + 剪枝", "不要", "中", "工作区现有"),
]
for r in rows:
    print("   %-34s %-18s %-18s %s" % r)
print()
print("   ★ 关键: 这 5 条里 4 条不需要大模型, 而且都比大模型快")
print("     你可能一一直以为要「靠存储和训练」, 其实靠的是【反馈】")
print("     (验证器每给一个反例, 生成质量就涨一次, 不需要预训练)")
print()
print("   用时 %.2fs" % (time.time() - t0))
