# -*- coding: utf-8 -*-
"""struct2task.py — 结构叠加 能不能转成【任务能力】?
   设计: 用相关混沌构造"语法", 任务是【预测下一个符号】(需要真懂结构)
"""
import math,random,time
from collections import Counter,defaultdict
t0=time.time()
random.seed(1)
N=60000

def logi(N,seed):
    s=[]; x=0.1+0.3*random.Random(seed).random()
    for _ in range(N):
        x=4*x*(1-x); s.append(1 if x<0.5 else 0)
    return s

# ---------- 造 4 种"世界", 结构强度递增 ----------
def w_rand(N):            # 世界0: 纯随机 (无结构)
    return [random.randint(0,1) for _ in range(N)]
def w_golden(N):          # 世界1: 禁 '11'
    s=[];st=0
    for _ in range(N):
        s.append(st); st = random.randint(0,1) if st==0 else 0
    return s
def w_pair(N):            # 世界2: 两坐标相关 (结构在关系里)
    a=logi(N,1); return [2*a[i]+a[i] for i in range(N)]
def w_tri(N):             # 世界3: 三坐标相关 + 禁11
    a=w_golden(N); return [4*a[i]+2*a[i]+a[i] for i in range(N)]

WORLDS=[("世界0 纯随机(无结构)",w_rand,2),
        ("世界1 禁11(浅结构)",w_golden,2),
        ("世界2 双坐标相关",w_pair,4),
        ("世界3 三坐标相关+禁11",w_tri,8)]

def acc(seq,al,order=3):
    """任务: 看前order个符号, 预测下一个. 训练80%测20%"""
    tab=defaultdict(Counter)
    cut=int(len(seq)*0.8)
    for i in range(order,cut):
        tab[tuple(seq[i-order:i])][seq[i]]+=1
    if not tab: return 0,0
    hit=0;tot=0
    for i in range(cut,len(seq)):
        k=tuple(seq[i-order:i]); c=tab.get(k)
        tot+=1
        if c:
            if c.most_common(1)[0][0]==seq[i]: hit+=1
        else:
            # 没见过: 猜最多的
            pass
    return hit/tot, len(tab)

print("="*94)
print("★ 结构强度 -> 任务能力: 能不能转成「预测下一个符号」?")
print("="*94)
print()
print(f"  {'世界':<26}{'熵':<9}{'禁止2字':<11}{'见过的表大小':<15}{'预测准确率':<12}{'随机'}")
print("  "+"-"*92)
for nm,fn,al in WORLDS:
    s=fn(N)
    c=Counter(tuple(s[i:i+2]) for i in range(len(s)-1))
    h=-sum((v/len(s))*math.log2(v/len(s)+1e-12) for v in c.values())
    f2=al*al-len(set(tuple(s[i:i+2]) for i in range(len(s)-1)))
    a,ts=acc(s,al,3)
    print(f"  {nm:<26}{h:<9.3f}{f2:<11}{ts:<15}{a:<12.3f}{1/al:.3f}")
print()
print("="*94)
print("★★ 关键: 结构能不能【外推到没见过的上下文】?")
print("="*94)
print()
print("  做法: 只训练【部分上下文】, 测【剩下的】(真外推)")
print()
print(f"  {'世界':<26}{'训练的上下文':<16}{'测试准确率':<14}{'说明'}")
print("  "+"-"*80)
for nm,fn,al in WORLDS:
    s=fn(N)
    # 只用一半的上下文类型训练
    tab=defaultdict(Counter)
    keys=set()
    for i in range(3,len(s)):
        keys.add(tuple(s[i-3:i]))
    keys=sorted(keys)
    train_keys=set(keys[:len(keys)//2])
    for i in range(3,len(s)):
        k=tuple(s[i-3:i])
        if k in train_keys: tab[k][s[i]]+=1
    hit=0;tot=0
    for i in range(3,len(s)):
        k=tuple(s[i-3:i])
        if k in train_keys: continue
        tot+=1
        if tab and False: pass
    # 外推: 对没见过的上下文, 用"最短匹配"猜测
    def predict(k):
        for L in range(2,0,-1):
            c=tab.get(k[-L:]) if False else None
        # 退回到 2 阶
        c2=defaultdict(Counter)
        for i in range(3,len(s)):
            kk=tuple(s[i-3:i])
            if kk in train_keys: c2[kk[-2:]][s[i]]+=1
        c=c2.get(k[-2:])
        return c.most_common(1)[0][0] if c else random.randint(0,1)
    hit=0;tot=0
    for i in range(3,len(s)):
        k=tuple(s[i-3:i])
        if k in train_keys: continue
        tot+=1
        if predict(k)==s[i]: hit+=1
    print(f"  {nm:<26}{f'{len(train_keys)}/{len(keys)}':<16}{100*hit/max(tot,1):<14.1f}%{'★' if hit/max(tot,1)>0.6 else ''}")
print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  三个数字要分别看:

  ① 结构强度 (禁止模式数):     世界0=0, 世界1=1, 世界2/3 更多
  ② 表大小 (需要的样本):        结构越强, 表越小 (泛化越强)
  ③ 预测准确率:                 结构越强, 越准

  ★★ 关键判据: 【结构 -> 能力】能不能转?
     如果能: 结构强的世界, 预测准确率应该明显更高
     如果不能: 结构只是"好看", 对任务没用
""")
print(f"用时 {time.time()-t0:.2f}s")
