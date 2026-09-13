# -*- coding: utf-8 -*-
"""topo.py — 耦合【拓扑】的影响: 同样k、同样强度, 只换连接方式"""
import math,random,time
from collections import Counter
t0=time.time(); random.seed(11)
N=8000; K=4
def logi(x): return 3.9*x*(1-x)
def tent(x): return 2*x if x<0.5 else 2*(1-x)
def sine(x):
    v=abs(math.sin(math.pi*x)); return v if v>1e-9 else 1e-9
FS=[logi,tent,sine,logi]

def build_topo(kind):
    """返回邻接权重矩阵 A (行i 被 谁 影响)"""
    A=[[0.0]*K for _ in range(K)]
    if kind=='none': return A
    if kind=='diffuse':                       # 全连接(拉向均值)
        for i in range(K):
            for j in range(K):
                if i!=j: A[i][j]=1.0/(K-1)
        return A
    if kind=='ring':                          # 环: i 被 i-1 影响
        for i in range(K): A[i][(i-1)%K]=1.0
        return A
    if kind=='ring2':                         # 双向环 50/50
        for i in range(K):
            A[i][(i-1)%K]=0.5; A[i][(i+1)%K]=0.5
        return A
    if kind=='driver':                        # 0 驱动 1,2,3 (单向)
        for i in range(1,K): A[i][0]=1.0
        return A
    if kind=='chain':                         # 链: i 被 i-1 影响
        for i in range(1,K): A[i][i-1]=1.0
        return A
    if kind=='sparse':                        # 稀疏随机
        r=random.Random(3)
        for i in range(K):
            js=[j for j in range(K) if j!=i]
            for j in r.sample(js,2): A[i][j]=0.5
        return A
    return A

def sim(kind,eps):
    x=[0.1+0.8*random.Random(11+i*13).random() for i in range(K)]
    A=build_topo(kind)
    outs=[[] for _ in range(K)]
    for t in range(N):
        for i in range(K): outs[i].append(1 if x[i]<0.5 else 0)
        fx=[FS[i](x[i]) for i in range(K)]
        nb=[sum(A[i][j]*x[j] for j in range(K)) for i in range(K)]
        x=[(1-eps)*fx[i]+eps*nb[i] for i in range(K)]
        x=[min(0.9999,max(0.0001,v)) for v in x]
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

TOPO=['none','diffuse','ring','ring2','driver','chain','sparse']
print("="*94)
print(f"★ 耦合拓扑对比 (k={K}, 每层测eps=0.2/0.3 找最优)")
print("="*94)
print()
print(f"  {'拓扑':<12}{'eps':<7}{'熵':<10}{'准确率':<11}{'同熵iid':<11}{'结构增益'}")
print("  "+"-"*64)
best={}
for tp in TOPO:
    row=[]
    for eps in [0.2,0.3]:
        s=sim(tp,eps); h=ent(s); a1=acc(s); a2=acc(iid(s)); g=a1/max(a2,1e-9)
        row.append((h,a1,a2,g))
        print(f"  {tp:<12}{eps:<7}{h:<10.3f}{a1:<11.3f}{a2:<11.3f}{g:.2f}x")
    best[tp]=max(row,key=lambda r:r[3])
    print()
print("="*94)
print("★★ 排名 (按结构增益)")
print("="*94)
print()
for tp,g in sorted(best.items(),key=lambda x:-x[1][3]):
    print(f"  {tp:<12}增益 {g[3]:.2f}x   熵 {g[0]:.3f}   准确率 {g[1]:.3f}")
print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ★ 如果拓扑之间差异明显 -> 拓扑是【可调的杠杆】(好消息)
  ★ 如果差不多         -> 拓扑不重要, 只有'有没有耦合'重要
""")
print(f"用时 {time.time()-t0:.2f}s")
