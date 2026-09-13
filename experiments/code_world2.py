#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_world2.py — 代码任务闭环 (修正版)
========================================
修正 code_world.py 的致命 bug:
  ① 正确候选永远是 index 0 → 系统只要"永远选第0个"就得 0.95
  ② 用"类别独热"当输入 → 等于查表, 不算理解

本版:
  ① 正确候选位置【随机】 (每道题打乱)
  ② 输入是【输入-输出样例】(不是类别标签)
     → 系统必须从样例推断"哪个候选函数匹配"
  ③ 世界 = Python 执行 (客观对错)

任务: 给 3 组 (输入, 输出) 样例 + K 个候选实现
      系统选哪个候选能复现这些样例

对照:
  A 无记忆     只学读出层      → 应灾难性遗忘
  B 配额记忆   每类保留12条    → 应保持
  C 全量记忆   不删            → 上界
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)

# ==================== 任务库: 20 类, 每类 1 正确 + 4 错 ====================
def mk_tasks():
    T = []
    A = lambda: [lambda a,b:a+b,   lambda a,b:a-b,  lambda a,b:a*b,   lambda a,b:abs(a-b), lambda a,b:max(a,b)]
    S = lambda: [lambda a,b:a-b,   lambda a,b:a+b,  lambda a,b:b-a,   lambda a,b:a*b,      lambda a,b:a//(b+1)]
    M = lambda: [lambda a,b:a*b,   lambda a,b:a+b,  lambda a,b:a-b,   lambda a,b:max(a,b), lambda a,b:a**2]
    X = lambda: [lambda a,b:max(a,b),lambda a,b:min(a,b),lambda a,b:a+b,lambda a,b:abs(a-b),lambda a,b:a*b]
    N = lambda: [lambda a,b:min(a,b),lambda a,b:max(a,b),lambda a,b:a-b,lambda a,b:abs(a-b),lambda a,b:a//2]
    T.append(('add',  lambda r:(r.randint(1,9),  r.randint(1,9)), A()))
    T.append(('sub',  lambda r:(r.randint(3,9),  r.randint(1,3)), S()))
    T.append(('mul',  lambda r:(r.randint(1,5),  r.randint(1,5)), M()))
    T.append(('max',  lambda r:(r.randint(1,9),  r.randint(1,9)), X()))
    T.append(('min',  lambda r:(r.randint(1,9),  r.randint(1,9)), N()))
    T.append(('abs',  lambda r:(r.randint(-9,-1),0),              [lambda a,b:abs(a),lambda a,b:a,lambda a,b:-a,lambda a,b:a*a,lambda a,b:0]))
    T.append(('doub', lambda r:(r.randint(1,9),  0),              [lambda a,b:a*2,lambda a,b:a+2,lambda a,b:a*a,lambda a,b:a//2,lambda a,b:a]))
    T.append(('half', lambda r:(r.randint(2,9)*2,0),              [lambda a,b:a//2,lambda a,b:a*2,lambda a,b:a-2,lambda a,b:a%2,lambda a,b:a]))
    T.append(('sqr',  lambda r:(r.randint(1,6),  0),              [lambda a,b:a*a,lambda a,b:a*2,lambda a,b:a+2,lambda a,b:a**3,lambda a,b:a]))
    T.append(('neg',  lambda r:(r.randint(1,9),  0),              [lambda a,b:-a,lambda a,b:a,lambda a,b:abs(a),lambda a,b:a-1,lambda a,b:0]))
    T.append(('even', lambda r:(r.randint(1,9),  0),              [lambda a,b:a%2==0,lambda a,b:a%2==1,lambda a,b:a>5,lambda a,b:a<5,lambda a,b:True]))
    T.append(('odd',  lambda r:(r.randint(1,9),  0),              [lambda a,b:a%2==1,lambda a,b:a%2==0,lambda a,b:a>5,lambda a,b:False,lambda a,b:a<5]))
    T.append(('inc',  lambda r:(r.randint(1,9),  0),              [lambda a,b:a+1,lambda a,b:a-1,lambda a,b:a*2,lambda a,b:a,lambda a,b:a+2]))
    T.append(('dec',  lambda r:(r.randint(1,9),  0),              [lambda a,b:a-1,lambda a,b:a+1,lambda a,b:a//2,lambda a,b:a,lambda a,b:-a]))
    T.append(('gt5',  lambda r:(r.randint(1,9),  0),              [lambda a,b:a>5,lambda a,b:a<5,lambda a,b:a==5,lambda a,b:a>=5,lambda a,b:False]))
    T.append(('lt5',  lambda r:(r.randint(1,9),  0),              [lambda a,b:a<5,lambda a,b:a>5,lambda a,b:a==5,lambda a,b:a<=5,lambda a,b:True]))
    T.append(('sum3', lambda r:(r.randint(1,5),  r.randint(1,5)), [lambda a,b:a+b+3,lambda a,b:a+b-3,lambda a,b:a*b+3,lambda a,b:a+b,lambda a,b:(a+b)*3]))
    T.append(('twice',lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:(a+b)*2,lambda a,b:a+b,lambda a,b:a*b,lambda a,b:abs(a-b)*2,lambda a,b:max(a,b)*2]))
    T.append(('diff', lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:abs(a-b),lambda a,b:a+b,lambda a,b:a-b,lambda a,b:a*b,lambda a,b:max(a,b)]))
    T.append(('eq',   lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:a==b,lambda a,b:a!=b,lambda a,b:a>b,lambda a,b:a<b,lambda a,b:True]))
    return T

TASKS = mk_tasks()
NC, K = len(TASKS), 5


def make_instance(cls, r):
    """生成一道题: 随机打乱候选, 返回 (样例, 正确位置)"""
    name, gen, cands = TASKS[cls]
    # 3 组样例 (确保能区分正确候选)
    samples = []
    for _ in range(3):
        args = gen(r)
        try:
            out = cands[0](*args)
        except Exception:
            out = None
        samples.append((args, out))
    # ★ 打乱候选顺序 (正确位置随机)
    perm = r.permutation(K)
    shuffled = [cands[p] for p in perm]
    correct_pos = int(np.where(perm == 0)[0][0])
    return samples, shuffled, correct_pos


def sample_vec(samples, D):
    """★ 输入 = 样例的 (输入,输出) 数值, 不是类别标签"""
    v = np.zeros(D)
    for i, (args, out) in enumerate(samples[:3]):
        base = i * 6
        if base + 5 < D:
            v[base] = args[0] / 10.0
            v[base+1] = (args[1] if len(args) > 1 else 0) / 10.0
            v[base+2] = (out if isinstance(out, (int, float)) else (1.0 if out else 0.0)) / 10.0
            v[base+3] = 1.0 if len(args) > 1 else 0.0
            v[base+4] = 1.0 if isinstance(out, bool) else 0.0
    return v


D = 24
rng2 = np.random.RandomState(1)
Q, _ = np.linalg.qr(rng2.randn(D, D))
A = Q * 1.15
Qt = np.ascontiguousarray(A.T)
NPH = 6
PHW = np.array([1.0, 1.618, 2.414, 1.732, 2.236, 1.414])
ph = rng2.rand(NPH) * 2 * np.pi


def brain(x, steps=3):
    global ph
    x = x.copy()
    for _ in range(steps):
        x = 0.5 * x + 0.5 * np.tanh(x @ Qt)
        d = ph[None, :] - ph[:, None]
        ph = ph + 0.05 * (PHW + 0.5 * np.sin(d).mean(1))
    return x


def run(mode, steps=800, lr=0.3, quota=12):
    W = rng2.randn(K, D) * 0.01
    base = 0.0
    mem = []
    cls_seen = []
    acc_hist = []

    for t in range(steps):
        cls = t % NC
        if cls not in cls_seen: cls_seen.append(cls)
        samples, cands, corr = make_instance(cls, rng)
        h = brain(sample_vec(samples, D))

        z = W @ h
        if mode in ('quota', 'all'):
            ms = [m for m in mem if m[0] == cls]
            if ms:
                v = np.zeros(K)
                for _, hm, ch in ms:
                    s = float(hm @ h) / (np.linalg.norm(hm)*np.linalg.norm(h)+1e-9)
                    if s > 0.5: v[ch] += s
                z = z + 0.6 * v

        p = np.exp(z - z.max()); p /= p.sum()
        choice = int(rng.choice(K, p=p))

        # ★ 世界执行: 候选能不能复现样例?
        ok = 1.0
        for args, out in samples:
            try:
                got = cands[choice](*args)
            except Exception:
                got = None
            if got != out: ok = 0.0; break

        base = 0.99*base + 0.01*ok
        g = np.zeros(K); g[choice] = 1.0
        W = W + lr * (ok - base) * np.outer(g - p, h)
        W = np.clip(W, -3, 3)

        if mode in ('quota', 'all') and ok > 0.5:
            mem.append((cls, h.copy(), choice))
            if mode == 'quota':
                cnt = {}; keep = []
                for m in reversed(mem):
                    c = m[0]; cnt[c] = cnt.get(c, 0) + 1
                    if cnt[c] <= quota: keep.append(m)
                mem = list(reversed(keep))

        # 测: 所有历史类别
        if t % 40 == 39 and len(cls_seen) >= 2:
            acc = 0; tot = 0
            for c in cls_seen:
                for _ in range(3):
                    s2, cd2, cor2 = make_instance(c, rng)
                    h2 = brain(sample_vec(s2, D))
                    z2 = W @ h2
                    if mode in ('quota', 'all'):
                        ms = [m for m in mem if m[0] == c]
                        if ms:
                            v = np.zeros(K)
                            for _, hm, ch in ms:
                                s3 = float(hm @ h2)/(np.linalg.norm(hm)*np.linalg.norm(h2)+1e-9)
                                if s3 > 0.5: v[ch] += s3
                            z2 = z2 + 0.6*v
                    # 判对: 选中的候选要能复现样例
                    pick = int(np.argmax(z2))
                    good = 1
                    for args, out in s2:
                        try: got = cd2[pick](*args)
                        except Exception: got = None
                        if got != out: good = 0; break
                    acc += good; tot += 1
            acc_hist.append(acc/tot)
    return np.array(acc_hist), len(mem), len(cls_seen)


print('=' * 72)
print('代码任务闭环 (修正版) 20类 × 5候选, 正确位置随机, 输入=样例')
print('=' * 72)
print('  %-12s %-34s %-9s %s' % ('模式', '历史类别准确率曲线', '最终', '记忆条数'))
for mode, nm in [('none', 'A 无记忆'), ('quota', '★B 配额记忆'), ('all', 'C 全量记忆')]:
    acc, nmem, ncls = run(mode)
    curve = ' '.join('%.2f' % a for a in acc[:11])
    print('  %-12s %-34s %-9.3f %d' % (nm, curve, acc[-1], nmem))
print()
print('  随机基线 = 0.20')
print('  用时 %.1fs' % (time.time()-t0))
