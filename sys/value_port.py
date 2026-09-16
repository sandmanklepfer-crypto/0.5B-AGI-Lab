# -*- coding: utf-8 -*-
"""价值插口 — 显式、可切换、可审计的规范层"""
from itertools import permutations

BRIDGES={
 'utilitarian': {  # 功利主义: 最大化总福利
   'name':'功利主义','rule':'max Σutility',
   'score':lambda outcomes,weights: sum(o*w for o,w in zip(outcomes,weights))},
 'deontological':{ # 义务论: 禁止不可接受的行动
   'name':'义务论','rule':'禁越红线',
   'score':lambda outcomes,weights: -999 if outcomes.get('violates_redline') else sum(outcomes.get('vals',[0]))},
 'virtue':{        # 德性论: 最大化德性匹配度
   'name':'德性论','rule':'max 德性匹配',
   'score':lambda outcomes,weights: outcomes.get('virtue_score',0)},
}
def evaluate(options, bridge='utilitarian', weights=None):
    """用指定桥接公理评估选项 → 返回(排序, 理由链)"""
    B=BRIDGES[bridge]
    scored=[]
    for name,out in options.items():
        try: s=B['score'](out, weights or [1]*len(out.get('vals',[])))
        except Exception: s=-1e9
        scored.append((name,s))
    scored.sort(key=lambda x:-x[1])
    audit=[{'option':n,'score':round(s,4)} for n,s in scored]
    return scored, {'bridge':B['name'],'rule':B['rule'],'audit':audit}
def compare_bridges(options):
    """同一组选项, 不同公理下的排序差异 (价值多元性可视化)"""
    out={}
    for b in BRIDGES:
        sc,_=evaluate(options,b)
        out[BRIDGES[b]['name']]=[n for n,_ in sc]
    return out
def social_choice(votes, n, method='borda'):
    """聚合规则 (本身也是价值选择)"""
    import ops_social as S
    if method=='borda': return S.borda(votes,n)
    if method=='condorcet': return S.condorcet(votes,n)
    if method=='copeland': return S.copeland(votes,n)
    if method=='kemeny': return S.kemeny(votes,n)
    raise ValueError(method)
if __name__=='__main__':
    opts={'方案A':{'vals':[3,2,1]},'方案B':{'vals':[2,4,0]},'方案C':{'vals':[1,1,5]}}
    print("价值插口演示:")
    for b in BRIDGES:
        sc,au=evaluate(opts,b)
        print(f"  {au['bridge']}({au['rule']}): {' > '.join(n for n,_ in sc)}")
    print()
    print("  同一组选项的排序差异:", compare_bridges(opts))
    print("  → 这就是'价值多元性'的显式化(可切换, 可审计)")
