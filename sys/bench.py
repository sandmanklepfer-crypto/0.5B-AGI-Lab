# -*- coding: utf-8 -*-
"""最终基准 — 全轴实测, 真实数字"""
import sys,time,re
sys.path.insert(0,'/workspace'); sys.path.insert(0,'/workspace/sys')
import core, ops_math as M, ops_social as S, lexicon as LX, verifiers as V
import form_v3 as F
t0=time.time()
def bar(a,n=20): f=int(a*n); return '█'*f+'░'*(n-f)
R={}
# ══ 轴1 数学 (20题) ══
MT=[('97是素数吗',True),('91是素数吗',False),('101是素数吗',True),
    ('gcd(48,180)',12),('gcd(1071,462)',21),('φ(100)',40),('φ(36)',12),
    ('C(10,3)',120),('C(20,5)',15504),('catalan(5)',42),('catalan(7)',429),
    ('5的阶乘',120),('10的阶乘',3628800),('perm(5,2)',20),
    ('360的因式分解',None),('fib(10)',55),('fib(20)',6765),
    ('37乘以23等于多少',851),('12加上30是多少',42),('100减去45是多少',55)]
ok=0;bad=[]
for q,e in MT:
    try:
        a=core.answer(q); r=a['result'] or {}
        vals=[v for v in r.values() if isinstance(v,(int,float))]
        g = bool(e is None and r) or bool(e in vals)
    except Exception: g=False
    ok+=g
    if not g: bad.append(q)
R['数学']=(ok,len(MT)); 
print(f"【轴1 数学】{ok}/{len(MT)} = {ok/len(MT)*100:5.1f}%  {bar(ok/len(MT))}")
if bad: print("     漏:",bad)
# ══ 轴2 数列 (12题) ══
SQ=[([1,4,9,16,25],36),([1,8,27,64,125],216),([2,4,8,16,32],64),([1,3,6,10,15],21),
    ([2,7,20,57,166],491),([1,1,2,3,5,8],13),([5,10,20,40,80],160),([1,4,10,22,46],94),
    ([2,3,5,7,11],13),([1,2,5,14,42],132),([3,12,27,48,75],108),([1,4,11,26,57],120)]
ok=0;bad=[]
for s,e in SQ:
    r,p=F.search_v2(s)
    g = (p==e) or (p is not None and abs(float(p)-e)<1e-6)
    ok+=g
    if not g: bad.append((s,e,p,r))
R['数列']=(ok,len(SQ))
print(f"【轴2 数列】{ok}/{len(SQ)} = {ok/len(SQ)*100:5.1f}%  {bar(ok/len(SQ))}")
if bad: print("     漏:",bad[:3])
# ══ 轴3 社科 (12题) ══
import numpy as np
ST=[('dominant',lambda: S.dominant(np.array([[3,0],[1,2]]))==[]),
    ('dominant2',lambda: S.dominant(np.array([[3,0],[5,1]]))==[1]),
    ('nash_pd',lambda: (1,1) in S.nash_pure(np.array([[-1,-3],[0,-2]]),np.array([[-1,0],[-3,-2]]))),
    ('nash_bos',lambda: len(S.nash_pure(np.array([[2,0],[0,1]]),np.array([[2,0],[0,1]])))==2),
    ('borda',lambda: S.borda([[0,1,2],[0,2,1],[1,0,2]],3)[1]==0),
    ('condorcet',lambda: S.condorcet([[0,1,2],[0,2,1],[1,0,2]],3)==0),
    ('copeland',lambda: S.copeland([[0,1,2],[0,2,1],[1,0,2]],3)[1]==0),
    ('ess',lambda: S.is_ess([[2,0],[0,2]],0)),
    ('knapsack',lambda: S.knapsack_01([2,3,4],[3,4,5],5)==7),
    ('infer_value',lambda: abs(S.auction_infer_value(20,5)-25)<1e-9),
    ('replicator',lambda: S.replicator([[2,0],[0,2]],[0.3,0.7])[1]>0.99),
    ('rubinstein',lambda: abs(S.rubinstein_share(0.5,0.5)-1/3)<1e-9)]
ok=0;bad=[]
for nm,fn in ST:
    try: g=bool(fn())
    except Exception as e: g=False
    ok+=g
    if not g: bad.append(nm)
R['社科']=(ok,len(ST))
print(f"【轴3 社科】{ok}/{len(ST)} = {ok/len(ST)*100:5.1f}%  {bar(ok/len(ST))}")
if bad: print("     漏:",bad)
# ══ 轴4 词典 ══
D=LX.load()
WT=['苹果','量子力学','人工智能','神经网络','数据','模型','算法','推理','学习','知识']
ok=sum(1 for w in WT if w in D)
R['词典']=(ok,len(WT))
print(f"【轴4 词典】{ok}/{len(WT)} = {ok/len(WT)*100:5.1f}%  {bar(ok/len(WT))}  (总{len(D):,}词)")
# ══ 轴5 验证器 (负例=应拒绝) ══
VT=[('L1算术',V.v_arith("37*23",851)[0] is True),
    ('L1算术(错)',V.v_arith("37*23",999)[0] is False),
    ('L1素数',V.v_prime(97,True)[0] is True),
    ('L2类型(对)',V.v_types(['r','v','n'],{'r':'R','v':'V','n':'N'})[0] is True),
    ('L2类型(错)',V.v_types(['v','v','n'],{'v':'V','n':'N'})[0] is False),
    ('L4重复',V.v_repetition('我我我我我我')[0] is False),
    ('L3矛盾',V.v_consistency('我不喜欢苹果',['我喜欢苹果'])[0] is False),
    ('L3无矛盾',V.v_consistency('我喜欢苹果',['我喜欢苹果'])[0] is True)]
ok=sum(1 for _,g in VT if g)
R['验证器']=(ok,len(VT))
print(f"【轴5 验证器】{ok}/{len(VT)} = {ok/len(VT)*100:5.1f}%  {bar(ok/len(VT))}")
for nm,g in VT:
    if not g: print("     漏:",nm)
# ══ 总账 ══
print()
tot=sum(v[0] for v in R.values()); n=sum(v[1] for v in R.values())
print("="*60)
for k,(a,b) in R.items(): print(f"  {k:<8}{a:>3}/{b:<3} = {a/b*100:5.1f}%  {bar(a/b,16)}")
print(f"  {'合计':<8}{tot:>3}/{n:<3} = {tot/n*100:5.1f}%")
print(f"  总耗时 {time.time()-t0:.2f}s")
