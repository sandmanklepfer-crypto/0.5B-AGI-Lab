#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
form_library.py — 形式库框架
==============================
核心思想: 模型的瓶颈不是参数, 是「形式库」覆盖度。

一个"形式"= 一类规律的结构 + 对应的搜索器 + 验证器

已收录:
  ✅ closed_form   封闭公式 (多项式/指数/组合)
  ✅ recurrence    递归/差分方程
空缺 (欢迎 PR):
  ⬜ linear_system 线性方程组
  ⬜ ode           微分方程
  ⬜ integral      积分变换
  ⬜ matrix        矩阵/线性代数
  ⬜ graph         图/组合
  ⬜ prob          概率/统计

用法:
    from form_library import FORMS, search
    print(search([2,7,20,57,166]))   # -> ('recurrence', '3*a(n-1)-2n+5', [491,1464])
"""
import math, itertools

def _primes(n):
    """前 n 个素数 (不依赖第三方库)"""
    out=[]; c=2
    while len(out)<n:
        if all(c%p for p in out if p*p<=c): out.append(c)
        c+=1
    return out
_PRIME_CACHE=_primes(80)

# ==================== 原子 (可自由扩充) ====================
ATOMS = {
    'n':              lambda k: k,
    'n^2':            lambda k: k*k,
    'n^3':            lambda k: k**3,
    '2^n':            lambda k: 2**k,
    'n!':             lambda k: math.factorial(k),
    'fib':            lambda k: [0,1,1,2,3,5,8,13,21,34,55,89,144,233,377,610,987][k] if k < 17 else 0,
    'prime':          lambda k: _PRIME_CACHE[k-1] if k >= 1 else 0,
    'T_tri':          lambda k: k*(k+1)//2,
    'S2_sq':          lambda k: k*(k+1)*(2*k+1)//6,
    'catalan':        lambda k: math.comb(2*k,k)//(k+1),
    'C2k_k':          lambda k: math.comb(2*k,k),
    '2n-1':           lambda k: 2*k-1,
}


# ==================== 形式 1: 封闭公式 ====================
def search_closed_form(seq, k0=1, max_deg=3, atoms=ATOMS):
    """a_k = 原子的线性组合"""
    # 单项
    for nm, f in atoms.items():
        if _verify(f, seq, k0):
            return nm, _pred(f, k0, len(seq))
    # 二项 (系数 -3..4)
    for (n1,f1),(n2,f2) in itertools.combinations(atoms.items(), 2):
        for a in range(1,5):
            for b in range(-3,5):
                if b == 0: continue
                g = lambda k, f1=f1, f2=f2, a=a, b=b: a*f1(k) + b*f2(k)
                if _verify(g, seq, k0):
                    return f"{a}*{n1}+{b}*{n2}", _pred(g, k0, len(seq))
    # 多项式 (直接拟合)
    if len(seq) >= 4:
        try:
            import numpy as np
            ks = np.arange(k0, k0+len(seq))
            for deg in range(1, max_deg+1):
                if len(seq) < deg+1: break
                c = np.polyfit(ks, seq, deg)
                test = np.polyval(c, ks)
                if np.allclose(test, seq, atol=1e-6):
                    fn = lambda k, c=c: float(np.polyval(c, k))
                    return f"poly(deg={deg})", [round(fn(k0+len(seq)+i)) for i in range(2)]
        except Exception:
            pass
    return None, None


# ==================== 形式 2: 递归/差分 ====================
def search_recurrence(seq, k0=1, order=1, cmax=6, dmax=25, emax=25):
    """
    a_k = c*a_{k-1} + d*k + e          (order=1)
    a_k = c1*a_{k-1} + c2*a_{k-2}       (order=2)
    """
    if len(seq) < 4: return None, None

    def build(o1, c1, c2, d, e):
        def f(k):
            v = list(seq[:o1])
            for kk in range(o1+1, k+1):
                nv = c1*v[-1] + (c2*v[-2] if o1 >= 2 else 0) + d*kk + e
                v.append(nv)
            return v[-1]
        return f

    # 一阶: a_k = c*a_{k-1} + d*k + e
    for c1 in range(1, cmax+1):
        for d in range(-dmax, dmax+1):
            for e in range(-emax, emax+1):
                f = build(1, c1, 0, d, e)
                if _verify(f, seq, k0):
                    L = len(seq)
                    pred = [f(k0+L), f(k0+L+1)]
                    return f"a_k = {c1}*a_(k-1) + {d}*k + {e}", pred
    # 二阶: a_k = c1*a_{k-1} + c2*a_{k-2}
    for c1 in range(0, cmax+1):
        for c2 in range(-6, cmax+1):
            if c1 == 0 and c2 == 0: continue
            f = build(2, c1, c2, 0, 0)
            if _verify(f, seq, k0):
                L = len(seq)
                pred = [f(k0+L), f(k0+L+1)]
                return f"a_k = {c1}*a_(k-1) + {c2}*a_(k-2)", pred
    return None, None


# ==================== 待 PR 补齐的形式 (占位) ====================
def search_linear_system(seq, **kw):
    """TODO: 欢迎 PR. a_k 由线性方程组定义时在此实现"""
    return None, None

def search_ode(seq, **kw):
    """TODO: 欢迎 PR. 微分方程解序列"""
    return None, None

def search_integral(seq, **kw):
    """TODO: 欢迎 PR. 积分变换"""
    return None, None

def search_matrix(seq, **kw):
    """TODO: 欢迎 PR. 矩阵幂/特征值"""
    return None, None

def search_graph(seq, **kw):
    """TODO: 欢迎 PR. 图计数/组合结构"""
    return None, None

def search_prob(seq, **kw):
    """TODO: 欢迎 PR. 概率分布/统计量"""
    return None, None


# ==================== 工具 ====================
def _verify(f, seq, k0):
    try:
        return all(abs(f(k0+i) - v) < 1e-6 for i, v in enumerate(seq))
    except Exception:
        return False

def _pred(f, k0, L):
    try:
        return [f(k0+L), f(k0+L+1)]
    except Exception:
        return None


# ==================== 注册表 ====================
FORMS = {
    'closed_form':   search_closed_form,
    'recurrence':    search_recurrence,
    # ---- 空缺, 等你 PR ----
    'linear_system': search_linear_system,
    'ode':           search_ode,
    'integral':      search_integral,
    'matrix':        search_matrix,
    'graph':         search_graph,
    'prob':          search_prob,
}


def search(seq, forms=None, verbose=False):
    """依次用每种形式搜索, 返回第一个命中的"""
    forms = forms or list(FORMS)
    for name in forms:
        try:
            rule, pred = FORMS[name](seq)
        except Exception as e:
            if verbose: print(f"  [{name}] 错误: {e}")
            continue
        if rule:
            return name, rule, pred
        if verbose: print(f"  [{name}] 未命中")
    return None, None, None


if __name__ == '__main__':
    TESTS = [
        ([1,4,9,16,25],      'n^2'),
        ([2,6,12,20,30],     'n^2+n'),
        ([2,4,8,16,32],      '2^n'),
        ([1,2,5,14,42],      'catalan'),
        ([2,7,20,57,166],    '★ 需要 recurrence 形式'),
        ([2,3,5,9,17],       '★ a=2a-1'),
    ]
    print("="*80)
    print("形式库测试")
    print("="*80)
    for seq, note in TESTS:
        name, rule, pred = search(seq)
        mark = "✅" if rule else "❌"
        print(f"\n{mark} {seq}")
        print(f"   期望: {note}")
        if rule:
            print(f"   命中: [{name}] {rule}")
            print(f"   预测: {pred}")
        else:
            print(f"   未命中")
    print("\n" + "="*80)
    print("空缺形式 (欢迎 PR): linear_system / ode / integral / matrix / graph / prob")
    print("="*80)
