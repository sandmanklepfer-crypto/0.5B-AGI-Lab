# -*- coding: utf-8 -*-
"""社会科学算子库 — 可执行 (博弈/运筹/社会选择/规范)"""
import numpy as np
from itertools import product

# ============ 博弈论 ============
def nash_pure(A,B):
    """2x2 纯策略纳什均衡"""
    out=[]
    if A[0,0]>=A[1,0] and B[0,0]>=B[0,1]: out.append((0,0))
    if A[0,1]>=A[1,1] and B[0,1]>=B[0,0]: out.append((0,1))
    if A[1,0]>=A[0,0] and B[1,0]>=B[1,1]: out.append((1,0))
    if A[1,1]>=A[0,1] and B[1,1]>=B[1,0]: out.append((1,1))
    return out
def nash_mixed(A,B):
    """2x2 混合纳什 (返回(p,q)概率)"""
    d1=A[0,0]-A[0,1]-A[1,0]+A[1,1]
    d2=B[0,0]-B[1,0]-B[0,1]+B[1,1]
    if abs(d1)<1e-12 or abs(d2)<1e-12: return None
    q=(A[1,1]-A[0,1])/d1; p=(B[1,1]-B[1,0])/d2
    if 0<p<1 and 0<q<1: return (float(p),float(q))
    return None
def dominant(A):
    """行玩家严格占优策略"""
    return [i for i in range(A.shape[0]) if all(A[i,j]>A[k,j] for k in range(A.shape[0]) if k!=i for j in range(A.shape[1]))]
def best_response(A,opp):
    """给定对手策略(概率), 求最优反应"""
    v=A@np.array(opp,dtype=float)
    return int(np.argmax(v)), float(v.max())
def price_of_anarchy(social,social_eq):
    """无政府状态代价 = 最优社会收益 / 均衡收益"""
    return social/social_eq if social_eq else float('inf')
def backward_induct(payoff_tree):
    """逆向归纳 (序列博弈) — 树为嵌套tuple"""
    if not isinstance(payoff_tree,tuple) or len(payoff_tree)==0: return payoff_tree
    if all(not isinstance(x,tuple) for x in payoff_tree):
        return payoff_tree
    vals=[backward_induct(x) for x in payoff_tree]
    return max(vals) if all(isinstance(v,(int,float)) for v in vals) else vals
# ============ 运筹学 ============
def knapsack_01(w,v,W):
    """0/1背包 — DP精确"""
    n=len(w); dp=[[0]*(W+1) for _ in range(n+1)]
    for i in range(1,n+1):
        for c in range(W+1):
            dp[i][c]=dp[i-1][c]
            if w[i-1]<=c: dp[i][c]=max(dp[i][c],dp[i-1][c-w[i-1]]+v[i-1])
    return dp[n][W]
def tsp_bruteforce(D):
    """TSP 精确 (小规模)"""
    from itertools import permutations
    n=len(D); best=float('inf'); bp=None
    for p in permutations(range(1,n)):
        tour=(0,)+p
        c=sum(D[tour[i]][tour[(i+1)%n]] for i in range(n))
        if c<best: best=c;bp=tour
    return best,bp
def assignment(cost):
    """指派问题 — 匈牙利算法(scipy可选)/暴力小规模"""
    from itertools import permutations
    n=len(cost); best=float('inf');bp=None
    for p in permutations(range(n)):
        c=sum(cost[i][p[i]] for i in range(n))
        if c<best: best=c;bp=p
    return best,bp
def min_cost_flow_1d(supply,demand,cost):
    """一维运输问题"""
    s=list(supply); d=list(demand); tot=0
    i=j=0
    while i<len(s) and j<len(d):
        x=min(s[i],d[j]); tot+=x*cost[i][j]
        s[i]-=x; d[j]-=x
        if s[i]==0: i+=1
        if d[j]==0: j+=1
    return tot
# ============ 社会选择 ============
def borda(votes,n):
    s=np.zeros(n)
    for v in votes:
        for r,a in enumerate(v): s[a]+=(n-1-r)
    return s.tolist(), int(np.argmax(s))
def condorcet(votes,n):
    for a in range(n):
        wins=0
        for b in range(n):
            if a==b: continue
            cn=sum(1 for v in votes if list(v).index(a)<list(v).index(b))
            if cn>len(votes)/2: wins+=1
        if wins==n-1: return a
    return None
def copeland(votes,n):
    sc=np.zeros(n)
    for a in range(n):
        for b in range(n):
            if a==b: continue
            cn=sum(1 for v in votes if list(v).index(a)<list(v).index(b))
            sc[a]+= 1 if cn>len(votes)/2 else 0
    return sc.tolist(), int(np.argmax(sc))
def kemeny(votes,n):
    """Kemeny最优排序 (暴力)"""
    from itertools import permutations
    best=float('inf');bp=None
    for p in permutations(range(n)):
        pos={a:i for i,a in enumerate(p)}
        k=0
        for v in votes:
            for a in range(n):
                for b in range(n):
                    if pos[a]<pos[b] and list(v).index(a)>list(v).index(b): k+=1
        if k<best: best=k;bp=p
    return best,bp
# ============ 规范/演化 ============
def replicator(P,f0,steps=500):
    """复制动力学"""
    f=np.array(f0,dtype=float); P=np.array(P,dtype=float)
    for _ in range(steps):
        fit=P@f
        fi=f*fit
        s=fi.sum()
        if s<=0: break
        f=fi/s
    return f.tolist()
def ess(P):
    """演化稳定策略 (对称博弈)"""
    A=np.array(P,dtype=float); n=A.shape[0]
    out=[]
    for i in range(n):
        # i 是ESS: 对任何 j≠i, A[i,i]>=A[j,i] 且若等则 A[i,j]>A[j,j]
        ok=all(A[i,i]>=A[j,i] for j in range(n))
        if ok:
            ok2=all(A[i,i]>A[j,i] or A[i,j]>A[j,j] for j in range(n) if j!=i)
            if ok2: out.append(i)
    return out
def is_ess(A,i):
    A=np.array(A,dtype=float); n=len(A)
    return all(A[i,i]>A[j,i] or (A[i,i]==A[j,i] and A[i,j]>A[j,j]) for j in range(n) if j!=i)
# ============ 偏好反推 ============
def auction_infer_value(bid,n):
    """一价拍卖: 从出价反推估值"""
    return bid*n/(n-1) if n>1 else None
def rubinstein_infer_patience(share,d2):
    """鲁宾斯坦议价: 从份额反推耐心d1"""
    return share/(1-d2+d2*share)
def rubinstein_share(d1,d2):
    return d1*(1-d2)/(1-d1*d2)

REGISTRY={
 'nash_pure':nash_pure,'nash_mixed':nash_mixed,'dominant':dominant,'best_response':best_response,
 'price_of_anarchy':price_of_anarchy,'backward_induct':backward_induct,
 'knapsack_01':knapsack_01,'tsp':tsp_bruteforce,'assignment':assignment,'transport':min_cost_flow_1d,
 'borda':borda,'condorcet':condorcet,'copeland':copeland,'kemeny':kemeny,
 'replicator':replicator,'ess':ess,'is_ess':is_ess,
 'infer_value':auction_infer_value,'infer_patience':rubinstein_infer_patience,'rubinstein':rubinstein_share,
}
if __name__=='__main__':
    print("社科算子库:",len(REGISTRY),"个")
    A=np.array([[3,0],[5,1]]); B=np.array([[3,5],[0,1]])
    print("  囚徒困境纳什:",nash_pure(A,B))
    print("  严格占优:",dominant(np.array([[3,0],[1,2]])))
    print("  Borda:",borda([[0,1,2],[0,2,1],[1,0,2]],3))
    print("  复制动力学:",replicator([[2,0],[0,2]],[0.3,0.7]))
    print("  一价拍卖反推(出价20,5人):",auction_infer_value(20,5))
