# -*- coding: utf-8 -*-
"""s2t2.py 修正: 真用两个独立坐标组合"""
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
def w_pair_ind(N):                 # 两个【独立】logistic
    a=logi(N,1); b=logi(N,7); return [2*a[i]+b[i] for i in range(N)]
def w_pair_rel(N):                 # 两个【相关】logistic
    a=logi(N,1); return [2*a[i]+a[i] for i in range(N)]
def w_gold2(N):                    # 黄金 × 随机
    a=w_golden(N); b=w_rand(N); return [2*a[i]+b[i] for i in range(N)]
def w_gun(N):                      # 黄金 × 黄金(独立)
    a=w_golden(N); b=w_golden(N); return [2*a[i]+b[i] for i in range(N)]

WORLDS=[("世界0 纯随机",w_rand,2),
        ("世界1 黄金(禁11)",w_golden,2),
        ("世界2 独立 logistic x2",w_pair_ind,4),
        ("世界3 相关 logistic x2",w_pair_rel,4),
        ("世界4 黄金 × 随机",w_gold2,4),
        ("世界5 黄金 × 黄金",w_gun,4)]

def run(s,al,order=3):
    cut=int(len(s)*0.8); tab={}
    for i in range(order,cut):
        k=tuple(s[i-order:i]); d=tab.setdefault(k,Counter()); d[s[i]]+=1
    hit=0;tot=0; unk=0
    for i in range(cut,len(s)):
        tot+=1
        c=tab.get(tuple(s[i-order:i]))
        if c:
            if c.most_common(1)[0][0]==s[i]: hit+=1
        else: unk+=1
    return hit/tot, len(tab), unk/tot

print("="*96)
print("★ 修正后: 结构强度 -> 预测能力 (训练80% 测20%)")
print("="*92)
print()
print(f"  {'世界':<26}{'熵':<9}{'禁止2字':<11}{'表大小':<10}{'准确率':<10}{'随机':<8}{'没见过率'}")
print("  "+"-"*86)
for nm,fn,al in WORLDS:
    s=fn(N)
    c=Counter(tuple(s[i:i+2]) for i in range(len(s)-1))
    h=-sum((v/len(s))*math.log2(v/len(s)+1e-12) for v in c.values())
    f2=al*al-len(set(tuple(s[i:i+2]) for i in range(len(s)-1)))
    a,ts,ur=run(s,al)
    print(f"  {nm:<26}{h:<9.3f}{f2:<11}{ts:<10}{a:<10.3f}{1/al:<8.2f}{ur:.3f}")
print()
print("="*92)
print("★★★ 核心结论")
print("="*92)
print("""
  对比三条线:

   世界1 黄金(禁11)      熵1.585  禁止1个   准确率 0.665  ★ 结构->能力有效
   世界3 相关 logistic   熵1.000  禁止12个  准确率 ?      ★ 相关性=约束
   世界2 独立 logistic   熵2.000  禁止0个   准确率 ?      结构没增加
   世界5 黄金×黄金       熵?      禁止?     准确率 ?

  ★ 判据: 结构强 -> 准确率明显高于随机 (且表更小)
""")
print(f"用时 {time.time()-t0:.2f}s")
