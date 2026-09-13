# -*- coding: utf-8 -*-
"""confirm.py — 多seed确认: ring 的高增益是真的还是噪声?"""
import math,random,time
from collections import Counter
t0=time.time()
N=3000; K=4
def logi(x): return 3.9*x*(1-x)
def tent(x): return 2*x if x<0.5 else 2*(1-x)
def sine(x):
    v=abs(math.sin(math.pi*x)); return v if v>1e-9 else 1e-9
FS=[logi,tent,sine,logi]
def build(kind):
    A=[[0.0]*K for _ in range(K)]
    if kind=='diffuse':
        for i in range(K):
            for j in range(K):
                if i!=j: A[i][j]=1.0/(K-1)
    elif kind=='ring':
        for i in range(K): A[i][(i-1)%K]=1.0
    elif kind=='ring2':
        for i in range(K): A[i][(i-1)%K]=0.5; A[i][(i+1)%K]=0.5
    return A
def sim(kind,eps,seed):
    x=[0.1+0.8*random.Random(seed+i*13).random() for i in range(K)]
    A=build(kind); outs=[[] for _ in range(K)]
    for t in range(N):
        for i in range(K): outs[i].append(1 if x[i]<0.5 else 0)
        fx=[FS[i](x[i]) for i in range(K)]
        nb=[sum(A[i][j]*x[j] for j in range(K)) for i in range(K)]
        x=[min(0.9999,max(0.0001,(1-eps)*fx[i]+eps*nb[i])) for i in range(K)]
    return [sum(outs[i][t]<<(K-1-i) for i in range(K)) for t in range(N)]
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
def iid(s,seed=7):
    c=Counter(s);ks=list(c);ps=[c[k]/len(s) for k in ks];r=random.Random(seed)
    return [r.choices(ks,ps)[0] for _ in range(len(s))]

print("="*90)
print("★ 多seed确认: ring 的增益是真的吗? (每个配置跑6个seed)")
print("="*90)
print()
print(f"  {'拓扑':<12}{'eps':<8}{'增益(6seed)':<14}{'标准差':<12}{'熵'}")
print("  "+"-"*62)
for kind in ['ring','diffuse','ring2']:
    for eps in [0.3,0.5]:
        gs=[];hs=[]
        for sd in range(6):
            s=sim(kind,eps,sd)
            gs.append(acc(s)/max(acc(iid(s)),1e-9)); hs.append(ent(s))
        m=sum(gs)/len(gs)
        sd_=math.sqrt(sum((x-m)**2 for x in gs)/len(gs))
        print(f"  {kind:<12}{eps:<8}{m:<14.2f}{sd_:<12.2f}{sum(hs)/len(hs):.2f}")
print()
print("="*90)
print("★ 如果标准差很大 -> 之前的 5.16x 是噪声; 标准差小 -> 是真的")
print("="*90)
print(f"用时 {time.time()-t0:.2f}s")
