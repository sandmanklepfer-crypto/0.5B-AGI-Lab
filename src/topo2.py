# -*- coding: utf-8 -*-
"""topo2.py — 严格对照: 把各拓扑调到【同熵】, 再比结构增益"""
import math,random,time
from collections import Counter
t0=time.time()
N=4000
def logi(x): return 3.9*x*(1-x)
def tent(x): return 2*x if x<0.5 else 2*(1-x)
def sine(x):
    v=abs(math.sin(math.pi*x)); return v if v>1e-9 else 1e-9
FS=[logi,tent,sine,logi]
def build(kind,K=4):
    A=[[0.0]*K for _ in range(K)]
    if kind=='diffuse':
        for i in range(K):
            for j in range(K):
                if i!=j: A[i][j]=1.0/(K-1)
    elif kind=='ring':
        for i in range(K): A[i][(i-1)%K]=1.0
    elif kind=='ring2':
        for i in range(K): A[i][(i-1)%K]=0.5; A[i][(i+1)%K]=0.5
    elif kind=='driver':
        for i in range(1,K): A[i][0]=1.0
    elif kind=='chain':
        for i in range(1,K): A[i][i-1]=1.0
    return A
def sim(kind,eps,seed,K=4):
    x=[0.1+0.8*random.Random(seed+i*13).random() for i in range(K)]
    A=build(kind,K); outs=[[] for _ in range(K)]
    for t in range(N):
        for i in range(K): outs[i].append(1 if x[i]<0.5 else 0)
        fx=[FS[i](x[i]) for i in range(K)]
        nb=[sum(A[i][j]*x[j] for j in range(K)) for i in range(K)]
        x=[min(0.9999,max(0.0001,(1-eps)*fx[i]+eps*nb[i])) for i in range(K)]
    out=[]
    for t in range(N):
        v=0
        for i in range(K): v=v*2+outs[i][t]
        out.append(v)
    return out
def ent(s):
    c=Counter(s);n=len(s);return -sum((v/n)*math.log2(v/n) for v in c.values())
def acc(s,order=2):
    cut=int(len(s)*0.8);tab={}
    for i in range(order,cut):
        k=tuple(s[i-order:i]);d=tab.setdefault(k,Counter());d[s[i]]+=1
    hit=0;tot=0
    for i in range(cut,len(s)):
        tot+=1
        c=tab.get(tuple(s[i-order:i]))
        if c and c.most_common(1)[0][0]==s[i]: hit+=1
    return hit/tot
def iid(s):
    c=Counter(s);ks=list(c);ps=[c[k]/len(s) for k in ks];r=random.Random(7)
    return [r.choices(ks,ps)[0] for _ in range(len(s))]
def find_eps(kind,target,seeds=(1,)):
    "二分找使熵≈target的eps, 用多seed平均(减噪声)"
    lo,hi=0.0,0.95
    for _ in range(7):
        mid=(lo+hi)/2
        hs=[ent(sim(kind,mid,s)) for s in seeds]
        if sum(hs)/len(hs) > target: lo=mid
        else: hi=mid
    eps=(lo+hi)/2
    hh=[ent(sim(kind,eps,s)) for s in seeds]
    aa=[acc(sim(kind,eps,s))/max(acc(iid(sim(kind,eps,s))),1e-9) for s in seeds]
    return eps,sum(hh)/len(hh),sum(aa)/len(aa)

print("="*94)
print("★ 严格对照: 调各拓扑到【同熵】, 比结构增益 (3个seed平均)")
print("="*94)
print()
print(f"  {'拓扑':<12}{'目标熵':<10}{'实际熵':<10}{'needed eps':<13}{'结构增益':<12}{'排名'}")
print("  "+"-"*72)
TOPO=['diffuse','ring','ring2','driver','chain']
res=[]
for tp in TOPO:
    r=[]
    for tgt in [2.0]:
        eps,h,g=find_eps(tp,tgt)
        r.append((tgt,eps,h,g))
    res.append((tp,r))
for tp,r in res:
    line=[]
    for tgt,eps,h,g in r:
        line.append(f"[H{tgt}]eps={eps:.2f} 增益{g:.2f}x")
    print(f"  {tp:<12}" + "  ".join(line))
print()
print("="*94)
print("★★ 同熵下的平均增益排名")
print("="*94)
print()
rank=[]
for tp,r in res:
    rank.append((sum(x[3] for x in r)/len(r),tp))
for g,tp in sorted(rank,reverse=True):
    print(f"  {tp:<12}平均增益 {g:.2f}x")
print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ★ 如果同熵下拓扑仍有差异 -> 拓扑是【真杠杆】
  ★ 如果同熵下都差不多     -> 之前的差异只是'熵不同'造成的假象
""")
print(f"用时 {time.time()-t0:.2f}s")
