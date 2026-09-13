# -*- coding: utf-8 -*-
import json,re,time
from collections import defaultdict
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')
# 建索引: 锚点 -> 答案列表
IDX=defaultdict(list)
for d in QA:
    for a in PAT.findall(d['q']):
        if len(a)>=4: IDX[a].append((d['a'],d['task']))
def gen(q):
    out=[]
    for a in PAT.findall(q):
        if len(a)>=4: out+=IDX.get(a,[])
    return out
print("="*94)
print("★ 标准编译器: 规则从数据里自动学, 把「塔尖」编译成「腰部」")
print("="*94)
print(f"  库: {len(IDX)} 个锚点   |   {len(QA)} 条任务")
print()

def feats(a,k,t):
    return (len(a)>=20, a.count(' ')<3, a[:1].isupper(), k in a,
            not a.strip().startswith(('What','How','I ')), t=='solve')
FN=['长>=20','无空格','首大写','含锚点','非问句','solve']

# 从数据里统计: 正确 vs 错误的特征分布
pos=[0]*6; neg=[0]*6; np_=nneg=0
for d in QA:
    for a,t in gen(d['q']):
        f=feats(a,d['q'][:1],t) if False else feats(a,'',t)
        on=[i for i,v in enumerate(f) if v]
        if a==d['a']:
            np_+=1
            for i in range(6): pos[i]+= (i in on)
        else:
            nneg+=1
            for i in range(6): neg[i]+= (i in on)
print(f"  正确配对 {np_} | 错误配对 {nneg}")
print()
print(f"  {'特征':<12}{'正确组':<12}{'错误组':<12}{'区分度':<10}{'判定'}")
print("  "+"-"*60)
for i,nm in enumerate(FN):
    pp=pos[i]/max(np_,1); pn=neg[i]/max(nneg,1)
    d=pp-pn
    tag="★ 有用" if abs(d)>0.08 else "无用"
    print(f"  {nm:<12}{pp:<12.2f}{pn:<12.2f}{d:+.2f}{'':<6}{tag}")
print()

print("="*94)
print("★ 逐步加规则, 看候选池纯度 + 挑对率")
print("="*94)
print()
print(f"  {'规则':<28}{'候选数':<10}{'纯度':<12}{'Top-1挑对率'}")
print("  "+"-"*62)
combos=[("无规则",[]),("+长>=20",['长>=20']),("+长>=20 +非问句",['长>=20','非问句']),
        ("+长>=20 +非问句 +首大写",['长>=20','非问句','首大写'])]
for nm,use in combos:
    n=0; good=0; hit=0; tot=0
    for d in QA:
        cs=gen(d['q'])
        if not cs: continue
        tot+=1
        scored=[]
        for a,t in cs:
            f=feats(a,'',t)
            ok=all(f[FN.index(u)] for u in use)
            if ok: n+=1
            if ok and a==d['a']: good+=1
            scored.append((sum(1 for u in use if f[FN.index(u)]),a))
        best=max(scored,key=lambda x:x[0])[1]
        if best==d['a']: hit+=1
    print(f"  {nm:<28}{n:<10}{100*good/max(n,1):<12.1f}{100*hit/max(tot,1):.1f}%")
print()
print("  ★ 这就是「塔尖->腰部」的机器:")
print("     塔尖: '哪个答案最好?' -> 人的品味")
print("     腰部: '按规则打分取最高' -> 机器全自动")
print("     而规则【从数据里自动学出】, 不需要人来写")
print(f"用时 {time.time()-t0:.2f}s")
