#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dispatcher.py — 调度核 (元控制器)
===================================
今天测出: 最优配置依赖任务
  线性型任务 → 核1步最好
  非线性型   → 直通最好

调度核的职责: 看当前任务的状态 → 选配置
  输入信号: 各类的"误差流" (不看标签, 只看预测误差)
  输出: 核步数 (0=直通 / 1 / 3 / 8)

三种策略对照:
  A 固定直通      永远 steps=0
  B 固定核1步     永远 steps=1
  ★C 调度核      按误差信号动态选

关键: 调度核只有几个参数 = "小"
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)

RULES = [
    ('add',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:a+b),
    ('sub',  lambda r:(r.randint(3,9), r.randint(1,3)), lambda a,b:a-b),
    ('mul',  lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b:a*b),
    ('max',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:max(a,b)),
    ('min',  lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:min(a,b)),
    ('abs',  lambda r:(r.randint(-9,-1),0),             lambda a,b:abs(a)),
    ('doub', lambda r:(r.randint(1,9), 0),              lambda a,b:a*2),
    ('half', lambda r:(r.randint(2,9)*2,0),             lambda a,b:a//2),
    ('sqr',  lambda r:(r.randint(1,6), 0),              lambda a,b:a*a),
    ('neg',  lambda r:(r.randint(1,9), 0),              lambda a,b:-a),
    ('inc',  lambda r:(r.randint(1,9), 0),              lambda a,b:a+1),
    ('dec',  lambda r:(r.randint(1,9), 0),              lambda a,b:a-1),
    ('sum3', lambda r:(r.randint(1,5), r.randint(1,5)), lambda a,b:a+b+3),
    ('twice',lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:(a+b)*2),
    ('diff', lambda r:(r.randint(1,9), r.randint(1,9)), lambda a,b:abs(a-b)),
    ('fmul', lambda r:(r.randint(1,4), r.randint(1,4)), lambda a,b:a*b+1),
    ('fadd', lambda r:(r.randint(1,6), r.randint(1,6)), lambda a,b:a+b-1),
    ('dbl',  lambda r:(r.randint(1,9), 0),              lambda a,b:a-2),
    ('tri',  lambda r:(r.randint(1,9), 0),              lambda a,b:a*3),
    ('quad', lambda r:(r.randint(1,9), 0),              lambda a,b:a*4),
]
NC, D = len(RULES), 32


def gen_args(cls, r): return RULES[cls][1](r)


def feat(cls, args):
    v = np.zeros(D); v[cls] = 1.0
    v[20] = args[0] / 10.0
    v[21] = (args[1] if len(args) > 1 else 0) / 10.0
    v[22] = 1.0 if len(args) > 1 else 0.0
    v[23] = 1.0
    return v


rng2 = np.random.RandomState(1)
Q, _ = np.linalg.qr(rng2.randn(D, D))
A = Q * 1.15
Qt = np.ascontiguousarray(A.T)
NPH = 6
PHW = np.array([1.0, 1.618, 2.414, 1.732, 2.236, 1.414])
ph = rng2.rand(NPH) * 2 * np.pi


def brain(x, steps):
    global ph
    if steps <= 0:
        return x.copy()
    x = x.copy()
    for _ in range(steps):
        x = 0.5 * x + 0.5 * np.tanh(x @ Qt)
        d = ph[None, :] - ph[:, None]
        ph = ph + 0.05 * (PHW + 0.5 * np.sin(d).mean(1))
    return x


class QuotaMem:
    def __init__(self, q=12): self.q = q; self.s = {}
    def add(self, c, h, y):
        l = self.s.setdefault(c, []); l.append((h.copy(), y))
        if len(l) > self.q: self.s[c] = l[-self.q:]
    def size(self): return sum(len(v) for v in self.s.values())


# ==================== ★ 调度核 ====================
class Dispatcher:
    """★ 跟注 (follow-the-leader): 每步实测各配置, 选即时误差最小的

    区别于 dispatcher v1 的"价值估计":
      v1: 用长期估计 (粗糙, 区分度仅1%)
      本版: 每步实测 (即时误差, 区分度大)

    实现: 滑动窗口记录各配置的实测误差, 选窗口均值最小的
    """

    def __init__(self, candidates=(0, 1, 3), win=8):
        self.cands = candidates
        self.win = win
        self.hist = {c: [] for c in candidates}
        self.cur = 0

    def observe(self, steps_used, err):
        h = self.hist[steps_used]
        h.append(err)
        if len(h) > self.win:
            h.pop(0)

    def choose(self, eps=0.05):
        """选窗口内平均误差最小的 (无历史则轮询)"""
        scored = []
        for c in self.cands:
            if len(self.hist[c]) >= 2:
                scored.append((np.mean(self.hist[c]), c))
        if not scored:
            self.cur = self.cands[len(self.hist[self.cands[0]]) % len(self.cands)]
        elif np.random.rand() < eps:
            self.cur = int(np.random.choice(self.cands))
        else:
            self.cur = min(scored)[1]
        return self.cur


def run(policy, rounds=4, batch=30, lam=1e-2, quota=12):
    """policy: 'fixed0' | 'fixed1' | 'dispatch'"""
    W = np.zeros(D)
    mem = QuotaMem(quota)
    disp = Dispatcher((0, 1, 3))
    seen = []
    accs = []
    used_steps = []

    for t in range(NC * rounds):
        cls = t % NC
        if cls not in seen: seen.append(cls)

        Xn = []; Yn = []
        for _ in range(batch):
            a = gen_args(cls, rng)
            Xn.append(feat(cls, a)); Yn.append(RULES[cls][2](*a))
        Xn = np.array(Xn); Yn = np.array(Yn, float)

        # ★ 选步数
        if policy == 'fixed0': st = 0
        elif policy == 'fixed1': st = 1
        else: st = disp.choose()
        used_steps.append(st)

        # ★ 跟注: 同一步数据实测所有候选的即时误差
        if policy == 'dispatch':
            for c in disp.cands:
                Hc = np.array([brain(x, c) for x in Xn])
                erc = float(np.mean(np.abs(Hc @ W - Yn)) / (np.mean(np.abs(Yn)) + 1e-9))
                disp.observe(c, erc)

        Hn = np.array([brain(x, st) for x in Xn])

        # 训练集 = 新数据 + 记忆
        Xa = [Hn]; Ya = [Yn]
        for c in seen:
            l = mem.s.get(c)
            if l: Xa.append(np.array([h for h, _ in l])); Ya.append(np.array([y for _, y in l]))
        Xall = np.vstack(Xa); Yall = np.concatenate(Ya)
        W = np.linalg.solve(Xall.T @ Xall + lam * np.eye(D), Xall.T @ Yall)

        # 测误差 (供调度核学习)
        err = float(np.mean(np.abs(Hn @ W - Yn)) / (np.mean(np.abs(Yn)) + 1e-9))
        if policy == 'dispatch':
            disp.observe(st, err)

        for i in range(batch): mem.add(cls, Hn[i], Yn[i])

        # 评估
        if t % 6 == 5 and len(seen) >= 2:
            g = 0; tt = 0
            for c in seen:
                st2 = disp.cur if policy == 'dispatch' else (0 if policy == 'fixed0' else 1)
                for _ in range(4):
                    a = gen_args(c, rng)
                    h = brain(feat(c, a), st2)
                    pr = h @ W
                    tr = RULES[c][2](*a)
                    g += (abs(pr - tr) <= 0.15 * (abs(tr) + 1.0)); tt += 1
            accs.append(g / tt)
    return np.array(accs), used_steps, {c: (round(np.mean(disp.hist[c]),4) if disp.hist[c] else None) for c in disp.cands}


print('=' * 76)
print('调度核 (元控制器) — 看误差信号自动选核步数')
print('=' * 76)
print('  %-14s %-40s %-8s %s' % ('策略', '历史类别准确率曲线', '最终', '平均步数'))
res = {}
for pol, nm in [('fixed0', 'A 固定直通(0)'), ('fixed1', 'B 固定核1步'),
                ('dispatch', '★C 调度核')]:
    acc, us, val = run(pol)
    res[pol] = acc[-1]
    print('  %-14s %-40s %-8.3f %.2f' % (nm, ' '.join('%.2f' % a for a in acc[:13]),
                                         acc[-1], np.mean(us)))
print()
_, _, val = run('dispatch')
print('  调度核学到的价值估计: %s' % {k: round(v, 3) for k, v in val.items()})
print()
best = max(res, key=res.get)
print('  最优: %s (%.3f)' % (best, res[best]))
print('  调度核 vs 最优固定: %+.1f%%' % (100 * (res['dispatch'] - max(res['fixed0'], res['fixed1'])) / max(res['fixed0'], res['fixed1'], 1e-9)))
print()
print('  用时 %.1fs' % (time.time() - t0))
