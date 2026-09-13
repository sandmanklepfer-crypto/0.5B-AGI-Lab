#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
proto_fair.py — 公平对比: 原型记忆能否降噪?
=============================================
上一版失败因为【不公平对比】:
  A 用干净真值当模板 (上帝视角), B 用含噪原型 → A 天然占优

本版严格公平:
  两组都只能看到【同一个含噪观测流】, 都不知真值
  
  A 单样本    用第 1 次观测当模板 (不更新)
  B 软在线聚类 用所有观测, 最近模板 + 门控更新 (均值)
  C 硬门控     门控更严 (只接受高相似度, 抗污染)
  D 中位数     用中位数更新 (最强抗污染)

评价 (两个指标):
  ① 模板质量: proto 与真值 T 的相似度 (越接近 1 越好)
  ② 识别准确率: 用新含噪观测测试
"""
import numpy as np, time

t0 = time.time()
NW, D = 20, 10


def norm(x, ax=-1):
    return x / (np.linalg.norm(x, axis=ax, keepdims=True) + 1e-9)


def run(mode, sig, n_obs=40, n_test=30, seed=0, tol=0.7, lr=0.15):
    rng = np.random.RandomState(seed)
    T = norm(rng.randn(NW, D))                     # 真值模板 (系统看不到)
    obs = norm(T[:, None, :] + rng.randn(NW, n_obs, D) * sig)   # 观测流

    # ---------- 初始化: 都从第 1 次观测开始 ----------
    proto = obs[:, 0, :].copy()
    cnt = np.ones(NW)

    if mode != 'single':
        # ---------- 在线更新 (不知道标签, 用最近模板 + 门控) ----------
        for t in range(1, n_obs):
            # 打乱顺序 (模拟真实流)
            order = rng.permutation(NW)
            for i in order:
                o = obs[i, t]
                s = proto @ o                       # 与所有模板的相似度
                j = int(np.argmax(s))
                thr = tol if mode == 'hard' else 0.4
                if s[j] > thr:                      # ★ 门控: 相似度够才更新
                    if mode == 'median':
                        # 中位数: 累积样本, 取中位数
                        cnt[j] += 1
                        # 近似: 用加权平均模拟中位数 (对离群更稳)
                        proto[j] = proto[j]*(1 - 0.05) + o*0.05
                    else:
                        proto[j] = proto[j]*(1 - lr) + o*lr
                    proto[j] = proto[j] / (np.linalg.norm(proto[j]) + 1e-9)

    # ---------- 评价 ----------
    q1 = float(np.mean(np.sum(proto * T, axis=1)))           # ① 模板质量
    # ② 识别率
    test = norm(T[:,None,:] + rng.randn(NW, n_test, D) * sig)          # 新观测
    ok = 0; tot = 0
    for i in range(NW):
        for t_ in range(n_test):
            j = int(np.argmax(proto @ test[i, t_]))
            ok += (j == i); tot += 1
    return q1, ok / tot


print('=' * 84)
print('公平对比: 原型记忆能否降噪 (两组都只用含噪观测流)')
print('=' * 84)
print()
print('  %-8s %-16s %-16s %-16s %-16s' % ('噪声', 'A 单样本', 'B 软门控', 'C 硬门控', 'D 中位数'))
print('  %-8s %-16s %-16s %-16s %-16s' % ('', '质量/识别', '质量/识别', '质量/识别', '质量/识别'))
print('  ' + '-' * 80)
RES = {}
for sig in [0.0, 0.2, 0.4, 0.6, 0.9, 1.2]:
    row = {}
    for mode, nm in [('single', 'A'), ('soft', 'B'), ('hard', 'C'), ('median', 'D')]:
        q, a = run(mode, sig)
        row[nm] = (q, a)
    RES[sig] = row
    print('  %-8.1f %-16s %-16s %-16s %-16s' % (
        sig,
        '%.3f/%.3f' % row['A'], '%.3f/%.3f' % row['B'],
        '%.3f/%.3f' % row['C'], '%.3f/%.3f' % row['D']))

print()
print('=' * 84)
print('识别率提升 (相对单样本)')
print('=' * 84)
print('  %-8s %-14s %-14s %-14s' % ('噪声', 'B 软门控', 'C 硬门控', 'D 中位数'))
for sig, row in RES.items():
    print('  %-8.1f %+-14.3f %+-14.3f %+-14.3f %s' % (
        sig, row['B'][1]-row['A'][1], row['C'][1]-row['A'][1], row['D'][1]-row['A'][1],
        '★' if max(row['B'][1], row['C'][1], row['D'][1]) > row['A'][1] + 0.05 else ''))

print()
print('  随机基线 = %.3f' % (1/NW))
print('  用时 %.2fs' % (time.time() - t0))
