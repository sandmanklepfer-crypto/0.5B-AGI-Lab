# -*- coding: utf-8 -*-
"""
form_v2.py — 可组合原语引擎
=================================================================
核心思想(用户提出): 覆盖面应该是【指数】的, 不是线性的。

  线性(旧): 加一条规则 → 多覆盖一类题
  指数(新): K个原语 × 深度D → K^D 条可表达规则

指数从哪来? —— 不是暴力枚举, 是【差分/比值降阶】:
  ★ 若 Δa 是已知形式 → a = 前缀和(那个形式)
  ★ 若 a_{k+1}/a_k 趋于常数 → a 是等比
  ★ 若 a 是 f,g 的线性组合 → 组合系数解方程

这样 16 个原语能覆盖远超 16 类的序列。
"""
import math, itertools
from fractions import Fraction

# ==================== 原语 (16个, 覆盖初等序列空间) ====================
def _fibs(n=60):
    a,b=1,1; out=[]
    for _ in range(n): out.append(a); a,b=b,a+b
    return out
def _primes(n=200):
    o=[];c=2
    while len(o)<n:
        if all(c%p for p in o if p*p<=c): o.append(c)
        c+=1
    return o
_FIB=_fibs(); _PR=_primes()
ATOMS = {
    '1':      lambda k: 1,
    'n':      lambda k: k,
    'n^2':    lambda k: k*k,
    'n^3':    lambda k: k**3,
    '2^n':    lambda k: 2**k,
    '3^n':    lambda k: 3**k,
    'n!':     lambda k: math.factorial(k),
    'fib':    lambda k: _FIB[k-1] if k>=1 else 0,
    'prime':  lambda k: _PR[k-1] if k>=1 else 0,
    'tri':    lambda k: k*(k+1)//2,
    'sqsum':  lambda k: k*(k+1)*(2*k+1)//6,
    'catalan':lambda k: math.comb(2*k,k)//(k+1),
    'C2n_n':  lambda k: math.comb(2*k,k),
    '2n-1':   lambda k: 2*k-1,
    '(-1)^n': lambda k: (-1)**k,
    'n*(-1)^n':lambda k: k*((-1)**k),
}

def vals(f, k0=1, n=6):
    return [f(k) for k in range(k0, k0+n)]

def match(f, seq, k0=1):
    """严格匹配: 前 len(seq) 项全对"""
    try:
        v = vals(f, k0, len(seq))
        return v == list(seq)
    except Exception:
        return False

# ==================== 组合器 ====================
def lin2(n1,f1,a,n2,f2,b):
    return lambda k: a*f1(k) + b*f2(k)
def prod(f1,f2):
    return lambda k: f1(k)*f2(k)
def prefix_sum(f):
    """前缀和: a_k = Σ_{i<=k} f(i)  ← 差分的逆"""
    return lambda k: sum(f(i) for i in range(1,k+1))
def scaled(f,c):
    return lambda k: c*f(k)
def shifted(f,d):
    return lambda k: f(k+d)

# ==================== 搜索 (降阶优先, 非暴力) ====================
def search_v2(seq, k0=1, verbose=False):
    """
    返回 (形式描述, 下一项)
    搜索顺序 = 从简单到复杂, 每步都做L1验证
    """
    n=len(seq)
    if n<2: return None,None
    # ① 单原子 (含平移: a_k = f(k+d))
    for nm,f in ATOMS.items():
        for d in range(0,10):                      # ★ 起点偏移 k0+d
            g=shifted(f,d)
            if match(g,seq,k0): return f"{nm}(k+{d})" if d else nm, g(k0+n)
    # ② 线性组合 a*f1 + b*f2 (系数扫描)
    for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
        for a in (1,2,3,4,-1,-2):
            for b in (-3,-2,-1,1,2,3):
                g=lin2(n1,f1,a,n2,f2,b)
                if match(g,seq,k0): return f"{a}*{n1}{b:+d}*{n2}", g(k0+n)
    # ③ 乘积 (含自乘积 f*f)
    for nm,f in ATOMS.items():
        g=lambda k,f=f: f(k)*f(k)
        if match(g,seq,k0): return f"{nm}^2", g(k0+n)
    for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
        g=prod(f1,f2)
        if match(g,seq,k0): return f"{n1}*{n2}", g(k0+n)
    # ③b 带符号/平方的交叉乘积: (a*f1^p) * f2
    for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
        for pw in (2,):
            g=lambda k,f1=f1,f2=f2,pw=pw: (f1(k)**pw)*f2(k)
            if match(g,seq,k0): return f"{n1}^{pw}*{n2}", g(k0+n)
    # ④ ★ 差分降阶: Δa 能匹配某形式 → a = 前缀和
    d1=[seq[i+1]-seq[i] for i in range(n-1)]
    r,_=search_v2(d1,k0,verbose=False)
    if r is not None:
        # 递归找一阶差分的规则, 用前缀和还原
        dr=lambda k: _eval_rule(r,k)
        g=prefix_sum(dr)
        if match(g,seq,k0):
            gs=lambda k: seq[-1]+sum(dr(i) for i in range(k0+n,k+1))
            return f"Σ[{r}]", seq[-1]+sum(dr(i) for i in range(k0+n,k0+n+1))
    # ④b ★ 递推型: a_{k+1} = p*a_k + q*k + r  (解3元一次)
    if n>=4:
        import numpy as np
        A=np.array([[seq[i],i+1,1.0] for i in range(3)])
        try:
            pqr=np.linalg.solve(A,np.array(seq[1:4],dtype=float))
            if all(abs(x-round(x))<1e-6 for x in pqr):
                p_,q_,r_=[round(x) for x in pqr]
                g=lambda k: p_*seq[k-k0]+q_*k+r_ if k0<=k<k0+n else None
                ok=True; cur=seq[-1]
                for k in range(k0+n,k0+n):
                    nx=p_*cur+q_*k+r_
                    cur=nx
                # 验证全程
                vv=[seq[0]]
                for i in range(n-1): vv.append(p_*vv[-1]+q_*(k0+i)+r_)
                if vv==list(seq):
                    return f"a(k+1)={p_}*a(k){'+' if q_>=0 else ''}{q_}*k{'+' if r_>=0 else ''}{r_}", p_*seq[-1]+q_*(k0+n-1)+r_
        except Exception: pass
    # ⑤ 比值: a_{k+1}/a_k 是常数或有规律
    if all(x!=0 for x in seq):
        rt=[Fraction(seq[i+1],seq[i]) for i in range(n-1)]
        if len(set(rt))==1 and rt[0].denominator==1:
            c=rt[0].numerator
            g=scaled(ATOMS['1'],0)
            g=lambda k: seq[0]*(c**(k-1))
            if match(g,seq,k0): return f"{seq[0]}*{c}^(n-1)", g(k0+n)
    # ⑥ 多项式拟合 (≤3次)
    import numpy as np
    ks=np.arange(k0,k0+n)
    for deg in range(1,4):
        if n<deg+2: continue
        c=np.polyfit(ks,seq,deg)
        if np.allclose(np.polyval(c,ks),seq,rtol=1e-9):
            g=lambda k: np.polyval(c,k)
            return f"poly{deg}", float(g(k0+n))
    return None,None

def _eval_rule(r,k):
    """把规则名转成可调用 (仅支持部分)"""
    if r in ATOMS: return ATOMS[r](k)
    import re
    m=re.match(r'(-?\d+)\*(\S+?)([+-]\d+)\*(\S+)$',r)
    if m:
        a=float(m.group(1)); n1=m.group(2); b=float(m.group(3)); n2=m.group(4)
        return a*ATOMS[n1](k)+b*ATOMS[n2](k)
    m=re.match(r'(\S+)\*(\S+)$',r)
    if m: return ATOMS[m.group(1)](k)*ATOMS[m.group(2)](k)
    if r.startswith('poly'):
        return 0
    return 0

if __name__=='__main__':
    import json,sys
    BANK=json.load(open('/workspace/_BANK60.json'))
    ok=0; miss=[]
    for b in BANK:
        r,p=search_v2(b['seq'])
        hit = (p==b['next'])
        if hit: ok+=1
        else: miss.append((b['name'],b['seq'],b['next'],r,p))
    print(f"form_v2 覆盖: {ok}/{len(BANK)}")
    print("未命中:")
    for m in miss[:10]: print("  ",m)
