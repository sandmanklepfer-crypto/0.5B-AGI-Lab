#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfmodel.py — 边界感 → 自我模型 (自我认识的可测形式)
======================================================
上一轮: 验证器能判定「无解」= 有边界
本轮:   边界累积起来 → 能否变成"我知道我擅长什么"= 自我模型

设计:
  20 类问题, 其中 10 类系统【真能做】(有解且能求), 10 类【真不能】(结构性无解)
  系统逐步遇到各类问题, 累积每类的历史成功率
  
  三种:
    A 无自我模型   每次都直接做 (不知道自己做不做得到)
    B 有自我模型   先预测"这类我能做吗" → 按预测决定做/跳过/上报
    C 完美自我模型 上帝视角 (上界)

关键指标:
  ① 校准度: "我预测我能做" 中的实际成功率 (应接近 1)
  ② 资源浪费: 在"做不了"的问题上花的尝试次数
  ③ 自主求助: 能否知道"这个得叫外援"
"""
import numpy as np, time

t0 = time.time()
rng = np.random.RandomState(0)

NCLS = 20
# ★ 10 类真能做 (线性可解), 10 类真不能 (约束矛盾)
SOLVABLE = list(range(10))
UNSOLVABLE = list(range(10, 20))


def make_instance(cls, r):
    """每类问题: 返回 (参数, 是否真有解)"""
    if cls in SOLVABLE:
        a = cls + 2
        x0 = r.randint(-8, 9)
        b = r.randint(-9, 10)
        c = a*x0 + b
        return (a, b, c), True
    else:
        # ★ 结构性无解: a*x + b = c 其中 (c-b) 不被 a 整除
        a = cls - 10 + 2
        b = r.randint(-9, 10)
        c = a*r.randint(-5, 6) + b + r.choice([1, -1]) * (a//2 if a > 2 else 1)
        return (a, b, c), False


def try_solve(args, budget=40):
    """实际尝试求解, 返回 (成功?, 尝试次数)"""
    a, b, c = args
    t = 0
    for x in range(-30, 31):
        t += 1
        if t > budget: break
        if a*x + b == c:
            return True, t
    return False, t


# ==================== 系统 ====================
class System:
    def __init__(self, mode):
        self.mode = mode
        self.stat = {}            # cls -> [成功数, 总次数]
        self.asked = set()        # 已知做不了的类

    def predict(self, cls, thresh=0.5):
        """★ 自我预测: 这类我做得了吗"""
        if cls not in self.stat or self.stat[cls][1] < 2:
            return None            # 数据不足 → 不确定
        sr = self.stat[cls][0] / self.stat[cls][1]
        return sr > thresh

    def act(self, cls, args):
        """返回 (是否尝试, 是否成功, 是否上报求助)"""
        if self.mode == 'none':
            ok, t = try_solve(args)
            self._update(cls, ok)
            return True, ok, False
        elif self.mode == 'self':
            pred = self.predict(cls)
            if pred is False:
                # ★ 知道自己不行 → 跳过, 上报
                return False, None, True
            ok, t = try_solve(args)
            self._update(cls, ok)
            return True, ok, False
        else:   # perfect
            really = cls in SOLVABLE
            if not really:
                return False, None, True
            ok, t = try_solve(args)
            self._update(cls, ok)
            return True, ok, False

    def _update(self, cls, ok):
        s = self.stat.setdefault(cls, [0, 0])
        s[1] += 1
        if ok: s[0] += 1


# ==================== 运行 ====================
def run(mode, rounds=25, per_round=20, seed=0):
    r = np.random.RandomState(seed)
    sys_ = System(mode)
    tried = 0; wasted = 0; wasted_tries = 0; escalated = 0
    calib_num = 0; calib_den = 0
    for rd in range(rounds):
        for _ in range(per_round):
            cls = r.randint(NCLS)
            args, really = make_instance(cls, r)
            pred = sys_.predict(cls) if mode == 'self' else None
            did, ok, esc = sys_.act(cls, args)
            if did:
                tried += 1
                if not really:
                    wasted += 1
                    _, tt = try_solve(args)
                    wasted_tries += tt
                if pred is True:
                    calib_den += 1
                    if ok: calib_num += 1
            if esc:
                escalated += 1
    return dict(tried=tried, wasted=wasted, wasted_tries=wasted_tries,
                escalated=escalated,
                calib=(calib_num/max(calib_den, 1)), calib_n=calib_den)


print('=' * 78)
print('边界感 → 自我模型')
print('=' * 78)
print('  %d 类问题: 10 类真能做, 10 类结构性无解' % NCLS)
print('  共 %d 轮 × %d 次 = %d 个问题 (每类约 %d 个)' % (25, 20, 500, 25))
print()
print('  %-22s %-11s %-11s %-13s %-9s %s' % ('模型', '询问次数', '无解上花费', '浪费尝试', '正确上报', '校准度'))
print('  ' + '-' * 74)
res = {}
for mode, nm in [('none', 'A 无自我模型'),
                 ('self', '★B 有自我模型'),
                 ('perfect', 'C 完美(上界)')]:
    r = run(mode)
    res[nm] = r
    print('  %-22s %-11d %-11d %-13d %-9d %.3f (n=%d)' % (
        nm, r['tried'], r['wasted'], r['wasted_tries'], r['escalated'],
        r['calib'], r['calib_n']))

print()
print('=' * 78)
print('核心结论')
print('=' * 78)
a = res['A 无自我模型']; b = res['★B 有自我模型']; c = res['C 完美(上界)']
print('  无解上的浪费尝试: %d → %d  (%.0f%% 下降)' % (a['wasted_tries'], b['wasted_tries'],
      100*(a['wasted_tries']-b['wasted_tries'])/max(a['wasted_tries'], 1)))
print('  正确上报(求助):   %d → %d' % (a['escalated'], b['escalated']))
print('  自预测校准度: %.3f  %s' % (b['calib'],
      '✅ 说能做的基本都做到了' if b['calib'] > 0.8 else '⚠️ 还不太准'))
print('  离完美上界: 浪费尝试 %d vs %d' % (b['wasted_tries'], c['wasted_tries']))
print()
print('  用时 %.2fs' % (time.time() - t0))
