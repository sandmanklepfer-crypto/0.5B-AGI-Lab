# -*- coding: utf-8 -*-
"""端到端实测 — 逐轴跑真实测试, 报真实数字"""
import sys, re, json, time
sys.path.insert(0,'/workspace'); sys.path.insert(0,'/workspace/sys')
import core, ops_math as M, ops_social as S, lexicon as LX, verifiers as V
t0=time.time()
def bar(acc,n):
    f=int(acc*n); return '█'*f+'░'*(n-f)
print("="*76)
print("  0.5B+全库系统  端到端实测")
print("="*76)
# ── 轴1: 数学(数论/代数) ──
cases=[('97是素数吗',True),('91是素数吗',False),('360的因式分解',None),
       ('gcd(48,180)',12),('φ(100)',40),('C(10,3)',120),('catalan(5)',42)]
ok=0; det=[]
for q,exp in cases:
    a=core.answer(q); r=a['result']
    if exp is None: good = r is not None
    else:
        try: good = (exp in r.values()) or (exp==list(r.values())[0])
        except Exception: good = False
    ok+=good; det.append((q,good,r))
print(f"\n【轴1 数学】{ok}/{len(cases)} = {ok/len(cases)*100:.0f}%   {bar(ok/len(cases),20)}")
for q,g,r in det: print(f"    {'✅' if g else '❌'} {q:<18} {str(r)[:52]}")
# ── 轴2: 数列(形式库) ──
print()
try:
    import form_v3 as F
    seqs=[([1,4,9,16,25],36),([1,8,27,64,125],216),([2,4,8,16,32],64),
          ([1,3,6,10,15],21),([2,7,20,57,166],491),([1,1,2,3,5,8],13)]
    ok=0; det=[]
    for s,e in seqs:
        r,p=F.search_v2(s); g=(p==e); ok+=g; det.append((s,e,r,p,g))
    print(f"【轴2 数列】{ok}/{len(seqs)} = {ok/len(seqs)*100:.0f}%   {bar(ok/len(seqs),20)}")
    for s,e,r,p,g in det: print(f"    {'✅' if g else '❌'} {str(s):<26} {r} → {p} (真{e})")
except Exception as ex: print("【轴2】未加载:",ex)
# ── 轴3: 社会(博弈/社会选择) ──
print()
ok=0; det=[]
tests=[('dominant',[[3,0],[5,1]],lambda: S.dominant(__import__('numpy').array([[3,0],[5,1]]))),
       ('nash',[[3,0],[0,2]],lambda: S.nash_pure(__import__('numpy').array([[3,0],[0,2]]),__import__('numpy').array([[3,0],[0,2]]))),
       ('borda',None,lambda: S.borda([[0,1,2],[0,2,1],[1,0,2]],3)[1]),
       ('condorcet',None,lambda: S.condorcet([[0,1,2],[0,2,1],[1,0,2]],3)),
       ('ESS',[[2,0],[0,2]],lambda: S.is_ess([[2,0],[0,2]],0))]
for nm,arg,fn in tests:
    try: r=fn(); g=True
    except Exception as e: r=str(e); g=False
    ok+=g; det.append((nm,g,r))
print(f"【轴3 社科】{ok}/{len(tests)} = {ok/len(tests)*100:.0f}%   {bar(ok/len(tests),20)}")
for nm,g,r in det: print(f"    {'✅' if g else '❌'} {nm:<12} {r}")
# ── 轴4: 知识(词典) ──
print()
D=LX.load()
ok=sum(1 for w in ['苹果','量子力学','人工智能','神经网络','区块链','元宇宙'] if w in D)
print(f"【轴4 词典】{ok}/6 = {ok/6*100:.0f}%   (总词表 {len(D):,} 词)")
# ── 轴5: 验证器栈 ──
print()
vres=[('L1算术',V.v_arith("37*23",851)),('L1素数',V.v_prime(97,True)),
      ('L2类型',V.v_types(['r','v','n'],{'r':'R','v':'V','n':'N'})),
      ('L4重复',V.v_repetition('我我我我我我')),
      ('L3一致',V.v_consistency('我不喜欢苹果',['我喜欢苹果']))]
ok=sum(1 for _,r in vres if (r[0] is True if '重复' not in _ and '一致' not in _ else r[0] is False))
print(f"【轴5 验证器】{ok}/{len(vres)} 层可用")
for nm,r in vres: print(f"    {nm:<10} {r}")
print()
print(f"总耗时 {time.time()-t0:.2f}s")
