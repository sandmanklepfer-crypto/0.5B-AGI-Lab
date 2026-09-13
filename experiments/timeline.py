# -*- coding: utf-8 -*-
"""timeline.py — 把 v 系列按版本号排成时间序列, 看方法演化趋势"""
import glob,os,re,time
t0=time.time()
vf=[]
for f in glob.glob('/workspace/v*.py'):
    b=os.path.basename(f)
    m=re.match(r'v(\d+)',b)
    if m: vf.append((int(m.group(1)),f,b))
vf.sort()
print(f"v系列脚本 {len(vf)} 个, 版本号 v{vf[0][0]} ~ v{vf[-1][0]}")
print()
GROUPS={
 '生命/自持':['self','life','loop','soul','dyn','ssk'],
 '知识/挣取':['earn','knowledge','concept','riemann','truth','textpath'],
 '狩猎/攻击':['hunt','hijack','attack','poison','ctrl','gcg','hunter'],
 '剪枝/压缩':['prune','condense','shrink','prune','distill','gen_grains'],
 '自读/自我':['selfread','self_integrated','talking','naked','self_boundary','self_probe','selfemerge'],
 '组合/融合':['fused','fusion','chain','graph','lineage','compute_graph'],
 '符号/形式':['symbol','formal','separation','sep_diag'],
 '信息论/极限':['model_limit','lang_limit','reason_limit','resolution','surf'],
 '其他':[],
}
print("="*90)
print("★ 138个版本的方法演化 (按版本号分5段, 看每段在做什么)")
print("="*90)
print()
SEG=5; per=len(vf)//SEG+1
print(f"  {'版本段':<16}" + "".join(f"{g[:8]:<10}" for g in GROUPS))
print("  "+"-"*88)
for s in range(SEG):
    seg=vf[s*per:(s+1)*per]
    if not seg: continue
    cnt={g:0 for g in GROUPS}
    for v,f,b in seg:
        placed=False
        for g,kws in GROUPS.items():
            if g=='其他': continue
            if any(k in b for k in kws): cnt[g]+=1; placed=True; break
        if not placed: cnt['其他']+=1
    lab=f"v{seg[0][0]}-v{seg[-1][0]}"
    print(f"  {lab:<16}" + "".join(f"{cnt[g]:<10}" for g in GROUPS))
print()
print("="*90)
print("★ 关键读数")
print("="*90)
print()
# 各家族出现的时间跨度
print(f"  {'方法家族':<16}{'脚本数':<10}{'最早版本':<12}{'最晚版本':<12}{'跨度'}")
print("  "+"-"*66)
for g,kws in GROUPS.items():
    if g=='其他': continue
    hit=[v for v,f,b in vf if any(k in b for k in kws)]
    if hit:
        print(f"  {g:<16}{len(hit):<10}v{min(hit):<11}v{max(hit):<11}{max(hit)-min(hit)}")
print()
print("="*90)
print("★ 演化趋势: 后半段 vs 前半段")
print("="*90)
print()
mid=vf[len(vf)//2][0]
early={g:sum(1 for v,f,b in vf if v<mid and any(k in b for k in kws)) for g,kws in GROUPS.items() if g!='其他'}
late ={g:sum(1 for v,f,b in vf if v>=mid and any(k in b for k in kws)) for g,kws in GROUPS.items() if g!='其他'}
print(f"  {'家族':<16}{'前半(v<'+str(mid)+')':<16}{'后半':<12}{'趋势'}")
print("  "+"-"*56)
for g in GROUPS:
    if g=='其他': continue
    e,l=early.get(g,0),late.get(g,0)
    tr="↑ 加重" if l>e else ("↓ 减少" if l<e else "→ 持平")
    print(f"  {g:<16}{e:<16}{l:<12}{tr}")
print(f"  (分界点: v{mid})")
print()
print(f"用时 {time.time()-t0:.2f}s")
