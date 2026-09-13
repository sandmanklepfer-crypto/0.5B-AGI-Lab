#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stress_v2.py — 用「原型记忆」加固语义识别这一环
==================================================
上一轮的压力测试暴露: 语义识别(最近邻)在噪声 0.2 以上崩溃 (0.975→0.050)
本版用今天验证过的「配额记忆」思路加固:

  ★ 核心: 记忆不只存「词→数字」, 还存「词→去噪原型」
  
  运作:
    ① 每次观测到一个含噪嵌入
    ② 找最近的【原型】(不是原始嵌入)
    ③ 若距离在容差内 → 这是"内点" → 用鲁棒平均更新原型
       (多次观测平均 → 噪声按 √N 下降)
    ④ 若距离超容差 → "离群点" → 不更新 (防污染)
    
  鸡生蛋问题: 不知是哪个词, 怎么知道往哪个原型累加?
    → 答案: 不需要知道! 只需"最近的" + "容差判定"
    → 正确归属会自我强化, 错误归属被容差挡掉

对比四组 (噪声扫描):
  A 原始最近邻      (上一轮的方案, 基线)
  B 原型记忆        (本版)
  C 原型 + 数字反馈   (再加一层: 用和的正确性验证)
  D 直接ID          (上界参照)

任务: 20个伪数字词, 求两词的和 mod 10, 映射每15轮漂移
"""
import numpy as np, time

t0 = time.time()

Vn = np.load('/workspace/_cache_V.npy')
NW = 20
E896 = Vn[:NW]
mu = E896.mean(0)
_, _, Vt = np.linalg.svd(E896 - mu, full_matrices=False)
E = (E896 - mu) @ Vt[:10].T                     # (20,10) 干净的语义坐标
E = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)
D = E.shape[1]


def run(mode, sig=0.0, rounds=25, drift_every=15, seed=0):
    """mode: 'raw' | 'proto' | 'proto_fb' | 'id'"""
    rng = np.random.RandomState(seed)
    mapping = rng.randint(0, 10, NW)
    est = np.full(NW, -1)
    # ★ 原型 (初值 = 一次含噪观测, 模拟"从零开始")
    proto = E + rng.randn(NW, D) * sig * 1.5
    proto = proto / (np.linalg.norm(proto, axis=1, keepdims=True) + 1e-9)
    cnt = np.ones(NW) * 1.0
    accs = []

    TOL = 0.6                                    # 容差 (归一化后)

    def recog(obs):
        o = obs / (np.linalg.norm(obs) + 1e-9)
        if mode == 'raw':
            s = (E / (np.linalg.norm(E, axis=1, keepdims=True)+1e-9)) @ o
            return int(np.argmax(s)), 1.0
        s = proto @ o
        j = int(np.argmax(s))
        return j, float(s[j])

    for rd in range(rounds):
        if rd > 0 and rd % drift_every == 0:
            c = rng.randint(NW); mapping[c] = rng.randint(0, 10)

        # ---------- 探索: 学映射 + 更新原型 ----------
        for _ in range(6):
            i = rng.randint(NW)
            obs = E[i] + rng.randn(D) * sig
            wi, sim = recog(obs)
            # ★ 鲁棒原型更新
            if mode in ('proto', 'proto_fb') and sim > TOL:
                o = obs / (np.linalg.norm(obs) + 1e-9)
                proto[wi] = (proto[wi] * cnt[wi] + o) / (cnt[wi] + 1.0)
                proto[wi] /= (np.linalg.norm(proto[wi]) + 1e-9)
                cnt[wi] += 1.0
            if est[wi] < 0:
                est[wi] = mapping[i]

        # ---------- 测试: 求和 ----------
        ok = 0
        for _ in range(8):
            i, j = rng.randint(0, NW, 2)
            true = (mapping[i] + mapping[j]) % 10
            if mode == 'id':
                wi, wj = i, j
            else:
                wi, _ = recog(E[i] + rng.randn(D) * sig)
                wj, _ = recog(E[j] + rng.randn(D) * sig)
            ai = est[wi] if est[wi] >= 0 else rng.randint(0, 10)
            aj = est[wj] if est[wj] >= 0 else rng.randint(0, 10)
            pred = (ai + aj) % 10
            good = (pred == true)
            ok += good
            # ★ 数字反馈: 对了 → 强化归属 (更新原型); 错了 → 不更新
            if mode == 'proto_fb' and good:
                for k, w in [(i, wi), (j, wj)]:
                    o = (E[k] + rng.randn(D) * sig)
                    o = o / (np.linalg.norm(o) + 1e-9)
                    proto[w] = (proto[w] * cnt[w] + o) / (cnt[w] + 1.0)
                    proto[w] /= (np.linalg.norm(proto[w]) + 1e-9)
                    cnt[w] += 1.0
        accs.append(ok / 8)
    return np.mean(accs[-8:])


print('=' * 82)
print('原型记忆加固: 语义识别在噪声下的鲁棒性')
print('=' * 82)
print()
print('  %-8s %-14s %-14s %-16s %s' % ('噪声', 'A 原始最近邻', 'B 原型记忆',
                                      'C 原型+数字反馈', 'D 直接ID(上界)'))
print('  ' + '-' * 78)
RES = {}
for sig in [0.0, 0.1, 0.2, 0.3, 0.5, 0.8]:
    r = {}
    for mode, nm in [('raw', 'A'), ('proto', 'B'), ('proto_fb', 'C'), ('id', 'D')]:
        r[nm] = run(mode, sig=sig)
    RES[sig] = r
    print('  %-8.1f %-14.3f %-14.3f %-16.3f %-14.3f' % (
        sig, r['A'], r['B'], r['C'], r['D']))

print()
print('=' * 82)
print('改善幅度 (相对原始最近邻)')
print('=' * 82)
print('  %-8s %-16s %-16s' % ('噪声', 'B 提升', 'C 提升'))
for sig, r in RES.items():
    db = r['B'] - r['A']; dc = r['C'] - r['A']
    print('  %-8.1f %+-16.3f %+-16.3f %s' % (sig, db, dc,
          '★ 显著' if dc > 0.05 else ''))

print()
print('  随机基线 = 0.10')
print('  用时 %.2fs' % (time.time() - t0))
