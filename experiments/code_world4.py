#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_world4.py — 代码任务闭环 (标准范式: 逐步学习 + 经验回放)
==============================================================
前两版失败原因:
  code_world2: 要求程序归纳 → 不可学 (0.25 ≈ 随机)
  code_world3: 正确位置随机 → 记位置是错策略 → 记忆有害

本版 (标准持续学习范式):
  任务: 20 类代码计算规则, 输入参数 → 输出数值
  学习: 逐步 (一步只见一个任务类型的数据)
  世界: 执行真规则判对错 (客观)
  测: 对【所有历史类型】的准确率 → 灾难性遗忘?

三模式:
  A 无记忆     只学当前数据        → 应遗忘
  B 配额记忆   混合每类12条        → 应保持
  C 全量记忆   混合全部            → 上界
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)


def mk_rules():
    """20 类代码规则: (类型名, 参数生成, 真函数)"""
    R = []
    R.append(('add',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:a+b))
    R.append(('sub',  lambda r:(r.randint(3,9), r.randint(1,3)), lambda a,b:a-b))
    R.append(('mul',  lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b:a*b))
    R.append(('max',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:max(a,b)))
    R.append(('min',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:min(a,b)))
    R.append(('abs',  lambda r:(r.randint(-9,-1),0),             lambda a,b:abs(a)))
    R.append(('doub', lambda r:(r.randint(1,9), 0),              lambda a,b:a*2))
    R.append(('half', lambda r:(r.randint(2,9)*2,0),             lambda a,b:a//2))
    R.append(('sqr',  lambda r:(r.randint(1,6), 0),              lambda a,b:a*a))
    R.append(('neg',  lambda r:(r.randint(1,9), 0),              lambda a,b:-a))
    R.append(('inc',  lambda r:(r.randint(1,9), 0),              lambda a,b:a+1))
    R.append(('dec',  lambda r:(r.randint(1,9), 0),              lambda a,b:a-1))
    R.append(('sum3', lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b:a+b+3))
    R.append(('twice',lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:(a+b)*2))
    R.append(('diff', lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:abs(a-b)))
    R.append(('fmul', lambda r:(r.randint(1,4), r.randint(1,4)), lambda a,b:a*b+1))
    R.append(('fadd', lambda r:(r.randint(1,6), r.randint(1,6)), lambda a,b:a+b-1))
    R.append(('dbl',  lambda r:(r.randint(1,9), 0),              lambda a,b:a-2))
    R.append(('tri',  lambda r:(r.randint(1,9), 0),              lambda a,b:a*3))
    R.append(('quad', lambda r:(r.randint(1,9), 0),              lambda a,b:a*4))
    return R

RULES = mk_rules()
NC = len(RULES)
D = 32


def feat(cls, args):
    """特征: 类型独热 + 参数"""
    v = np.zeros(D)
    v[cls] = 1.0                       # ★ 独热覆盖全部 20 类
    v[20] = args[0] / 10.0
    v[21] = (args[1] if len(args) > 1 else 0) / 10.0
    v[22] = 1.0 if len(args) > 1 else 0.0
    v[23] = 1.0
    return v


def sample(cls, r, n):
    name, gen, fn = RULES[cls]
    X = []; Y = []
    for _ in range(n):
        a = gen(r)
        X.append(feat(cls, a))
        Y.append(fn(*a))
    return np.array(X), np.array(Y, dtype=float)


def run(mode, rounds=3, batch=40, quota=12, lam=1e-2):
    """rounds: 每类学多少轮; batch: 每轮样本数"""
    W = np.zeros(D)                     # 线性映射 (特征 → 输出)
    memX = []; memY = []
    acc_hist = []
    cls_seen = []

    for t in range(NC * rounds):
        cls = t % NC
        if cls not in cls_seen: cls_seen.append(cls)
        Xn, Yn = sample(cls, rng, batch)

        # 组装训练集
        if mode == 'none':
            X, Y = Xn, Yn
        elif mode == 'quota':
            X = np.vstack([np.array(memX), Xn]) if memX else Xn
            Y = np.concatenate([np.array(memY), Yn]) if memY else Yn
        else:  # all
            X = np.vstack([np.array(memX), Xn]) if memX else Xn
            Y = np.concatenate([np.array(memY), Yn]) if memY else Yn

        # 闭式最小二乘 (逐步更新)
        W = np.linalg.solve(X.T @ X + lam * np.eye(D), X.T @ Y)

        # 写入记忆
        if mode in ('quota', 'all'):
            memX += list(Xn); memY += list(Yn)
            if mode == 'quota':
                # ★ 每类配额 (按类分组保留)
                SX = np.array(memX); SY = np.array(memY)
                KX = []; KY = []
                for c in range(NC):
                    m = np.array([feat_matches(SX[i], c) for i in range(len(SX))])
                    if m.sum() > 0:
                        KX.append(SX[m][:quota]); KY.append(SY[m][:quota])
                if KX:
                    memX = list(np.vstack(KX)); memY = list(np.concatenate(KY))

        # 测所有历史类型
        if t % 5 == 4 and len(cls_seen) >= 2:
            good = 0; tot = 0
            for c in cls_seen:
                Xt, Yt = sample(c, rng, 5)
                pred = Xt @ W
                # 判对: 相对误差 < 15%
                ok = (np.abs(pred - Yt) <= 0.15 * (np.abs(Yt) + 1.0)).mean()
                good += ok; tot += 1
            acc_hist.append(good / tot)
    return np.array(acc_hist), len(memX), len(cls_seen)


def feat_matches(x, c):
    """该特征是否属于类型 c"""
    return int(np.argmax(x[:20])) == c


print('=' * 76)
print('代码任务闭环 (标准持续学习范式)  %d类规则, 逐步学习' % NC)
print('=' * 76)
print('  %-12s %-38s %-9s %s' % ('模式', '历史类别准确率曲线', '最终', '记忆条数'))
for mode, nm in [('none', 'A 无记忆'), ('quota', '★B 配额记忆'), ('all', 'C 全量记忆')]:
    acc, nmem, ncls = run(mode)
    curve = ' '.join('%.2f' % a for a in acc[:13])
    print('  %-12s %-38s %-9.3f %d' % (nm, curve, acc[-1], nmem))
print()
print('  判据: A 应随新类引入下降(遗忘); B 应保持')
print('  用时 %.1fs' % (time.time() - t0))
