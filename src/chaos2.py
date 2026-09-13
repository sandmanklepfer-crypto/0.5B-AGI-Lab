# -*- coding: utf-8 -*-
"""chaos2.py — 决定性对照: 独立混沌 vs 相关混沌, 组合后结构差多少"""
import math,random,time
from collections import Counter
import zlib
t0=time.time()
N=40000

def logi(N,seed):
    s=[]; x=0.1+0.3*random.Random(seed).random()
    for _ in range(N):
        x=4*x*(1-x); s.append(1 if x<0.5 else 0)
    return s
def henon(N,seed):
    s=[]; r=random.Random(seed); x=0.1+0.2*r.random(); y=0.1
    for _ in range(N):
        x,y=1-1.4*x*x+y,0.3*x; s.append(1 if x<0 else 0)
    return s
def prod(seqs):
    k=len(seqs)
    return [sum(seqs[j][i]*(2**j) for j in range(k)) for i in range(len(seqs[0]))]
def H(seq,L):
    c=Counter(tuple(seq[i:i+L]) for i in range(len(seq)-L+1))
    n=sum(c.values()); return -sum((v/n)*math.log2(v/n) for v in c.values())/L
def forb(seq,L,al):
    real=set(tuple(seq[i:i+L]) for i in range(len(seq)-L+1))
    return al**L-len(real)
def comp(seq):
    b=bytes(bytearray(seq[:20000])); return 20000/len(zlib.compress(b,9))

print("="*94)
print("★ 决定性对照: 「独立混沌」 vs 「相关混沌」, 组合后有没有结构?")
print("="*94)
print()
print("  结构判据: 禁止模式数 (>0 = 有结构)  |  结构率 = 1 - 出现模式/全部可能")
print()
print(f"  {'组合方式':<30}{'熵':<9}{'禁止2字':<10}{'禁止3字':<10}{'结构率':<10}{'压缩率':<10}{'判定'}")
print("  "+"-"*94)
cases=[
 ("① 独立 logistic × logistic",[logi(N,1),logi(N,2)],4),
 ("② 相关 logistic × logistic",[logi(N,1),logi(N,1)],4),
 ("③ 独立 Henon × Henon",   [henon(N,1),henon(N,2)],4),
 ("④ 相关 Henon × Henon",   [henon(N,1),henon(N,1)],4),
 ("⑤ 三者独立 logistic",     [logi(N,1),logi(N,2),logi(N,3)],8),
 ("⑥ 三者相关 logistic",     [logi(N,1),logi(N,1),logi(N,1)],8),
]
for nm,ss,al in cases:
    s=prod(ss)
    h=H(s,8); f2=forb(s,2,al); f3=forb(s,3,al); cr=comp(s)
    tot=al**2; sr=1-(tot-f2)/tot
    tag="✅ 有结构" if f2>0 else "❌ 纯随机"
    print(f"  {nm:<30}{h:<9.3f}{f2:<10}{f3:<10}{sr:<10.2f}{cr:<10.2f}{tag}")
print()
print("="*94)
print("★★ 结论: 结构不在【个体】里, 在【关系】里")
print("="*94)
print("""
  ★ 看点②④⑥ —— 都是【同一个系统跟自己组合】:
     logistic×logistic(相关): 禁止模式 >0, 有结构!

  ★ 为什么? 因为两个坐标是【完全相关】的 —— 这种"相关性"就是约束:
     允许出现的只有 (0,0) 和 (1,1), (0,1)/(1,0) 被禁止 -> 结构!

  ★★ 而①③⑤ (独立的) -> 禁止模式 0, 纯随机:
     两个独立混沌变量合起来 = 更高维的随机数, 结构【一点没增加】

  ★★★ 所以你说的「多个奇异结构组合 -> 无穷结构」, 精确条件是:

     组合产生【相关性/约束】 -> 才有结构   ✅  (②④⑥)
     组合只是【并排放着】   -> 只是更多随机 ❌ (①③⑤)

  ★ 这正好对应你工作区里的 资产_多视角(multiview.py):
     "结构在视角间的关系里, 不在任何单个视角里" —— 一模一样!
""")
print(f"用时 {time.time()-t0:.2f}s")
