# -*- coding: utf-8 -*-
import json, re, time
from collections import Counter, defaultdict
from difflib import SequenceMatcher
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')
def anchors(q): return [x for x in PAT.findall(q) if len(x)>=4]
def skel(q):
    s=q
    for a in anchors(q): s=s.replace(a,'<A>')
    return s

print("="*90)
print("命名的真实价值: 层层抽象 (压缩链) + 泛化到新问法")
print("="*90)
print()

# ===== 压缩链 =====
qs=[d['q'] for d in QA]
sk=[skel(q) for q in qs]
print("【一】层层命名 = 层层压缩")
print(f"  {'层':<28}{'个数':<12}{'压缩比'}")
print("  "+"-"*54)
print(f"  {'第0层 原始问题':<28}{len(qs):<12}{'1x'}")
print(f"  {'第1层 命名: 问法骨架':<28}{len(set(sk)):<12}{f'{len(qs)/len(set(sk)):.1f}x'}")
# 第2层: 把骨架的"动作词"抽象掉 -> 元骨架
def meta(s):
    s=re.sub(r'[，。？?、,\s]+',' ',s)
    toks=s.split()
    # 只保留"动作核" (最长的2个词)
    toks=sorted(toks,key=lambda x:-len(x))[:2]
    return '|'.join(sorted(toks))
ms=[meta(s) for s in sk]
print(f"  {'第2层 命名: 元骨架':<28}{len(set(ms)):<12}{f'{len(qs)/len(set(ms)):.1f}x'}")
print()

# ===== 泛化: 新问法 =====
print("【二】泛化: 从「见过的问法」推出「没见过的问法」")
tpl=set(sk)
NEW=['项目 ZZZ-org/ZZZ 是做什么的？',
     '请介绍一下 ZZZ-org/ZZZ 这个项目',
     'ZZZ-org/ZZZ 有什么类似的参考吗？',
     '帮我总结 ZZZ-org/ZZZ 这个项目']
print(f"  {'新问法':<44}{'最像的模板':<10}{'相似度'}")
print("  "+"-"*76)
for q in NEW:
    if not anchors(q):
        continue
    s=skel(q)
    best=max(tpl,key=lambda t:SequenceMatcher(None,s,t).ratio())
    r=SequenceMatcher(None,s,best).ratio()
    mark="★ 命中" if r>0.6 else "⚠️ 新骨架"
    print(f"  {q[:42]:<44}{mark:<10}{r:.3f}")
print()

print("="*90)
print("【三】★ 真跑对话 (用上「命名」的系统)")
print("="*90)
print()
libA=defaultdict(Counter)
for d in QA:
    for a in anchors(d['q']): libA[a][d['a']]+=1
libA={k:v.most_common(1)[0][0] for k,v in libA.items()}

def answer(q):
    """系统: 命名路由 -> 抽锚点 -> 查库"""
    s=skel(q)
    # 命名层: 匹配最像的模板, 决定用哪个操作
    op='查库'
    if '复述' in q or '要点' in q: op='提取'
    if op=='提取':
        for sep in ['：',':','\n']:
            i=q.find(sep)
            if i>=0 and len(q)-i>40:
                key=q[i+1:i+41]
                for d in QA:
                    if key in d['q']: return '【提取+组合】'+d['a'][:60],op
    for a in anchors(q):
        if a in libA: return libA[a],op
    return None,op

for q in NEW:
    got,op=answer(q)
    print(f"  用户: {q}")
    if got:
        print(f"  → 用[{op}] 助手: {got[:78]}")
    else:
        print(f"  → 库中无此锚点, 需外部提供 (这就是唯一的'创造'时刻)")
    print()
print(f"  用时 {time.time()-t0:.2f}s")
