#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_world.py — 代码任务闭环系统
==================================
世界 = Python 解释器 (能判对错, 客观)

任务: 从 K 个候选实现中选出正确的
  类别: 20 种代码任务类型 (滚动引入新的)
  实例: 输入参数每次随机 (世界持续变化)

系统:
  正交核 A   → 任务表示演化 (提供特征)
  相位通道   → 时间 (永不重复)
  读出层     → 选候选 (REINFORCE 学习)
  配额记忆   → 每类保留固定条数 (防遗忘)

三组对照 (核心):
  A 无记忆   只学读出层          → 应灾难性遗忘
  B 配额记忆 每类12条            → 应保持
  C 全量记忆 不删                → 上界, 但容量爆

指标: 对【所有历史类别】的准确率随时间的变化
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

# ==================== 世界: 20 种代码任务 ====================
# 每类: (名称, 参数生成器, K 个候选函数, 正确索引)
def mk_tasks():
    T = []
    T.append(('add',  lambda r: (r.randint(1,9), r.randint(1,9)), [lambda a,b:a+b, lambda a,b:a-b, lambda a,b:a*b, lambda a,b:a%b+1, lambda a,b:abs(a-b)]))
    T.append(('sub',  lambda r: (r.randint(1,9), r.randint(1,9)), [lambda a,b:a-b, lambda a,b:a+b, lambda a,b:b-a, lambda a,b:a*b, lambda a,b:a//(b+1)]))
    T.append(('mul',  lambda r: (r.randint(1,6), r.randint(1,6)), [lambda a,b:a*b, lambda a,b:a+b, lambda a,b:a**b, lambda a,b:a-b, lambda a,b:max(a,b)]))
    T.append(('max',  lambda r: (r.randint(1,9), r.randint(1,9)), [lambda a,b:max(a,b), lambda a,b:min(a,b), lambda a,b:a+b, lambda a,b:abs(a-b), lambda a,b:a]))
    T.append(('min',  lambda r: (r.randint(1,9), r.randint(1,9)), [lambda a,b:min(a,b), lambda a,b:max(a,b), lambda a,b:a-b, lambda a,b:abs(a-b), lambda a,b:b]))
    T.append(('abs',  lambda r: (r.randint(-9,-1), 0),           [lambda a,b:abs(a), lambda a,b:a, lambda a,b:-a, lambda a,b:a*a, lambda a,b:0-a-1]))
    T.append(('doub', lambda r: (r.randint(1,9), 0),             [lambda a,b:a*2, lambda a,b:a+2, lambda a,b:a*a, lambda a,b:a//2, lambda a,b:a]))
    T.append(('half', lambda r: (r.randint(2,9)*2, 0),           [lambda a,b:a//2, lambda a,b:a*2, lambda a,b:a-2, lambda a,b:a%2, lambda a,b:a]))
    T.append(('sqr',  lambda r: (r.randint(1,6), 0),             [lambda a,b:a*a, lambda a,b:a*2, lambda a,b:a+2, lambda a,b:a**3, lambda a,b:a]))
    T.append(('neg',  lambda r: (r.randint(1,9), 0),             [lambda a,b:-a, lambda a,b:a, lambda a,b:abs(a), lambda a,b:a-1, lambda a,b:0]))
    T.append(('even', lambda r: (r.randint(1,9), 0),             [lambda a,b:a%2==0, lambda a,b:a%2==1, lambda a,b:a>5, lambda a,b:a<5, lambda a,b:True]))
    T.append(('odd',  lambda r: (r.randint(1,9), 0),             [lambda a,b:a%2==1, lambda a,b:a%2==0, lambda a,b:a>5, lambda a,b:False, lambda a,b:a<5]))
    T.append(('inc',  lambda r: (r.randint(1,9), 0),             [lambda a,b:a+1, lambda a,b:a-1, lambda a,b:a*2, lambda a,b:a, lambda a,b:a+2]))
    T.append(('dec',  lambda r: (r.randint(1,9), 0),             [lambda a,b:a-1, lambda a,b:a+1, lambda a,b:a//2, lambda a,b:a, lambda a,b:-a]))
    T.append(('gt5',  lambda r: (r.randint(1,9), 0),             [lambda a,b:a>5, lambda a,b:a<5, lambda a,b:a==5, lambda a,b:a>=5, lambda a,b:False]))
    T.append(('lt5',  lambda r: (r.randint(1,9), 0),             [lambda a,b:a<5, lambda a,b:a>5, lambda a,b:a==5, lambda a,b:a<=5, lambda a,b:True]))
    T.append(('sum3', lambda r: (r.randint(1,5), r.randint(1,5)),[lambda a,b:a+b+3, lambda a,b:a+b-3, lambda a,b:a*b+3, lambda a,b:a+b, lambda a,b:(a+b)*3]))
    T.append(('twice',lambda r: (r.randint(1,9), r.randint(1,9)),[lambda a,b:(a+b)*2, lambda a,b:a+b, lambda a,b:a*b, lambda a,b:abs(a-b)*2, lambda a,b:max(a,b)*2]))
    T.append(('diff', lambda r: (r.randint(1,9), r.randint(1,9)),[lambda a,b:abs(a-b), lambda a,b:a+b, lambda a,b:a-b, lambda a,b:max(a,b)-min(a,b)+1, lambda a,b:a*b]))
    T.append(('samed',lambda r: (r.randint(1,9), r.randint(1,9)),[lambda a,b:a==b, lambda a,b:a!=b, lambda a,b:a>b, lambda a,b:a<b, lambda a,b:True]))
    return T

TASKS = mk_tasks()
NC = len(TASKS)          # 20 类
K = 5                    # 每类 5 个候选


def run_code(fn, args):
    """世界: 执行代码, 返回结果"""
    try:
        return fn(*args)
    except Exception:
        return None


# ==================== 系统 ====================
D = 24                    # 核维度
rng2 = np.random.RandomState(1)
Q, _ = np.linalg.qr(rng2.randn(D, D))
A = Q * 1.15
Qt = np.ascontiguousarray(A.T)
NPH = 6
PHW = np.array([1.0, 1.618, 2.414, 1.732, 2.236, 1.414])
ph = rng2.rand(NPH) * 2 * np.pi


def task_vector(cls, args):
    """任务表示: 类别独热 + 参数"""
    v = np.zeros(D)
    v[cls % 20] = 1.0
    v[20] = args[0] / 10.0
    v[21] = (args[1] if len(args) > 1 else 0) / 10.0
    v[22] = 1.0 if len(args) > 1 else 0.0
    v[23] = 0.0
    return v


def brain(x, steps=3):
    global ph
    x = x.copy()
    for _ in range(steps):
        x = 0.5 * x + 0.5 * np.tanh(x @ Qt)
        d = ph[None, :] - ph[:, None]
        ph = ph + 0.05 * (PHW + 0.5 * np.sin(d).mean(1))
    return x


def run(mode, steps=600, lr=0.3, quota=12):
    """mode: 'none' | 'quota' | 'all'"""
    W = rng2.randn(K, D) * 0.01
    base = 0.0
    mem = []                       # (cls, h, choice) 记忆条目
    cls_seen = []
    acc_hist = []

    for t in range(steps):
        cls = t % NC               # 滚动引入新类别
        if cls not in cls_seen:
            cls_seen.append(cls)
        name, gen, cands = TASKS[cls]
        args = gen(rng)

        x = task_vector(cls, args)
        h = brain(x)

        # 若该类有记忆条目 → 用记忆辅助 (最近邻 + 读出层)
        z = W @ h
        if mode in ('quota', 'all'):
            mem_same = [m for m in mem if m[0] == cls]
            if mem_same:
                # 记忆投票: 记住的选择
                vote = np.zeros(K)
                for _, hm, ch in mem_same:
                    sim = float(hm @ h) / (np.linalg.norm(hm) * np.linalg.norm(h) + 1e-9)
                    if sim > 0.5:
                        vote[ch] += sim
                z = z + 0.5 * vote

        p = np.exp(z - z.max()); p /= p.sum()
        choice = int(rng.choice(K, p=p))

        # ★ 世界: 执行代码, 判对错
        res = run_code(cands[choice], args)
        true_res = run_code(cands[0], args)      # 候选0 总正确 (见 mk_tasks)
        ok = 1.0 if (res is not None and res == true_res) else 0.0
        # 注意: 候选0 是正确实现, 所以"选0"=正确
        correct = (choice == 0)

        # 学习 (REINFORCE, 标量)
        base = 0.99 * base + 0.01 * ok
        g = np.zeros(K); g[choice] = 1.0
        W = W + lr * (ok - base) * np.outer(g - p, h)
        W = np.clip(W, -3, 3)

        # 记忆写入
        if mode in ('quota', 'all') and correct:
            mem.append((cls, h.copy(), choice))
            if mode == 'quota':
                # ★ 每类配额
                cnt = {}
                keep = []
                for m in reversed(mem):
                    c = m[0]
                    cnt[c] = cnt.get(c, 0) + 1
                    if cnt[c] <= quota:
                        keep.append(m)
                mem = list(reversed(keep))

        # 每 30 步测: 对所有历史类别的准确率
        if t % 30 == 29 and len(cls_seen) >= 2:
            acc = 0; tot = 0
            for c in cls_seen:
                _, g2, cd = TASKS[c]
                for _ in range(4):
                    a2 = g2(rng)
                    h2 = brain(task_vector(c, a2))
                    z2 = W @ h2
                    if mode in ('quota', 'all'):
                        ms = [m for m in mem if m[0] == c]
                        if ms:
                            v = np.zeros(K)
                            for _, hm, ch in ms:
                                s2 = float(hm @ h2) / (np.linalg.norm(hm) * np.linalg.norm(h2) + 1e-9)
                                if s2 > 0.5: v[ch] += s2
                            z2 = z2 + 0.5 * v
                    pk = int(np.argmax(z2))
                    acc += (pk == 0); tot += 1
            acc_hist.append(acc / tot)
    return np.array(acc_hist), len(mem), len(cls_seen)


print('=' * 68)
print('代码任务闭环 (20类任务 × %d候选, 世界=Python执行)' % K)
print('=' * 68)
print('  %-14s %-30s %-10s %s' % ('模式', '历史类别准确率曲线', '最终', '记忆条数'))
for mode, nm in [('none', 'A 无记忆'), ('quota', '★B 配额记忆'), ('all', 'C 全量记忆')]:
    acc, nmem, ncls = run(mode)
    curve = ' '.join('%.2f' % a for a in acc[:10])
    print('  %-14s %-30s %-10.3f %d' % (nm, curve, acc[-1], nmem))
print()
print('  随机基线 = %.2f (选对概率 1/%d)' % (1 / K, K))
print('  用时 %.1fs' % (time.time() - t0))
