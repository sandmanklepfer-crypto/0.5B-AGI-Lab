# -*- coding: utf-8 -*-
"""数学算子库 — 可执行原语 (每条都真能算)"""
import numpy as np, math
from fractions import Fraction

# ============ 代数 ============
def solve_linear(a,b):            # ax+b=0
    if a==0: return None
    return -b/a
def solve_quad(a,b,c):            # ax²+bx+c=0
    if a==0: return solve_linear(b,c)
    d=b*b-4*a*c
    if d<0: return None
    r=math.sqrt(d)
    return sorted([(-b+r)/(2*a),(-b-r)/(2*a)])
def solve_system2(a1,b1,c1,a2,b2,c2):   # 2元一次
    D=a1*b2-a2*b1
    if abs(D)<1e-12: return None
    return ((c1*b2-c2*b1)/D, (a1*c2-a2*c1)/D)
# ============ 数论 ============
def is_prime(n):
    if n<2: return False
    if n<4: return True
    if n%2==0: return False
    for i in range(3,int(n**.5)+1,2):
        if n%i==0: return False
    return True
def factorize(n):
    f=[];d=2
    while d*d<=n:
        while n%d==0: f.append(d); n//=d
        d+=1
    if n>1: f.append(n)
    return f
def gcd(a,b):
    while b: a,b=b,a%b
    return abs(a)
def modinv(a,m):
    g,x=m,a
    x0,x1=0,1
    while x>1:
        q=x//m; x,m=m,x%m; x0,x1=x1-q*x0,x0
    return x1%g if x1>0 else x1%g+g
def euler_phi(n):
    r=n;p=2;m=n
    while p*p<=m:
        if m%p==0:
            while m%p==0: m//=p
            r-=r//p
        p+=1
    if m>1: r-=r//m
    return r
# ============ 组合 ============
def C(n,k):
    if k<0 or k>n: return 0
    return math.comb(n,k)
def perm(n,k):
    if k<0 or k>n: return 0
    return math.perm(n,k)
def catalan(n): return math.comb(2*n,n)//(n+1)
def fib(n):
    a,b=0,1
    for _ in range(n): a,b=b,a+b
    return a
# ============ 线性代数 ============
def det(M): return float(np.linalg.det(np.array(M,dtype=float)))
def inv(M): return np.linalg.inv(np.array(M,dtype=float)).tolist()
def eig(M):
    w=np.linalg.eigvals(np.array(M,dtype=float))
    return [complex(x) for x in w]
def rank(M): return int(np.linalg.matrix_rank(np.array(M,dtype=float)))
# ============ 微积分 ============
def deriv_poly(coef):             # coef=[a0,a1,...] → 导数系数
    return [i*coef[i] for i in range(1,len(coef))]
def integ_poly(coef):             # 不定积分系数 (常数项0)
    return [0]+[coef[i]/(i+1) for i in range(len(coef))]
def eval_poly(coef,x):            # Horner
    r=0
    for c in reversed(coef): r=r*x+c
    return r
# ============ 概率 ============
def bayes(pa,pb_given_a,pb_given_nota):
    pa_not=1-pa
    pb=pb_given_a*pa+pb_given_nota*pa_not
    return pb_given_a*pa/pb if pb>0 else None
def binom_pmf(n,k,p): return math.comb(n,k)*(p**k)*((1-p)**(n-k))
def expect(vals,probs): return sum(v*p for v,p in zip(vals,probs))
# ============ 优化 ============
def lp_corners(A,b):
    """线性规划: max c·x, 枚举顶点 (小规模)"""
    from itertools import combinations
    A=np.array(A,dtype=float); b=np.array(b,dtype=float)
    m,n=A.shape; pts=[]
    for idx in combinations(range(m),n):
        try:
            x=np.linalg.solve(A[list(idx)],b[list(idx)])
        except Exception: continue
        if np.all(A@x<=b+1e-9): pts.append(tuple(x))
    return pts
# ============ 信息论 ============
def entropy(p):
    p=np.array([x for x in p if x>0],dtype=float)
    return float(-(p*np.log2(p)).sum())
def mutual_info(joint):
    P=np.array(joint,dtype=float); P/=P.sum()
    px=P.sum(1,keepdims=True); py=P.sum(0,keepdims=True)
    with np.errstate(divide='ignore',invalid='ignore'):
        t=P*np.log2(P/(px*py)); t=np.nan_to_num(t)
    return float(t.sum())
def kl(p,q):
    p=np.array(p,float);q=np.array(q,float)
    m=p>0
    return float((p[m]*np.log2(p[m]/q[m])).sum())
def hamming_bound(n,k):
    """汉明码冗余下界"""
    t=0
    for i in range(k+1): t+=math.comb(n,i)
    return 2**n/t

REGISTRY={
 'solve_linear':solve_linear,'solve_quad':solve_quad,'solve_system2':solve_system2,
 'is_prime':is_prime,'factorize':factorize,'gcd':gcd,'modinv':modinv,'euler_phi':euler_phi,
 'C':C,'perm':perm,'catalan':catalan,'fib':fib,
 'det':det,'inv':inv,'eig':eig,'rank':rank,
 'deriv_poly':deriv_poly,'integ_poly':integ_poly,'eval_poly':eval_poly,
 'bayes':bayes,'binom_pmf':binom_pmf,'expect':expect,'lp_corners':lp_corners,
 'entropy':entropy,'mutual_info':mutual_info,'kl':kl,'hamming_bound':hamming_bound,
}
if __name__=='__main__':
    print("数学算子库:", len(REGISTRY), "个算子")
    print("  is_prime(97) =",is_prime(97))
    print("  factorize(360) =",factorize(360))
    print("  solve_quad(1,-5,6) =",solve_quad(1,-5,6))
    print("  C(10,3) =",C(10,3), " catalan(5) =",catalan(5))
    print("  entropy([0.5,0.5]) =",entropy([0.5,0.5]))
