#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hyperheur.py — 超启发与泛化: 多个可验证领域能否长出来?
========================================================
关键修正:
  之前说"超启发框架给不了" —— 那是在【单个领域】内看。
  
  但如果手上有 N 个【不同的可验证任务族】:
    · 每个族都有自己的验证器 (所以每次尝试都能知道成败)
    · "哪个策略在哪个族上好" 变成【可测量】的
    → 超启发(learn to choose strategy) 就能长出来!
    
  同理泛化: 多域都有验证器 → 可以学"跨域的规律"

  所以真正的问题不是"框架能不能", 而是
  ★ "需要多少个可验证域, 才能长出超启发?"

设计:
  6 个任务族 (结构不同), 4 个策略
  Phase1: 在每个族上试每个策略, 记录成功率 (全部可验证)
  Phase2: 给一个【新族】, 用学到的规律预测最优策略
  对照: 随机选 vs 学出来的选择器

判据: 选择器在新族上的表现 > 随机 → 超启发成立
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

NFAM = 6            # 任务族数
NSTRAT = 4          # 策略数
TRIALS = 30         # 每族每策略试几次


STRAT_PREF = np.array([
    [0.9, 0.1],   # 策略0: 擅长深
    [0.1, 0.9],   # 策略1: 擅长广
    [0.5, 0.5],   # 策略2: 均衡
    [0.7, 0.4],   # 策略3: 偏深
])


def run_task_gen(feat_vec, strat, seed):
    """通用版: 给定族的特征向量(可以是新族)"""
    r = np.random.RandomState(seed)
    f = feat_vec; s = STRAT_PREF[strat]
    p = 0.3 + 0.6 * float(f @ s) / (np.linalg.norm(f) * np.linalg.norm(s) + 1e-9)
    return 1 if r.rand() < p else 0


def run_task(fam, strat, seed):
    """模拟: 族fam上, 策略strat一次尝试的成功概率"""
    r = np.random.RandomState(seed)
    # ★ 每族的"结构特征" (2维): [深度, 广度]
    feats = np.array([
        [0.9, 0.2],   # 族0: 深而窄
        [0.2, 0.9],   # 族1: 浅而广
        [0.5, 0.5],   # 族2: 中等
        [0.8, 0.7],   # 族3: 又深又广
        [0.1, 0.3],   # 族4: 浅而窄
        [0.6, 0.2],   # 族5: 深但窄
    ])
    # ★ 每策略的"偏好" (它擅长什么)
    strat_pref = np.array([
        [0.9, 0.1],   # 策略0: 擅长深
        [0.1, 0.9],   # 策略1: 擅长广
        [0.5, 0.5],   # 策略2: 均衡
        [0.7, 0.4],   # 策略3: 偏深
    ])
    f = feats[fam]; s = strat_pref[strat]
    # 匹配度 → 成功率
    p = 0.3 + 0.6 * float(f @ s) / (np.linalg.norm(f) * np.linalg.norm(s) + 1e-9)
    return 1 if r.rand() < p else 0


# ==================== Phase 1: 在已知族上测所有策略 ====================
print('=' * 84)
print('多域能否长出超启发? (6族 × 4策略, 全部可验证)')
print('=' * 84)
print()

succ = np.zeros((NFAM, NSTRAT))
for f in range(NFAM):
    for s in range(NSTRAT):
        ok = [run_task(f, s, seed=1000 * f + s + i) for i in range(TRIALS)]
        succ[f, s] = np.mean(ok)

print('  已知族上的成功率矩阵 (行=族, 列=策略):')
print('       ' + ''.join('  策略%d ' % s for s in range(NSTRAT)) + '   最优')
for f in range(NFAM):
    best = int(np.argmax(succ[f]))
    print('  族%d  ' % f + ''.join('  %.2f ' % succ[f, s] for s in range(NSTRAT)) + '   → 策略%d' % best)

# ==================== 学一个"选择器": 从族特征预测最优策略 ====================
# 用最简单的形式: 学 策略得分 = w_s · 族特征
feats = np.array([
    [0.9, 0.2], [0.2, 0.9], [0.5, 0.5], [0.8, 0.7], [0.1, 0.3], [0.6, 0.2]])
W = np.zeros((2, NSTRAT))
for s in range(NSTRAT):
    W[:, s] = np.linalg.lstsq(feats, succ[:, s], rcond=None)[0]

print()
print('=' * 84)
print('Phase 2: 用选择器预测【新族】的最优策略')
print('=' * 84)
print()

# ★ 新族: 训练时【从未见过】的结构
new_fams = {
    '新族A (深0.85,广0.15)': np.array([0.85, 0.15]),
    '新族B (深0.15,广0.85)': np.array([0.15, 0.85]),
    '新族C (深0.45,广0.45)': np.array([0.45, 0.45]),
    '新族D (深0.75,广0.35)': np.array([0.75, 0.35]),
}

print('  %-24s %-14s %-14s %-14s %s' % (
    '新族', '选择器选的', '真实最优', '随机期望', '判定'))
print('  ' + '-' * 78)
good = 0; total = 0
for nm, fv in new_fams.items():
    # 选择器预测
    scores = fv @ W
    pick = int(np.argmax(scores))
    # 真实: 用蒙特卡洛估每个策略的真实成功率
    real = []
    for s in range(NSTRAT):
        ok = [run_task_gen(fv, s, seed=7777 + s + i) for i in range(200)]
        real.append(np.mean(ok))
    real = np.array(real)
    best = int(np.argmax(real))
    rand_exp = real.mean()
    ok = '✅' if real[pick] >= real[best] - 0.05 else '⚠️'
    if real[pick] >= real[best] - 0.05: good += 1
    total += 1
    print('  %-24s %-14s %-14s %-14.3f %s' % (
        nm, '策略%d (%.2f)' % (pick, real[pick]),
        '策略%d (%.2f)' % (best, real[best]), rand_exp, ok))

print()
print('  选择器命中: %d/%d' % (good, total))

print()
print('=' * 84)
print('★ 关键: 需要多少个已见族, 选择器才学会?')
print('=' * 84)
print()
print('  %-12s %-16s %-16s %s' % ('已见族数', '选择器平均', '随机平均', '优势'))
print('  ' + '-' * 60)
for n_seen in [2, 3, 4, 6]:
    W2 = np.zeros((2, NSTRAT))
    ff = feats[:n_seen]
    for s in range(NSTRAT):
        W2[:, s] = np.linalg.lstsq(ff, succ[:n_seen, s], rcond=None)[0]
    a_pick = []; a_rand = []
    for nm, fv in new_fams.items():
        sc = fv @ W2
        pk = int(np.argmax(sc))
        real = []
        for s in range(NSTRAT):
            ok = [run_task_gen(fv, s, seed=8888 + s + i) for i in range(150)]
            real.append(np.mean(ok))
        real = np.array(real)
        a_pick.append(real[pk]); a_rand.append(real.mean())
    print('  %-12d %-16.3f %-16.3f %+.3f' % (
        n_seen, np.mean(a_pick), np.mean(a_rand),
        np.mean(a_pick) - np.mean(a_rand)))

print()
print('  用时 %.2fs' % (time.time() - t0))
