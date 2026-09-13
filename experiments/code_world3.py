#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
code_world3.py — 代码任务闭环 (可学版)
========================================
code_world2 失败原因: 要求从样例反向推断函数 = 程序归纳 (不可学)

本版改成【等价性判断】:
  输入 = [样例输出们, 候选输出们]   (原始数值, 不直接给"是否相等")
  系统要学会: "这两组输出是否一致"
  对 K 个候选分别打分 → 选分数最高的

这既可学 (一致性检测), 又需要真理解 (不能靠猜位置)

世界 = Python 执行 (客观对错)
滚动引入新任务类型 → 测灾难性遗忘
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)


def mk_tasks():
    T = []
    T.append(('add',  lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:a+b,lambda a,b:a-b,lambda a,b:a*b,lambda a,b:abs(a-b),lambda a,b:max(a,b)]))
    T.append(('sub',  lambda r:(r.randint(3,9),  r.randint(1,3)), [lambda a,b:a-b,lambda a,b:a+b,lambda a,b:b-a,lambda a,b:a*b,lambda a,b:a//(b+1)]))
    T.append(('mul',  lambda r:(r.randint(1,5),  r.randint(1,5)), [lambda a,b:a*b,lambda a,b:a+b,lambda a,b:a-b,lambda a,b:max(a,b),lambda a,b:a**2]))
    T.append(('max',  lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:max(a,b),lambda a,b:min(a,b),lambda a,b:a+b,lambda a,b:abs(a-b),lambda a,b:a*b]))
    T.append(('min',  lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:min(a,b),lambda a,b:max(a,b),lambda a,b:a-b,lambda a,b:abs(a-b),lambda a,b:a//2]))
    T.append(('abs',  lambda r:(r.randint(-9,-1),0), [lambda a,b:abs(a),lambda a,b:a,lambda a,b:-a,lambda a,b:a*a,lambda a,b:0]))
    T.append(('doub', lambda r:(r.randint(1,9),  0), [lambda a,b:a*2,lambda a,b:a+2,lambda a,b:a*a,lambda a,b:a//2,lambda a,b:a]))
    T.append(('half', lambda r:(r.randint(2,9)*2,0), [lambda a,b:a//2,lambda a,b:a*2,lambda a,b:a-2,lambda a,b:a%2,lambda a,b:a]))
    T.append(('sqr',  lambda r:(r.randint(1,6),  0), [lambda a,b:a*a,lambda a,b:a*2,lambda a,b:a+2,lambda a,b:a**3,lambda a,b:a]))
    T.append(('neg',  lambda r:(r.randint(1,9),  0), [lambda a,b:-a,lambda a,b:a,lambda a,b:abs(a),lambda a,b:a-1,lambda a,b:0]))
    T.append(('inc',  lambda r:(r.randint(1,9),  0), [lambda a,b:a+1,lambda a,b:a-1,lambda a,b:a*2,lambda a,b:a,lambda a,b:a+2]))
    T.append(('dec',  lambda r:(r.randint(1,9),  0), [lambda a,b:a-1,lambda a,b:a+1,lambda a,b:a//2,lambda a,b:a,lambda a,b:-a]))
    T.append(('sum3', lambda r:(r.randint(1,5),  r.randint(1,5)), [lambda a,b:a+b+3,lambda a,b:a+b-3,lambda a,b:a*b+3,lambda a,b:a+b,lambda a,b:(a+b)*3]))
    T.append(('twice',lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:(a+b)*2,lambda a,b:a+b,lambda a,b:a*b,lambda a,b:abs(a-b)*2,lambda a,b:max(a,b)*2]))
    T.append(('diff', lambda r:(r.randint(1,9),  r.randint(1,9)), [lambda a,b:abs(a-b),lambda a,b:a+b,lambda a,b:a-b,lambda a,b:a*b,lambda a,b:max(a,b)]))
    return T

TASKS = mk_tasks()
NC, K = len(TASKS), 5


def make_inst(cls, r):
    name, gen, cands = TASKS[cls]
    args = gen(r)
    true_out = cands[0](*args)                   # 世界真值
    perm = r.permutation(K)
    shuff = [cands[p] for p in perm]
    outs = []
    for c in shuff:
        try: outs.append(c(*args))
        except Exception: outs.append(None)
    correct = int(np.where(perm == 0)[0][0])
    return args, true_out, outs, correct


def feat(args, true_out, cand_out, D):
    """★ 输入: [样例输入, 真值输出, 候选输出] — 不直接给"是否相等" """
    v = np.zeros(D)
    v[0] = args[0] / 10.0
    v[1] = (args[1] if len(args) > 1 else 0) / 10.0
    tv = true_out if isinstance(true_out, (int, float)) else (1.0 if true_out else 0.0)
    cv = cand_out if isinstance(cand_out, (int, float)) else (1.0 if cand_out else 0.0)
    v[2] = tv / 10.0
    v[3] = cv / 10.0
    v[4] = (tv - cv) / 10.0                      # 差值(需要学"接近0=对")
    v[5] = abs(tv - cv) / 10.0
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
        x = 0.5*x + 0.5*np.tanh(x @ Qt)
        d = ph[None, :] - ph[:, None]
        ph = ph + 0.05*(PHW + 0.5*np.sin(d).mean(1))
    return x


def run(mode, steps=900, lr=0.5, quota=12, seed=7):
    rr = np.random.RandomState(seed)
    w = rr.randn(D) * 0.01                 # ★ 单个打分器 (判断"是否一致")
    base = 0.0
    mem = []
    cls_seen = []
    acc_hist = []

    for t in range(steps):
        cls = t % NC
        if cls not in cls_seen: cls_seen.append(cls)
        args, tv, outs, corr = make_inst(cls, rr)

        # 对每个候选打分
        H = np.array([brain(feat(args, tv, o, D)) for o in outs])
        z = H @ w
        if mode in ('quota', 'all'):
            ms = [m for m in mem if m[0] == cls]
            if ms:
                v = np.zeros(K)
                for _, hm, ch in ms:
                    s = float(hm @ H[ch])/(np.linalg.norm(hm)*np.linalg.norm(H[ch])+1e-9)
                    if s > 0.5: v[ch] += s
                z = z + 0.8*v
        p = np.exp(z - z.max()); p /= p.sum()
        pick = int(rr.choice(K, p=p))
        ok = 1.0 if pick == corr else 0.0

        base = 0.99*base + 0.01*ok
        g = np.zeros(K); g[pick] = 1.0
        w = w + lr*(ok - base)*(H[pick] - p @ H)
        w = np.clip(w, -3, 3)

        if mode in ('quota', 'all') and ok > 0.5:
            mem.append((cls, H[corr].copy(), corr))
            if mode == 'quota':
                cnt = {}; keep = []
                for m in reversed(mem):
                    c = m[0]; cnt[c] = cnt.get(c, 0)+1
                    if cnt[c] <= quota: keep.append(m)
                mem = list(reversed(keep))

        # 测历史类别
        if t % 45 == 44 and len(cls_seen) >= 2:
            acc = 0; tot = 0
            for c in cls_seen:
                for _ in range(3):
                    a2, tv2, o2, cr2 = make_inst(c, rr)
                    H2 = np.array([brain(feat(a2, tv2, o, D)) for o in o2])
                    z2 = H2 @ w
                    if mode in ('quota', 'all'):
                        ms = [m for m in mem if m[0] == c]
                        if ms:
                            v = np.zeros(K)
                            for _, hm, ch in ms:
                                s2 = float(hm @ H2[ch])/(np.linalg.norm(hm)*np.linalg.norm(H2[ch])+1e-9)
                                if s2 > 0.5: v[ch] += s2
                            z2 = z2 + 0.8*v
                    acc += (int(np.argmax(z2)) == cr2); tot += 1
            acc_hist.append(acc/tot)
    return np.array(acc_hist), len(mem), len(cls_seen)


print('=' * 74)
print('代码任务闭环 (等价性判断版) %d类 × %d候选, 世界=Python执行' % (NC, K))
print('=' * 74)
print('  %-12s %-36s %-9s %s' % ('模式', '历史类别准确率曲线', '最终', '记忆条数'))
for mode, nm in [('none', 'A 无记忆'), ('quota', '★B 配额记忆'), ('all', 'C 全量记忆')]:
    acc, nmem, ncls = run(mode)
    curve = ' '.join('%.2f' % a for a in acc[:12])
    print('  %-12s %-36s %-9.3f %d' % (nm, curve, acc[-1], nmem))
print()
print('  随机基线 = 0.20')
print('  用时 %.1fs' % (time.time()-t0))
