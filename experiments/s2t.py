# -*- coding: utf-8 -*-
"""s2t.py 精简版: 结构强度 -> 预测能力"""
import math,random,time
from collections import Counter
t0=time.time()
random.seed(1)
N=8000

def logi(N,seed):
    s=[]; x=0.1+0.3*random.Random(seed).random()
    for _ in range(N):
        x=4*x*(1-x); s.append(1 if x<0.5 else 0)
    return s
def w_rand(N): return [random.randint(0,1) for _ in range(N)]
def w_golden(N):
    s=[];st=0
    for _ in range(N):
        s.append(st); st=random.randint(0,1) if st==0 else 0
    return s
def w_pair(N):
    a=logi(N,1); return [2*a[i]+a[i] for i in range(N)]
def w_tri(N):
    a=w_golden(N); return [4*a[i]+2*a[i]+a[i] for i in range(N)]

WORLDS=[("世界0 纯随机",w_rand,2),("世界1 禁11",w_golden,2),
        ("世界2 双坐标相关",w_pair,4),("世界3 三坐标+禁11",w_tri,8)]

def run(s,al,order=3):
    cut=int(len(s)*0.8)
    tab={}
    for i in range(order,cut):
        k=tuple(s[i-order:i])
        d=tab.setdefault(k,Counter()); d[s[i]]+=1
    hit=0;tot=0
    for i in range(cut,len(s)):
        tot+=1
        c=tab.get(tuple(s[i-order:i]))
        if c and c.most_common(1)[0][0]==s[i]: hit+=1
    return hit/tot,len(tab)

print("="*92)
print("★ 结构强度 -> 预测能力 (训练80% 测20%, 看前3个符号预测下一个)")
print("="*92)
print()
print(f"  {'世界':<24}{'熵':<10}{'禁止2字':<12}{'表大小':<10}{'准确率':<10}{'随机'}")
print("  "+"-"*78)
for nm,fn,al in WORLDS:
    s=fn(N)
    c=Counter(tuple(s[i:i+2]) for i in range(len(s)-1))
    h=-sum((v/len(s))*math.log2(v/len(s)+1e-12) for v in c.values())
    f2=al*al-len(set(tuple(s[i:i+2]) for i in range(len(s)-1)))
    a,ts=run(s,al)
    print(f"  {nm:<24}{h:<10.3f}{f2:<12}{ts:<10}{a:<10.3f}{1/al:.2f}")
print()
print("="*92)
print("★★ 决定性: 同样的【表大小】(同样成本), 准确率差多少?")
print("="*92)
print()
# 限制表大小, 看准确率
print(f"  {'世界':<24}{'表截断到50':<16}{'表截断到200':<16}{'不限制'}")
print("  "+"-"*66)
for nm,fn,al in WORLDS:
    s=fn(N); cut=int(len(s)*0.8)
    out=[]
    for LIM in [50,200,None]:
        tab={}
        for i in range(3,cut):
            k=tuple(s[i-3:i])
            if LIM and k not in tab and len(tab)>=LIM: continue
            d=tab.setdefault(k,Counter()); d[s[i]]+=1
        hit=0;tot=0
        for i in range(cut,len(s)):
            tot+=1
            c=tab.get(tuple(s[i-3:i]))
            if c and c.most_common(1)[0][0]==s[i]: hit+=1
        out.append(f"{100*hit/tot:.1f}%")
    print(f"  {nm:<24}{out[0]:<16}{out[1]:<16}{out[2]}")
print()
print("  ★ 读法: 结构强的世界, 只用50个表项就能高准确率")
print("         结构弱的世界, 给200个表项也上不去")
print(f"用时 {time.time()-t0:.2f}s")
