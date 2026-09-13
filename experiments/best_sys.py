# -*- coding: utf-8 -*-
"""best_sys.py — 用最优配置(ring, eps=0.5, k=4) 做端到端能力测试"""
import math,random,time
from collections import Counter
t0=time.time()
N=4000; K=4
def logi(x): return 3.9*x*(1-x)
def tent(x): return 2*x if x<0.5 else 2*(1-x)
def sine(x):
    v=abs(math.sin(math.pi*x)); return v if v>1e-9 else 1e-9
FS=[logi,tent,sine,logi]
def build(kind,K=K):
    A=[[0.0]*K for _ in range(K)]
    if kind=='ring':
        for i in range(K): A[i][(i-1)%K]=1.0
    elif kind=='diffuse':
        for i in range(K):
            for j in range(K):
                if i!=j: A[i][j]=1.0/(K-1)
    return A
def run(kind,eps,seed):
    x=[0.1+0.8*random.Random(seed+i*13).random() for i in range(K)]
    A=build(kind); outs=[[] for _ in range(K)]
    for t in range(N):
        for i in range(K): outs[i].append(1 if x[i]<0.5 else 0)
        fx=[FS[i](x[i]) for i in range(K)]
        nb=[sum(A[i][j]*x[j] for j in range(K)) for i in range(K)]
        x=[min(0.9999,max(0.0001,(1-eps)*fx[i]+eps*nb[i])) for i in range(K)]
    return [sum(outs[i][t]<<(K-1-i) for i in range(K)) for t in range(N)]

from collections import defaultdict
def task_next(s,order=2):
    cut=int(len(s)*0.75);tab=defaultdict(Counter)
    for i in range(order,cut):
        k=tuple(s[i-order:i]);tab[k][s[i]]+=1
    hit=0;tot=0
    for i in range(cut,len(s)):
        tot+=1;c=tab.get(tuple(s[i-order:i]))
        if c and c.most_common(1)[0][0]==s[i]: hit+=1
    return hit/tot
def task_long(s,L=4):
    """长程: 看前L个, 预测下一个 (更难)"""
    cut=int(len(s)*0.75);tab=defaultdict(Counter)
    for i in range(L,cut):
        tab[tuple(s[i-L:i])][s[i]]+=1
    hit=0;tot=0;seen=0
    for i in range(cut,len(s)):
        tot+=1;c=tab.get(tuple(s[i-L:i]))
        if c:
            seen+=1
            if c.most_common(1)[0][0]==s[i]: hit+=1
    return hit/tot, seen/tot

print("="*90)
print("★ 最优配置端到端: ring + eps=0.5 + k=4   vs   基线")
print("="*90)
print()
print(f"  {'系统':<22}{'短程预测':<12}{'长程预测':<12}{'长程覆盖率':<12}{'熵'}")
print("  "+"-"*70)
for nm,kind,eps in [("ring eps=0.5 (最优)","ring",0.5),
                    ("ring eps=0.3","ring",0.3),
                    ("diffuse eps=0.5","diffuse",0.5)]:
    a1=[];a2=[];a3=[];hh=[]
    for sd in range(4):
        s=run(kind,eps,sd)
        a1.append(task_next(s,2)); 
        r,seen=task_long(s,4); a2.append(r); a3.append(seen)
        c=Counter(s);n=len(s)
        hh.append(-sum((v/n)*math.log2(v/n) for v in c.values()))
    print(f"  {nm:<22}{sum(a1)/4:<12.3f}{sum(a2)/4:<12.3f}{sum(a3)/4:<12.3f}{sum(hh)/4:.2f}")
print()
print("="*90)
print("★ 关键: 结构是【跨seed通用】的吗? (用seed0学, 测seed1)")
print("="*90)
print()
print(f"  {'系统':<22}{'同seed准确率':<16}{'跨seed准确率':<16}{'说明'}")
print("  "+"-"*74)
for nm,kind,eps in [("ring eps=0.5","ring",0.5),("diffuse eps=0.5","diffuse",0.5)]:
    s0=run(kind,eps,0); s1=run(kind,eps,100)
    tab=defaultdict(Counter)
    for i in range(2,len(s0)):
        tab[tuple(s0[i-2:i])][s0[i]]+=1
    hit=0;tot=0;seen=0
    for i in range(2,len(s1)):
        tot+=1;c=tab.get(tuple(s1[i-2:i]))
        if c:
            seen+=1
            if c.most_common(1)[0][0]==s1[i]: hit+=1
    # 同seed(自己测自己)
    tab2=defaultdict(Counter)
    for i in range(2,int(len(s0)*0.75)):
        tab2[tuple(s0[i-2:i])][s0[i]]+=1
    h2=0;t2=0
    for i in range(int(len(s0)*0.75),len(s0)):
        t2+=1;c=tab2.get(tuple(s0[i-2:i]))
        if c and c.most_common(1)[0][0]==s0[i]: h2+=1
    print(f"  {nm:<22}{h2/t2:<16.3f}{hit/max(tot,1):<16.3f}{'★ 结构可迁移!' if hit/max(tot,1)>0.3 else '结构不通用'}")
print()
print(f"用时 {time.time()-t0:.2f}s")
