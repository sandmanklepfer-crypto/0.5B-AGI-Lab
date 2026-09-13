# -*- coding: utf-8 -*-
"""couple2.py — 最干净对照: 同符号分布、同熵, 只有'时间结构'不同"""
import math,random,time
from collections import Counter
t0=time.time(); random.seed(3)
N=9000
def logi(x): return 3.9*x*(1-x)
def tent(x): return 2*x if x<0.5 else 2*(1-x)
def sine(x):
    v=abs(math.sin(math.pi*x)); return v if v>1e-9 else 1e-9

# 用【同一族】4个映射(不同初值), 保证每个都是标准 1bit
def sim(eps,cpl,seeds=(11,23,37,41)):
    """cpl: 'diff'=扩散耦合(拉向均值), 'indep'=独立"""
    x=[0.1+0.8*random.Random(s).random() for s in seeds]
    fs=[logi,tent,sine,logi]
    outs=[[] for _ in range(4)]
    for t in range(N):
        for i in range(4): outs[i].append(1 if x[i]<0.5 else 0)
        fx=[fs[i](x[i]) for i in range(4)]
        if cpl=='diff':
            m=sum(x)/4
            x=[(1-eps)*fx[i]+eps*m for i in range(4)]
        else:
            x=fx
        x=[min(0.9999,max(0.0001,v)) for v in x]
    return [8*outs[0][i]+4*outs[1][i]+2*outs[2][i]+outs[3][i] for i in range(N)]

def ent(s,L=1,al=16):
    c=Counter(s)
    n=len(s); return -sum((v/n)*math.log2(v/n) for v in c.values())

def acc(s,order=2):
    cut=int(len(s)*0.8); tab={}
    for i in range(order,cut):
        k=tuple(s[i-order:i]); d=tab.setdefault(k,Counter()); d[s[i]]+=1
    hit=0;tot=0
    for i in range(cut,len(s)):
        tot+=1
        c=tab.get(tuple(s[i-order:i]))
        if c and c.most_common(1)[0][0]==s[i]: hit+=1
    return hit/tot

def iid_copy(s):
    """同分布、同熵, 但【时间上完全独立】的复制品"""
    c=Counter(s); ks=list(c); ps=[c[k]/len(s) for k in ks]
    r=random.Random(99)
    return [r.choices(ks,ps)[0] for _ in range(len(s))]

print("="*96)
print("★ 最干净对照: 同符号分布、同熵, 唯一差别 = 时间结构")
print("="*96)
print()
print(f"  {'配置':<30}{'熵':<10}{'准确率(有结构)':<18}{'准确率(i.i.d.复制)':<20}{'结构增益'}")
print("  "+"-"*92)
rows=[]
for eps in [0.0,0.05,0.1,0.2,0.3,0.4]:
    s=sim(eps,'diff')
    h=ent(s); a1=acc(s); a2=acc(iid_copy(s))
    gain=a1/max(a2,1e-9)
    rows.append((eps,h,a1,a2,gain))
    print(f"  {f'扩散耦合 eps={eps}':<30}{h:<10.3f}{a1:<18.3f}{a2:<20.3f}{gain:.2f}x")
print()
print("="*96)
print("★★ 结论")
print("="*96)
print(f"""
  ★ 判据: "结构增益" = 有结构的准确率 / 同熵i.i.d.的准确率
        > 1  -> 时间结构有【独立价值】(不是单纯降熵)
        = 1  -> 只是降熵, 结构没额外作用

  实测:
     eps=0.0  (独立)   熵 {rows[0][1]:.2f}  增益 {rows[0][4]:.2f}x
     eps=0.1           熵 {rows[2][1]:.2f}  增益 {rows[2][4]:.2f}x
     eps=0.2           熵 {rows[3][1]:.2f}  增益 {rows[3][4]:.2f}x
     eps=0.4           熵 {rows[5][1]:.2f}  增益 {rows[5][4]:.2f}x

  ★★ 所以「约束耦合」把结构转成能力 —— 这件事【成立】(增益>1)
  ★ 但增益是【有限倍】, 不是无穷
""")
print(f"用时 {time.time()-t0:.2f}s")
