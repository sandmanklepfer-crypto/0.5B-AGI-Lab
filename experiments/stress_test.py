#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stress_test.py — 协同压力测试 (修正设计)
==========================================
任务: 给两个「伪数字词」, 求它们的和 mod 10

三个阶段, 三个零件各司其职:
  ① 探索期: 展示单个词 → 世界回答它的数字 → 【记忆】学会映射
  ② 测试期: 展示两个词 → 认词(语义) + 查映射(记忆) + 算和(形式系统)
  ③ 漂移:   映射改变 → 记忆必须重新校准

四组对照:
  A 完整      (语义 + 记忆 + 形式系统)
  B 无记忆    (探索不保存 → 测试靠猜)      → 应失败
  C 无形式系统 (从嵌入直接回归和, 不用映射)  → 应差
  D 无语义    (直接给词 ID, 跳过认词)      → 参照上界
"""
import numpy as np, json, sys, time

t0 = time.time()
sys.path.insert(0, '/workspace')

Vn = np.load('/workspace/_cache_V.npy')
NW = 20
E896 = Vn[:NW]
mu = E896.mean(0)
_, _, Vt = np.linalg.svd(E896 - mu, full_matrices=False)
E = (E896 - mu) @ Vt[:10].T                    # 降维 (10维足够)
En = E / (np.linalg.norm(E, axis=1, keepdims=True) + 1e-9)


def recognize(e):
    """① 语义识别: 从嵌入认出是哪个词"""
    return int(np.argmax(En @ (e / (np.linalg.norm(e) + 1e-9))))


def run(mode, rounds=40, drift_every=15, seed=0, n_explore=5, n_test=8):
    rng = np.random.RandomState(seed)
    mapping = rng.randint(0, 10, NW)           # ★ 世界隐藏映射
    est = np.full(NW, -1)                       # ② 记忆: 词 → 估计数字
    conf = np.zeros(NW)
    # C 组的直接回归器 (累积数据, 闭式)
    RX = []; RY = []
    accs = []; drift_at = []

    for rd in range(rounds):
        if rd > 0 and rd % drift_every == 0:    # ③ 世界漂移
            c = rng.randint(NW)
            mapping[c] = rng.randint(0, 10)
            drift_at.append(rd)

        # ---------- 探索期: 学映射 ----------
        for _ in range(n_explore):
            i = rng.randint(NW)
            wi = i if mode == 'nosem' else recognize(E[i])
            # 系统猜, 世界回答
            guess = est[wi] if est[wi] >= 0 else rng.randint(0, 10)
            ok = (guess == mapping[i])
            if mode != 'nomem':                 # B 组不保存
                if ok: conf[wi] = min(conf[wi] + 1, 5)
                else:
                    conf[wi] = max(conf[wi] - 1, 0)
                    if conf[wi] == 0:           # 不确定 → 采纳新观测
                        est[wi] = mapping[i]; conf[wi] = 1

        # ---------- 测试期: 求和 ----------
        ok_cnt = 0
        for _ in range(n_test):
            i, j = rng.randint(0, NW, 2)
            true = (mapping[i] + mapping[j]) % 10
            wi = i if mode == 'nosem' else recognize(E[i])
            wj = j if mode == 'nosem' else recognize(E[j])

            if mode == 'nonet':                 # C: 无形式系统, 直接回归
                f = E[i] + E[j]
                if len(RY) >= 12:
                    Xa = np.array(RX)
                    W = np.linalg.solve(Xa.T @ Xa + 0.05*np.eye(10), Xa.T @ np.eye(10)[RY])
                    pred = int(np.argmax(f @ W))
                else:
                    pred = rng.randint(0, 10)
                RX.append(f); RY.append(true)
                if len(RY) > 400: RX.pop(0); RY.pop(0)
            else:                               # A/B/D: 记忆 + 形式系统
                ai = est[wi] if est[wi] >= 0 else rng.randint(0, 10)
                aj = est[wj] if est[wj] >= 0 else rng.randint(0, 10)
                pred = (ai + aj) % 10

            ok_cnt += (pred == true)

            # 从和反馈改进记忆 (A/D: 有记忆时)
            if mode not in ('nomem', 'nonet'):
                other = est[wj] if est[wj] >= 0 else 0
                implied = (true - other) % 10
                if est[wi] != implied and conf[wi] < 2:
                    est[wi] = implied; conf[wi] = 1
        accs.append(ok_cnt / n_test)

    return np.array(accs), drift_at


print('=' * 80)
print('协同压力测试: 认词(语义) + 查映射(记忆) + 算和(形式系统)')
print('=' * 80)
print('  %d 个伪数字词, 每 15 轮漂移一次映射, 40 轮' % NW)
print()
print('  %-18s %-44s %-8s %s' % ('配置', '准确率曲线', '最终', '漂移后恢复'))
print('  ' + '-' * 76)
res = {}
for mode, nm in [('full', '★A 完整'), ('nomem', 'B 无记忆'),
                 ('nonet', 'C 无形式系统'), ('nosem', 'D 无语义(参照)')]:
    acc, da = run(mode)
    rec = []
    for d in da:
        seg = acc[d:d+10]
        idx = np.where(seg > 0.5)[0]
        rec.append(int(idx[0]) if len(idx) else 99)
    res[nm] = acc[-1]
    print('  %-18s %-44s %-8.3f %s' % (nm, ' '.join('%.2f' % a for a in acc[:11]),
                                       acc[-1], ('%.1f轮' % np.mean(rec)) if rec else '—'))

print()
print('  随机基线 = 0.10')
print('  用时 %.1fs' % (time.time() - t0))
