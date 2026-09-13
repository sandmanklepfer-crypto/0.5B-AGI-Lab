#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_drift.py — 代码任务闭环 (concept drift 版: 世界会变)
==========================================================
真正的"无限前进"场景: 同一任务类型的规则会随时间改变
  例: 第0轮 add = a+b; 第K轮 add 变成 a+b+1 (世界改规则了)

关键问题:
  固定记忆 → 旧数据成为"错误知识" → 会拖累
  需要: 遗忘机制 / 时间加权 / 变化检测

四模式对照:
  A 无记忆      只学当前          → 遗忘历史, 但适应快
  B 配额记忆    混合历史          → 保持历史, 但被旧知识拖累
  C 时间加权    近期数据权重大     → 兼顾
  D 变化检测    检测到变化就清空   → 主动适应

世界变化速度: 每 CHANGE_EVERY 轮, 随机某类规则改变
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)

# 20 类规则 (可变版本: 用偏移量表示)
BASE = [
    ('add',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b,o:a+b+o),
    ('sub',  lambda r:(r.randint(3,9), r.randint(1,3)), lambda a,b,o:a-b+o),
    ('mul',  lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b,o:a*b+o),
    ('max',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b,o:max(a,b)+o),
    ('min',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b,o:min(a,b)+o),
    ('abs',  lambda r:(r.randint(-9,-1),0),             lambda a,b,o:abs(a)+o),
    ('doub', lambda r:(r.randint(1,9), 0),              lambda a,b,o:a*2+o),
    ('half', lambda r:(r.randint(2,9)*2,0),             lambda a,b,o:a//2+o),
    ('sqr',  lambda r:(r.randint(1,6), 0),              lambda a,b,o:a*a+o),
    ('neg',  lambda r:(r.randint(1,9), 0),              lambda a,b,o:-a+o),
    ('inc',  lambda r:(r.randint(1,9), 0),              lambda a,b,o:a+1+o),
    ('dec',  lambda r:(r.randint(1,9), 0),              lambda a,b,o:a-1+o),
    ('sum3', lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b,o:a+b+3+o),
    ('twice',lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b,o:(a+b)*2+o),
    ('diff', lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b,o:abs(a-b)+o),
    ('fmul', lambda r:(r.randint(1,4), r.randint(1,4)), lambda a,b,o:a*b+1+o),
    ('fadd', lambda r:(r.randint(1,6), r.randint(1,6)), lambda a,b,o:a+b-1+o),
    ('dbl',  lambda r:(r.randint(1,9), 0),              lambda a,b,o:a-2+o),
    ('tri',  lambda r:(r.randint(1,9), 0),              lambda a,b,o:a*3+o),
    ('quad', lambda r:(r.randint(1,9), 0),              lambda a,b,o:a*4+o),
]
NC = len(BASE)
D = 32


def feat(cls, args):
    v = np.zeros(D)
    v[cls] = 1.0
    v[20] = args[0] / 10.0
    v[21] = (args[1] if len(args) > 1 else 0) / 10.0
    v[22] = 1.0 if len(args) > 1 else 0.0
    v[23] = 1.0
    return v


def sample(cls, off, r, n):
    name, gen, fn = BASE[cls]
    X = []; Y = []
    for _ in range(n):
        a = gen(r)
        X.append(feat(cls, a)); Y.append(fn(*a, off))
    return np.array(X), np.array(Y, dtype=float)


def run(mode, rounds=4, batch=40, quota=12, lam=1e-2, change_every=12, drift=2.0):
    """世界: 每 change_every 轮, 随机一类规则偏移 +drift"""
    W = np.zeros(D)
    memX = []; memY = []; memW = []          # memW = 权重(新旧)
    offsets = np.zeros(NC)                    # 世界真实偏移
    seen = []
    accs = []
    changed_at = []

    for t in range(NC * rounds):
        # ★ 世界变化
        if t > 0 and t % change_every == 0:
            c = rng.randint(NC)
            offsets[c] += rng.choice([-drift, drift])
            changed_at.append((t, c))
            if mode == 'detect':
                # 变化检测: 清掉该类记忆
                keep = [(x, y, w) for x, y, w in zip(memX, memY, memW) if int(np.argmax(x[:20])) != c]
                if keep:
                    memX, memY, memW = map(list, zip(*keep))
                else:
                    memX, memY, memW = [], [], []

        cls = t % NC
        if cls not in seen: seen.append(cls)
        Xn, Yn = sample(cls, offsets[cls], rng, batch)

        if mode == 'none':
            X, Y = Xn, Yn
        elif mode == 'quota':
            X = np.vstack([np.array(memX), Xn]) if memX else Xn
            Y = np.concatenate([np.array(memY), Yn]) if memY else Yn
        elif mode == 'time':
            X = np.vstack([np.array(memX), Xn]) if memX else Xn
            Y = np.concatenate([np.array(memY), Yn]) if memY else Yn
        else:  # detect
            X = np.vstack([np.array(memX), Xn]) if memX else Xn
            Y = np.concatenate([np.array(memY), Yn]) if memY else Yn

        # 学习 (时间加权: 新数据权重大)
        if mode == 'time' and memX:
            wts = np.concatenate([np.full(len(memX), 0.3), np.ones(len(Xn))])
            Xw = X * wts[:, None]; Yw = Y * wts
            W = np.linalg.solve(Xw.T @ X + lam * np.eye(D), Xw.T @ Y)
        else:
            W = np.linalg.solve(X.T @ X + lam * np.eye(D), X.T @ Y)

        # 记忆写入
        if mode in ('quota', 'time', 'detect'):
            memX += list(Xn); memY += list(Yn); memW += [1.0] * len(Xn)
            if mode in ('quota', 'time'):     # ★ 时间加权也限配额
                SX = np.array(memX); SY = np.array(memY)
                cid = np.array([int(np.argmax(x[:20])) for x in SX])
                KX = []; KY = []
                for c in range(NC):
                    m = cid == c
                    if m.sum() > 0: KX.append(SX[m][:quota]); KY.append(SY[m][:quota])
                if KX: memX = list(np.vstack(KX)); memY = list(np.concatenate(KY))

        # 测所有历史类型 (用【当前】世界规则)
        if t % 6 == 5 and len(seen) >= 2:
            g = 0; tt = 0
            for c in seen:
                Xt, Yt = sample(c, offsets[c], rng, 5)
                pr = Xt @ W
                g += (np.abs(pr - Yt) <= 0.15 * (np.abs(Yt) + 1.0)).mean(); tt += 1
            accs.append(g / tt)
    return np.array(accs), len(memX), changed_at


print('=' * 78)
print('代码任务闭环 — concept drift 版 (世界每 %d 轮改一次规则)' % 12)
print('=' * 78)
print('  %-12s %-40s %-8s %s' % ('模式', '历史类别准确率曲线', '最终', '记忆条数'))
for mode, nm in [('none', 'A 无记忆'), ('quota', 'B 配额记忆'),
                 ('time', '★C 时间加权'), ('detect', '★D 变化检测')]:
    acc, nmem, ch = run(mode)
    curve = ' '.join('%.2f' % a for a in acc[:14])
    print('  %-12s %-40s %-8.3f %d' % (nm, curve, acc[-1], nmem))
print()
print('  世界变化点: %s' % str([c for _, c in run('none')[2]][:6]))
print('  判据: drift 场景下, 无记忆/纯配额 应差; 时间加权/变化检测 应好')
print('  用时 %.1fs' % (time.time() - t0))
