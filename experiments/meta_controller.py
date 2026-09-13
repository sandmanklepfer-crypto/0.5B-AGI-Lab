#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_controller.py — 全部门控 + 睡眠全局评估
==============================================
核心发现 (刚验证):
  门控能学会在"稳定↔可塑"杆上找最优位置 (a=0.35, 优于两端)
  ★ 但必须用【全局信号】(跨任务评估), 局部信号会滑错方向

设计 (对应工作区 V129 睡眠巩固):
  【白天】局部动作: 各门控按当前任务更新, 用局部信号
  【夜晚】全局评估: 用跨任务表现调整所有门控 ← 这是关键

三个门控 (覆盖今天的配置依赖):
  ① 核步数门控   步数 = round(g1 * 8)
  ② 配额门控     配额 = round(g2 * 40)
  ③ 遗忘门控     保留历史权重 = g3 (0=纯近期, 1=全保留)

对照:
  A 纯工程 (固定最优?)  —— 用人工选的最佳固定配置
  B 纯智能 (全可塑)     —— 所有门控饱和
  ★C 学习门控 + 全局信号

任务: 20 类代码规则, 滚动引入 + 中途漂移
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)

RULES = [
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
NC, D = len(RULES), 32


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
    if steps <= 0: return x.copy()
    x = x.copy()
    for _ in range(steps):
        x = 0.5*x + 0.5*np.tanh(x @ Qt)
        d = ph[None, :] - ph[:, None]
        ph = ph + 0.05*(PHW + 0.5*np.sin(d).mean(1))
    return x


class MetaCtrl:
    """全部门控: 核步数 / 配额 / 遗忘率"""

    def __init__(self):
        self.w = np.array([0.0, 0.0, 0.0])       # 三门的权重
        self.feat = np.zeros(4)                   # 共享输入特征
        self.hist = {"steps": 0.0, "quota": 20.0, "forget": 0.5}
        self.perturbed_w = np.zeros(3)
        self.delta = np.zeros(3)

    def set_feat(self, err_now, err_past, ncls, ntask):
        self.feat = np.array([err_now, err_past, ncls/NC, ntask/NC])

    def apply(self, saturate=None):
        """saturate: None|'eng'(全工程)|'intel'(全智能)"""
        if saturate == 'eng':
            return 0, 4, 1.0
        if saturate == 'intel':
            return 8, 40, 0.0
        s = 1/(1+np.exp(-(self.w[0] + self.feat @ np.array([2.0, -2.0, 1.0, 1.0]))))
        q = 1/(1+np.exp(-(self.w[1] + self.feat @ np.array([1.0, 0.5, 2.0, 0.0]))))
        f = 1/(1+np.exp(-(self.w[2] + self.feat @ np.array([-1.0, 1.0, 0.0, 1.0]))))
        return int(round(s*8)), int(round(q*40)), float(f)

    def learn(self, grads, lr=0.02):
        self.w = np.clip(self.w - lr*grads, -5, 5)

    def perturb(self, sigma=0.3):
        """★ 爬山法: 记录一个随机扰动方向"""
        self.delta = np.random.randn(3) * sigma
        return self.w + self.delta

    def accept(self, improved, lr=0.15):
        """若扰动后有改善 → 沿该方向走"""
        if improved:
            self.w = np.clip(self.w + lr * self.delta, -5, 5)


def run(mode, rounds=8, batch=25, lam=1e-2, drift_every=24):
    W = np.zeros(D)
    mem = {}
    mc = MetaCtrl()
    offsets = np.zeros(NC)
    seen = []
    perf = []
    gate_log = []

    for t in range(NC*rounds):
        # 世界漂移
        if t > 0 and t % drift_every == 0:
            c = rng.randint(NC); offsets[c] += rng.choice([-2.0, 2.0])

        cls = t % NC
        if cls not in seen: seen.append(cls)

        # 门控决定配置
        if mode == 'meta' and t % 40 >= 20:
            # ★ 试探期: 用扰动后的参数 (爬山)
            saved = mc.w.copy()
            mc.w = mc.perturbed_w
        st, q, f = mc.apply(mode if mode in ('eng','intel') else None)
        if mode == 'meta':
            gate_log.append((st, q, f))

        Xn = []; Yn = []
        for _ in range(batch):
            a = RULES[cls][1](rng)
            Xn.append(feat(cls, a)); Yn.append(RULES[cls][2](*a, offsets[cls]))
        Xn = np.array(Xn); Yn = np.array(Yn, float)
        Hn = np.array([brain(x, st) for x in Xn])

        # ★ 遗忘门控: f=1 全保留历史, f=0 只用新数据
        if f > 0.05 and len(mem) > 0:
            Xa = [Hn]; Ya = [Yn]
            for c, lst in mem.items():
                if lst:
                    Xa.append(np.array([h for h, _ in lst])); Ya.append(np.array([y for _, y in lst]))
            Xall = np.vstack(Xa); Yall = np.concatenate(Ya)
            # 历史样本权重 = f
            wts = np.concatenate([np.ones(len(Hn)), np.full(len(Yall)-len(Hn), f)])
            Xw = Xall * wts[:, None]
            W = np.linalg.solve(Xw.T @ Xall + lam*np.eye(D), Xw.T @ Yall)
        else:
            W = np.linalg.solve(Hn.T @ Hn + lam*np.eye(D), Hn.T @ Yn)

        # 写入记忆 (按配额)
        lst = mem.setdefault(cls, [])
        for i in range(batch):
            lst.append((Hn[i].copy(), Yn[i]))
        if q > 0 and len(lst) > q:
            mem[cls] = lst[-q:]

        # ★ 全局评估 (每 30 步 = "睡一觉")
        if t % 15 == 14 and len(seen) >= 2:
            g = 0; tt = 0
            for c in seen:
                for _ in range(3):
                    a = RULES[c][1](rng)
                    h = brain(feat(c, a), st)
                    pr = h @ W
                    tr = RULES[c][2](*a, offsets[c])
                    g += (abs(pr-tr) <= 0.15*(abs(tr)+1.0)); tt += 1
            acc = g/tt
            perf.append(acc)
            # ★ 每 60 步一个"试探周期": 前30步试扰动, 后30步用原参数
            if mode == 'meta' and t % 40 == 39:
                # 比较: 本轮(扰动后) vs 上轮(原参数)
                if len(perf) >= 2:
                    improved = perf[-1] > perf[-2]
                    mc.accept(improved)
                mc.perturbed_w = mc.perturb()
    return np.array(perf), gate_log, mem


print('=' * 78)
print('全部门控 + 睡眠全局评估  (20类规则 + 中途漂移)')
print('=' * 78)
print('  %-16s %-42s %-8s' % ('模式', '准确率曲线', '最终'))
res = {}
for mode, nm in [('eng', 'A 纯工程(固定)'), ('intel', 'B 纯智能(全可塑)'), ('meta', '★C 学习门控')]:
    perf, gl, mem = run(mode)
    res[nm] = perf[-1] if len(perf) else 0
    print('  %-16s %-42s %-8.3f' % (nm, ' '.join('%.2f' % a for a in perf[:13]), perf[-1]))

print()
perf, gl, mem = run('meta')
if gl:
    a = np.array(gl)
    print('  门控轨迹 (每50轮均值):')
    print('    核步数: %s' % ' '.join('%.1f' % np.mean(a[i*50:(i+1)*50, 0]) for i in range(min(6, len(a)//50))))
    print('    配额:   %s' % ' '.join('%.1f' % np.mean(a[i*50:(i+1)*50, 1]) for i in range(min(6, len(a)//50))))
    print('    遗忘:   %s' % ' '.join('%.2f' % np.mean(a[i*50:(i+1)*50, 2]) for i in range(min(6, len(a)//50))))
print()
print('  随机基线 = 0.05 (连续回归)')
print('  用时 %.1fs' % (time.time()-t0))
