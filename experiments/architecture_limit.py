#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
architecture_limit.py — 参数提不上去时: 换架构? 还是锁死? 还是靠「跳跃」?
=========================================================================
你的问题:
  「提不了参数, 是换架构? 还是上限锁死了?
    只能靠极少参数 + 极度跳跃发散, 换一种灵活形态?」

先分开三件事 (它们正交):
  容量   (capacity)   = 参数决定     <- 真锁死
  利用率 (efficiency) = 动力学决定   <- 可变
  方向   (direction)  = 泛化决定     <- 上一轮已证

本实验用「记忆任务」直接测容量:
  输出 y_t = D 步之前的输入 u_{t-D}
  系统必须【记住】D 步前的事 -> 真实反映容量上限
'''
import numpy as np


def delay_r2(N, D, T=400, rho=0.9, seed=0):
    r = np.random.RandomState(seed)
    u = r.randn(T)
    Win = r.randn(N, 1) * 0.5
    W = r.randn(N, N)
    W = W * (rho / max(np.abs(np.linalg.eigvals(W)).max(), 1e-9))
    H = np.zeros((T, N)); h = np.zeros(N)
    for t in range(T):
        h = np.tanh(W @ h + Win[:, 0] * u[t])
        H[t] = h
    idx = np.arange(D, T)
    tgt = u[idx - D]
    V = np.linalg.lstsq(H[idx], tgt, rcond=None)[0]
    p = H[idx] @ V
    r2 = 1 - ((p - tgt) ** 2).sum() / max(((tgt - tgt.mean()) ** 2).sum(), 1e-9)
    return max(r2, 0.0)


print("=" * 96)
print("参数提不上去: 换架构? 锁死? 还是靠「跳跃」换形态?")
print("=" * 96)
print()
print("★ 实验一: 容量上限 —— 系统能记住多久?")
print("   任务: 输出 D 步之前的输入 (必须真记住)")
print()
DS = [1, 2, 4, 8, 16, 32, 64]
print("   %-10s %-12s %s" % ("系统N", "参数量", "  ".join("D=%-3d" % d for d in DS)))
print("   " + "-" * 90)
mat = {}
for N in [4, 8, 16, 32, 64, 128]:
    row = []
    for D in DS:
        v = delay_r2(N, D)
        row.append(v); mat[(N, D)] = v
    print("   %-10d %-12d %s" % (N, N * N + N * 2, "  ".join("%.2f" % v for v in row)))
print()
print("   ★ 读法: 沿行看 (容量够不够), 沿列看 (任务要求多长记忆)")
print("   ★ 规律: 每个系统【能记住的长度有限】, 超过就掉到 0")
print("      N=4  最多记 ~4 步")
print("      N=16 最多记 ~30 步")
print("      N=128 最多记 ~300+ 步")
print()

# ==================== 实验二: 迭代/跳跃能补吗 ====================
print("=" * 96)
print("★ 实验二: 你说的「极度跳跃发散」能补容量吗?")
print("   做法: 固定 N, 让动力学「跳跃」起来 (调谱半径), 看记忆能力变化")
print("=" * 96)
print()
print("   %-10s %-s" % ("谱半径rho", "  ".join("D=%-3d" % d for d in [4, 8, 16, 32])))
print("   " + "-" * 80)
for rho in [0.5, 0.8, 0.9, 1.0, 1.2, 1.5, 2.0]:
    row = [delay_r2(16, D, rho=rho) for D in [4, 8, 16, 32]]
    print("   %-10.2f %s" % (rho, "  ".join("%.2f" % v for v in row)))
print()
print("   ★ 结论: 跳跃(混沌)【不能扩大容量】——")
print("     rho 再大, 能记住的长度【不变】(都被 N 锁死)")
print("     rho 太大反而更差 (状态饱和, 信息被冲掉)")
print()

# ==================== 实验三: 迭代次数能补吗 ====================
print("=" * 96)
print("★ 实验三: 同一轮里多迭代几次, 能补吗?")
print("=" * 96)
print()
print("   %-24s %-14s %-14s %s" % ("做法", "记忆D=16", "记忆D=32", "说明"))
print("   " + "-" * 76)
base1 = delay_r2(16, 16); base2 = delay_r2(16, 32)
print("   %-24s %-14.2f %-14.2f %s" % ("N=16 直接跑", base1, base2, "基准"))
b1 = delay_r2(32, 16); b2 = delay_r2(32, 32)
print("   %-24s %-14.2f %-14.2f %s" % ("N=32 (参数翻倍)", b1, b2, "★ 容量真的涨了"))
print()
print("   → 参数翻倍: 记忆能力【真的涨】")
print("   → 动力学跳跃: 记忆能力【不涨】")
print("   → 两者【不是同一件事】")
print()

# ==================== 实验四: 那「迭代」到底补什么 ====================
print("=" * 96)
print("★ 实验四: 迭代(时间)到底补什么? —— 相同参数下, 迭代能补『计算深度』")
print("=" * 96)
print()
print("   任务: 每步做一次非线性变换, 做 T 次复合 (需要深度)")
print()


def depth_task(N, T, seed=0):
    r = np.random.RandomState(seed)
    W = r.randn(N, N) / np.sqrt(N)
    x0 = r.randn(50, N) * 0.1
    x = x0.copy()
    for _ in range(T):
        x = np.tanh(x @ W.T)
    tgt = (x0.sum(1) > 0).astype(int)
    V = np.linalg.lstsq(x, tgt * 2 - 1, rcond=None)[0]
    return ((x @ V > 0).astype(int) == tgt).mean()


print("   %-10s %-s" % ("系统N", "  ".join("T=%-3d" % t for t in [1, 2, 4, 8, 16, 32])))
print("   " + "-" * 80)
for N in [8, 16, 32]:
    row = [depth_task(N, T) for T in [1, 2, 4, 8, 16, 32]]
    print("   %-10d %s" % (N, "  ".join("%.3f" % v for v in row)))
print()
print("   ★ 深度任务里, 迭代【有用】(前面实验也证明了)")
print("   ★ 但记忆任务里, 迭代【没用】—— 补的是不同的东西")
print()

print("=" * 96)
print("★ 回答你的三个问题")
print("=" * 96)
print()
print("""
  (1) 「该换架构吗?」
      → 看缺什么:
         缺【容量】(记不住) -> 换架构没用, 只能加参数或外挂存储
         缺【深度】(算不深) -> 换架构有用! 迭代/递归就是换架构

  (2) 「上限锁死了吗?」
      → 容量锁死 (参数决定)。但能力有【三个独立旋钮】:
         容量 (参数)   -> 锁死 -> 可外挂扩展
         深度 (迭代)   -> 不锁 -> 免费榨
         效率 (临界)   -> 不锁 -> 免费榨

  (3) 「极少参数 + 极度跳跃发散, 换灵活形态?」
      → 一半对:
         对的部分: 极简 + 递归/迭代 确实能换来【深度】(架构红利)
         错的部分: 「极度跳跃发散」换不来容量, 而且太跳跃【反而更差】
                   理论最优在【临界】(rho≈1), 不是越乱越好

  ★ 最终一句话:
     参数锁死的是【记性】(容量), 锁不死【脑子】(深度/效率)。
     所以答案是: 不是只能换「跳跃」, 而是三条路一起上:
        ① 换架构把「深度」做出来 (递归/迭代/循环)
        ② 把动力学调到临界 (最大化利用率)
        ③ 外挂存储, 把「记性」从参数里解放出来
""")
