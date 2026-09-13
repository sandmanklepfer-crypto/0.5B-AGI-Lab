#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
system_v1.py — 第一个完整系统 (最小闭环)
==========================================
组装 4 个零件, 验证"能不能合起来工作":

  ① 正交核 A    → 任务表示演化 (保距, 语义不损)
  ② 相位通道    → 时间 (Kuramoto, 永不重复)
  ③ 读出层 W    → 预测 (可学, 不碰核)
  ④ 配额记忆 M  → 持续学习 (每类固定条数, 防遗忘)

数据流:
  任务 → 特征x → 核演化(带相位) → h → 读出层 → 预测 → 世界判对错
                                    ↓
                              写入配额记忆
                                    ↓
                          下次同类任务 → 记忆辅助

任务: 20 类代码规则 (世界=Python执行, 客观对错)
世界: 滚动引入新类 → 测灾难性遗忘

★ 这是第一次把多个零件联合运行
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(7)

# ==================== ① 世界: 20 类代码规则 ====================
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
NC = len(RULES)
D = 32


def gen_args(cls, r):
    return RULES[cls][1](r)


def world_eval(cls, args, val):
    """② 世界: 执行真规则, 返回 (预测值, 是否正确)"""
    true = RULES[cls][2](*args)
    ok = abs(val - true) <= 0.15 * (abs(true) + 1.0)
    return true, ok


def feat(cls, args):
    """任务特征 (不含类别可学信息泄漏: 独热 + 参数)"""
    v = np.zeros(D)
    v[cls] = 1.0
    v[20] = args[0] / 10.0
    v[21] = (args[1] if len(args) > 1 else 0) / 10.0
    v[22] = 1.0 if len(args) > 1 else 0.0
    v[23] = 1.0
    return v


# ==================== ③ 核 + 相位 ====================
rng2 = np.random.RandomState(1)
Q, _ = np.linalg.qr(rng2.randn(D, D))
A = Q * 1.15
Qt = np.ascontiguousarray(A.T)
NPH = 6
PHW = np.array([1.0, 1.618, 2.414, 1.732, 2.236, 1.414])
phase = rng2.rand(NPH) * 2 * np.pi
phase_advance = []                     # 记录相位推进 (验证永生)


def brain(x, steps=3):
    """核演化 + 相位推进 (相位独立, 不驱动幅度)"""
    global phase
    x = x.copy()
    for _ in range(steps):
        x = 0.5 * x + 0.5 * np.tanh(x @ Qt)
        d = phase[None, :] - phase[:, None]
        phase = phase + 0.05 * (PHW + 0.5 * np.sin(d).mean(1))
    return x


# ==================== ④ 配额记忆 ====================
class QuotaMemory:
    """每类固定条数, 均衡保留"""

    def __init__(self, quota=12):
        self.q = quota
        self.store = {}                 # cls -> [(h, y), ...]

    def add(self, cls, h, y):
        lst = self.store.setdefault(cls, [])
        lst.append((h.copy(), y))
        if len(lst) > self.q:
            self.store[cls] = lst[-self.q:]

    def assist(self, cls, h, strength=0.5):
        """记忆辅助: 同类历史状态的加权平均输出"""
        lst = self.store.get(cls)
        if not lst:
            return 0.0, 0.0
        hn = np.linalg.norm(h)
        num = 0.0; den = 0.0
        for hm, ym in lst:
            s = float(hm @ h) / (np.linalg.norm(hm) * hn + 1e-9)
            if s > 0.3:
                num += s * ym; den += s
        if den < 1e-9:
            return 0.0, 0.0
        return strength * num / den, den

    def size(self):
        return sum(len(v) for v in self.store.values())


# ==================== 主循环 ====================
def run(use_mem=True, quota=12, rounds=3, batch=40, lam=1e-2, lr=0.0):
    W = np.zeros(D)                     # 读出层 (线性)
    mem = QuotaMemory(quota)
    seen = []
    acc_hist, mem_hist = [], []

    for t in range(NC * rounds):
        cls = t % NC
        if cls not in seen:
            seen.append(cls)

        # ── 取一批当前类的数据
        Xn = []; Yn = []
        for _ in range(batch):
            a = gen_args(cls, rng)
            Xn.append(feat(cls, a))
            Yn.append(RULES[cls][2](*a))
        Xn = np.array(Xn); Yn = np.array(Yn, float)

        # ── 核演化 (带相位)
        Hn = np.array([brain(x) for x in Xn])

        # ── 读出层更新: 用【新增数据 + 记忆中的旧数据】联合拟合
        #    ★ 修正: 记忆进入训练集 (而不是污染标签)
        if use_mem and mem.size() > 0:
            Xa = [Hn]; Ya = [Yn]
            for c in seen:
                lst = mem.store.get(c)
                if lst:
                    Xa.append(np.array([hm for hm, _ in lst]))
                    Ya.append(np.array([ym for _, ym in lst]))
            Xall = np.vstack(Xa); Yall = np.concatenate(Ya)
        else:
            Xall, Yall = Hn, Yn

        W = np.linalg.solve(Xall.T @ Xall + lam * np.eye(D), Xall.T @ Yall)

        # ── 写入配额记忆
        if use_mem:
            for i in range(batch):
                mem.add(cls, Hn[i], Yn[i])

        # ── 测: 所有历史类别
        if t % 6 == 5 and len(seen) >= 2:
            g = 0; tt = 0
            for c in seen:
                for _ in range(4):
                    a = gen_args(c, rng)
                    h = brain(feat(c, a))
                    pred = h @ W
                    if use_mem:
                        adj, _ = mem.assist(c, h)
                        pred = pred + adj
                    _, ok = world_eval(c, a, pred)
                    g += ok; tt += 1
            acc_hist.append(g / tt)
            mem_hist.append(mem.size())

    return np.array(acc_hist), mem_hist, seen


# ==================== 运行 ====================
print('=' * 76)
print('系统 v1 — 最小闭环 (正交核 + 相位 + 读出层 + 配额记忆)')
print('=' * 76)
print('  核: D=%d 正交 (保距 %.2e)' % (D, np.abs(A @ A.T / 1.15**2 - np.eye(D)).mean()))
print('  相位: %d 振荡器 (无理频率)' % NPH)
print('  任务: %d 类代码规则, 滚动引入' % NC)
print()

print('  %-16s %-42s %-9s %s' % ('配置', '历史类别准确率曲线', '最终', '记忆'))
for use_mem, nm in [(False, 'A 无记忆'), (True, '★B 配额记忆')]:
    acc, mh, seen = run(use_mem=use_mem)
    curve = ' '.join('%.2f' % a for a in acc[:13])
    print('  %-16s %-42s %-9.3f %d' % (nm, curve, acc[-1], mh[-1] if mh else 0))

# ── 相位永生验证
ph_before = phase.copy()
for _ in range(1000):
    brain(np.zeros(D))
adv = float(np.abs(phase - ph_before).mean())
print()
print('  相位推进 (1000步): %.2f rad  → %s' % (adv, '✅永不停止' if adv > 1 else '❌'))
print('  用时 %.1fs' % (time.time() - t0))
