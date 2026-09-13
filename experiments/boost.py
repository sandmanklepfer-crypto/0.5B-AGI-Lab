#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
boost.py — 推理泛化核心 能否极大增强整体模型?
================================================
四张王牌做成一个"加速核心", 看它对基础模型的整体增强:

  基础模型 (模拟 0.5B 的弱能力)
    · 小 MLP, 从问题特征直接预测答案
    · 能力有限 (实测准确率会显示)

  加速核心 (四张王牌)
    ① 约束 → 可执行验证器 (判对错)
    ② 推理 → 串行搜索 (候选不够就自己找)
    ③ 超启发 → 多策略 (枚举/代数/随机/分解)
    ④ 泛化 → 域特征 → 选策略

  四组对照:
    A 裸模型 (top1)
    B 模型 + 验证器      (验证失败就弃权)
    C 模型 + 验证 + 搜索  (失败就搜)
    D 完整核心           (再按域选策略)

判据: 核心能否把整体从弱拉到强, 且需要多少代价
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

NQ = 120          # 每域题数
FEAT = 12         # 问题特征维度

# ==================== 三个域 (真实约束问题) ====================
def dom_lin(n, r):
    """域1 线性: a*x + b = c"""
    qs = []
    for _ in range(n):
        a = r.randint(2, 60); x0 = r.randint(-300, 301)
        b = r.randint(-500, 501)
        qs.append(dict(k='lin', a=a, b=b, c=a*x0+b, x=x0))
    return qs


def dom_quad(n, r):
    """域2 二次: x² + p*x + q = 0 (有整数根)"""
    qs = []
    for _ in range(n):
        x0 = r.randint(-80, 81)
        p = r.randint(-200, 201)
        qs.append(dict(k='q', p=p, q=-(x0*x0 + p*x0), x=x0))
    return qs


def dom_sys(n, r):
    """域3 二元一次方程组: x+y=s, x-y=d"""
    qs = []
    for _ in range(n):
        x0 = r.randint(-150, 151); y0 = r.randint(-150, 151)
        qs.append(dict(k='sys', s=x0+y0, d=x0-y0, x=x0))
    return qs


DOMS = [('线性', dom_lin), ('二次', dom_quad), ('方程组', dom_sys)]


# ==================== ★ 约束: 可执行验证器 ====================
def verify(it, x):
    k = it['k']
    if k == 'lin':  return it['a']*x + it['b'] == it['c']
    if k == 'q':    return x*x + it['p']*x + it['q'] == 0
    if k == 'sys':  return (x + (it['s']-x) == it['s']) and (x - (it['s']-x) == it['d'])
    return False


# ==================== 特征编码 ====================
def featurize(it):
    k = it['k']
    v = np.zeros(FEAT)
    if k == 'lin':
        v[0] = 1; v[1] = it['a']/60.0; v[2] = it['b']/500.0; v[3] = it['c']/3000.0
    elif k == 'q':
        v[4] = 1; v[5] = it['p']/200.0; v[6] = it['q']/30000.0
    else:
        v[7] = 1; v[8] = it['s']/300.0; v[9] = it['d']/300.0
    v[10] = np.tanh(it.get('a', it.get('p', 0))/50.0)
    v[11] = 1.0
    return v


# ==================== 基础模型 (小 MLP, 预测答案的离散桶) ====================
NB = 61                                  # 答案分桶: [-300,300] → 61 桶
def to_bucket(x): return int(np.clip((x + 300) // 10, 0, NB-1))
def from_bucket(b): return int(b*10 - 300)


class BaseModel:
    """模拟 0.5B: 小容量, 直接预测答案"""
    def __init__(self, H=24, seed=0):
        r = np.random.RandomState(seed)
        self.W1 = r.randn(H, FEAT)/np.sqrt(FEAT); self.b1 = np.zeros((1, H))
        self.W2 = r.randn(NB, H)/np.sqrt(H); self.b2 = np.zeros((1, NB))
        self.M = [np.zeros_like(p) for p in (self.W1, self.b1, self.W2, self.b2)]
        self.V = [np.zeros_like(p) for p in (self.W1, self.b1, self.W2, self.b2)]
        self.t = 0

    def logits(self, X):
        A = np.tanh(X @ self.W1.T + self.b1)
        return A @ self.W2.T + self.b2, A

    def fit(self, X, Y, iters=250, lr=0.15):
        Yh = np.eye(NB)[Y]
        for it in range(iters):
            Lg, A = self.logits(X)
            e = np.exp(Lg - Lg.max(1, keepdims=True)); P = e/e.sum(1, keepdims=True)
            dY = (P - Yh)/len(X)
            gW2 = dY.T @ A; gb2 = dY.sum(0, keepdims=True)
            dZ = (dY @ self.W2)*(1 - A**2)
            gW1 = dZ.T @ X; gb1 = dZ.sum(0, keepdims=True)
            self.t += 1
            for i, g in enumerate([gW1, gb1, gW2, gb2]):
                self.M[i] = 0.9*self.M[i] + 0.1*g
                self.V[i] = 0.999*self.V[i] + 0.001*g**2
                pp = self.__dict__
                key = ['W1', 'b1', 'W2', 'b2'][i]
                pp[key] = pp[key] - lr*(self.M[i]/(1-0.9**self.t))/(np.sqrt(self.V[i]/(1-0.999**self.t))+1e-8)

    def topk(self, x, k=5):
        lg, _ = self.logits(x.reshape(1, -1))
        return list(np.argsort(-lg[0])[:k])


# ==================== ★ 推理: 串行搜索 (核心的搜索能力) ====================
def search(it, budget=2000, strat='auto'):
    """①②③: 根据域选策略, 串行探索 + 每步验证"""
    if strat == 'enum_small':
        for x in range(-300, 301):
            budget -= 1
            if budget <= 0: break
            if verify(it, x): return x
    elif strat == 'enum_wide':
        for x in range(-3000, 3001):
            budget -= 1
            if budget <= 0: break
            if verify(it, x): return x
    elif strat == 'algebra':
        if it['k'] == 'lin':
            num = it['c'] - it['b']
            if num % it['a'] == 0:
                x = num // it['a']
                if verify(it, x): return x
        if it['k'] == 'q':
            disc = it['p']**2 - 4*it['q']
            if disc >= 0:
                rt = int(round(disc**0.5))
                if rt*rt == disc:
                    for x in ((-it['p']+rt)//2, (-it['p']-rt)//2):
                        if verify(it, x): return x
        if it['k'] == 'sys':
            s, d = it['s'], it['d']
            if (s+d) % 2 == 0:
                x = (s+d)//2
                if verify(it, x): return x
    elif strat == 'random':
        rr = np.random.RandomState(abs(hash(str(it))) % 2**31)
        for _ in range(min(budget, 500)):
            x = int(rr.randint(-3000, 3001))
            if verify(it, x): return x
    return None


# ==================== ★ 泛化: 域特征 → 选策略 ====================
def domain_features(qs):
    """从数据测: 3个特征 (不需要设计)"""
    # ① 小范围枚举命中率
    ok1 = np.mean([1 if search(q, 300, 'enum_small') is not None else 0 for q in qs[:20]])
    # ② 代数解命中率
    ok2 = np.mean([1 if search(q, 500, 'algebra') is not None else 0 for q in qs[:20]])
    # ③ 大范围枚举命中率
    ok3 = np.mean([1 if search(q, 3000, 'enum_wide') is not None else 0 for q in qs[:20]])
    return np.array([ok1, ok2, ok3])


STRAT_NAMES = ['enum_small', 'algebra', 'enum_wide', 'random']


def pick_strategy(feat, W):
    sc = feat @ W
    return STRAT_NAMES[int(np.argmax(sc))]


# ==================== 训练/测试划分 ====================
r = np.random.RandomState(1)
data = {}
for nm, gen in DOMS:
    data[nm] = dict(tr=gen(NQ, r), te=gen(60, r))

# 训练基础模型 (所有域合并)
Xtr = np.array([featurize(q) for nm, _ in DOMS for q in data[nm]['tr']])
Ytr = np.array([to_bucket(q['x']) for nm, _ in DOMS for q in data[nm]['tr']])
model = BaseModel(H=24)
model.fit(Xtr, Ytr, iters=250)

# 训练策略选择器 (跑每个域, 记录每策略成功率)
Ymat = np.zeros((len(DOMS), len(STRAT_NAMES)))
Feat = np.zeros((len(DOMS), 3))
for di, (nm, _) in enumerate(DOMS):
    Feat[di] = domain_features(data[nm]['tr'])
    for si, s in enumerate(STRAT_NAMES):
        ok = np.mean([1 if search(q, 2000, s) is not None else 0 for q in data[nm]['tr'][:30]])
        Ymat[di, si] = ok
W = np.zeros((3, len(STRAT_NAMES)))
for si in range(len(STRAT_NAMES)):
    W[:, si] = np.linalg.lstsq(Feat, Ymat[:, si], rcond=None)[0]

print('=' * 88)
print('推理泛化核心 对基础模型的整体增强')
print('=' * 88)
print()
print('  基础模型: 小MLP (H=24, %d参数), 直接预测答案桶' % (24*FEAT + 24 + NB*24 + NB))
print('  加速核心: ①可执行验证 ②串行搜索 ③4策略 ④域特征选策略')
print()
print('  域特征矩阵 (从数据测):')
for di, (nm, _) in enumerate(DOMS):
    print('    %-8s [小枚举%.2f 代数%.2f 大枚举%.2f]  各策略成功率 %s'
          % (nm, Feat[di, 0], Feat[di, 1], Feat[di, 2],
             ' '.join('%.2f' % v for v in Ymat[di])))

# ==================== 四组对比 ====================
print()
print('=' * 88)
print('四组对照 (测试集, 每域 60 题)')
print('=' * 88)
print()
print('  %-8s %-14s %-14s %-14s %-14s' % ('域', 'A 裸模型', 'B +验证', 'C +搜索', 'D 完整核心'))

tot = {k: [0, 0] for k in ['A', 'B', 'C', 'D']}
for nm, _ in DOMS:
    res = {k: 0 for k in 'ABCD'}
    for q in data[nm]['te']:
        fv = featurize(q)
        # A: 裸模型 top1
        top = model.topk(fv, 5)
        a1 = from_bucket(top[0])
        res['A'] += verify(q, a1)
        # B: 模型 + 验证 (验证失败就弃权)
        res['B'] += any(verify(q, from_bucket(b)) for b in top[:1])
        # C: 模型 top5 + 验证, 不行再搜索
        hit = any(verify(q, from_bucket(b)) for b in top)
        if not hit:
            x = search(q, 2000, 'algebra')
            hit = (x is not None)
        if not hit:
            x = search(q, 2000, 'enum_small')
            hit = (x is not None)
        res['C'] += hit
        # D: 完整核心 (按域选策略)
        hit = any(verify(q, from_bucket(b)) for b in top)
        if not hit:
            s = pick_strategy(fv[:3] * 0 + domain_features([q]), W)
            x = search(q, 2000, s)
            hit = (x is not None)
        if not hit:
            for s in STRAT_NAMES:
                x = search(q, 2000, s)
                if x is not None: hit = True; break
        res['D'] += hit
    n = len(data[nm]['te'])
    print('  %-8s %-14.3f %-14.3f %-14.3f %-14.3f' % (
        nm, res['A']/n, res['B']/n, res['C']/n, res['D']/n))
    for k in 'ABCD': tot[k][0] += res[k]; tot[k][1] += n

print()
print('=' * 88)
print('整体结论')
print('=' * 88)
print('  %-16s %-14s %-14s' % ('配置', '总准确率', '相对裸模型'))
base = tot['A'][0]/tot['A'][1]
for k, nm in [('A', 'A 裸模型'), ('B', 'B +验证'), ('C', 'C +搜索'), ('D', '★D 完整核心')]:
    a = tot[k][0]/tot[k][1]
    print('  %-16s %-14.3f %s' % (nm, a,
          '—' if k == 'A' else '%+.1f 倍' % (a/base) if base > 0 else '∞'))
print()
print('  用时 %.2fs' % (time.time() - t0))
