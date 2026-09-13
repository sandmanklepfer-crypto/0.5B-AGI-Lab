# -*- coding: utf-8 -*-
import json,re,time
from collections import defaultdict
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')
print("="*94)
print("★ 真任务: 候选来自【不同锚点】, 必须挑对 (这才是「塔尖」)")
print("="*94)
print()

# 构造真实的选择任务: 给一个问题, 从库里抽 5 个【不同】候选 (1对4错)
import random
random.seed(0)
AN=list(set(a for d in QA for a in PAT.findall(d['q']) if len(a)>=4))
IDX=defaultdict(list)
for d in QA:
    for a in PAT.findall(d['q']):
        if len(a)>=4: IDX[a].append(d['a'])

TASKS=[]
for d in QA:
    ks=[a for a in PAT.findall(d['q']) if len(a)>=4 and a in IDX]
    if not ks: continue
    right=IDX[ks[0]][0]
    wrong=[]
    for _ in range(4):
        w=IDX[random.choice(AN)][0]
        if w!=right: wrong.append(w)
    if len(wrong)==4:
        TASKS.append((d['q'], ks[0], right, wrong))
print(f"  构造了 {len(TASKS)} 个「5选1」选择任务 (1对4错)")
print()

def gen_verifiers():
    """候选的'判定器' (从数据里能想到的客观检查)"""
    return [
      ("答案含问题里的锚点",  lambda a,q,k: k in a or k.replace('/',' ') in a),
      ("答案长度>=30",      lambda a,q,k: len(a)>=30),
      ("答案不是问题本身",    lambda a,q,k: a.strip()!=q.strip()),
      ("答案不是问句",       lambda a,q,k: not a.strip().startswith(('What','How','I want','请','我'))),
      ("答案含英文词",       lambda a,q,k: bool(re.search(r'[A-Za-z]{4,}',a))),
      ("答案不含'？'",       lambda a,q,k: '？' not in a and '?' not in a),
    ]

V=gen_verifiers()
print("="*94)
print("★ 逐个验证器, 单独能不能挑出正确答案?")
print("="*94)
print()
print(f"  {'验证器':<24}{'挑对率':<14}{'对正确解通过率':<18}{'对错误解通过率'}")
print("  "+"-"*74)
for nm,fn in V:
    hit=0; tp=0; fp=0; n=0
    for q,k,right,wrong in TASKS:
        n+=1
        if fn(right,q,k): tp+=1
        for w in wrong:
            if fn(w,q,k): fp+=1
        # 组合打分选最高
        sc=[sum(1 for _,f in V if f(x,q,k)) for x in [right]+wrong]
        if sc[0]==max(sc) and sc[0]>max(sc[1:]): hit+=1
    print(f"  {nm:<24}{100*hit/n:<14.1f}{tp/n:<18.2f}{fp/(4*n):.2f}")
print()

print("="*94)
print("★ 组合所有验证器 (投票) vs 单个")
print("="*94)
print()
for topn in range(1,len(V)+1):
    hit=0
    for q,k,right,wrong in TASKS:
        sc=[]
        for x in [right]+wrong:
            sc.append(sum(1 for _,f in V[:topn] if f(x,q,k)))
        if sc[0]==max(sc) and sc[0]>max(sc[1:]): hit+=1
    if topn<=3 or topn==len(V):
        print(f"  用前 {topn} 个验证器投票 -> 挑对率 {100*hit/len(TASKS):.1f}%")
print()
print("  ★ 这就是「塔尖->腰部」: 5选1 靠【投票筛】, 不靠【品味】")
print(f"  用时 {time.time()-t0:.2f}s")
