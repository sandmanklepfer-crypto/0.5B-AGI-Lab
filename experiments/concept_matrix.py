# -*- coding: utf-8 -*-
"""concept_matrix.py — 把373个脚本建成「机制×脚本」矩阵, 做整体分析"""
import glob,os,re,time
t0=time.time()
files=[f for f in sorted(glob.glob('/workspace/*.py'))]
CONCEPT={
 '能量/代谢':   ['能量','energy','代谢','metab','ET A','饿','回血','ATP'],
 '疲劳/慢变量': ['疲劳','fatigue','慢变量','F=','adapt'],
 '门控':       ['门控','gate','调制','modulat','g='],
 '拓扑/图':     ['拓扑','topo','小世界','无标度','模块','graph','ER','BA'],
 '对称性':     ['对称','symmetric','非对称','anti','反对称'],
 '符号/离散':   ['符号','离散','token','量化','格点','K=','BPE','编码'],
 '验证/判定':   ['验证','判定','真值','可判','对错','L1','screen','check'],
 '搜索/穷举':   ['搜索','穷举','枚举','beam','搜索树','候选','采样','sample'],
 '混沌/临界':   ['混沌','临界','谱半径','lyapunov','λ','边缘','edge'],
 '种子/自指':   ['种子','seed','自指','self-ref','自读','selfread','锚'],
 '纸带/读写':   ['纸带','tape','读+写','读写','图灵'],
 '并行/接力':   ['并行','parallel','接力','relay','核','worker'],
 '退火/收敛':   ['退火','anneal','收敛','converge','降温','切空间'],
 '记忆/配额':   ['记忆','memory','配额','quota','池','pool','错题'],
 '压缩/剪枝':   ['压缩','prune','剪枝','condense','shrink','低秩','SVD'],
 '正交/可逆':   ['正交','可逆','保面积','辛','reversib','orthogonal'],
 '自催化/耗散': ['自催化','autocat','耗散','dissipat','衰减'],
 '奖惩/能量形': ['奖励','惩罚','奖惩','reward','扣分','罚'],
 '演化/变异':   ['演化','evolve','变异','mutation','遗传','GA'],
 '策展/蒸馏':   ['蒸馏','distill','策展','提炼','grains'],
}
def label(f):
    try: s=open(f,encoding='utf-8',errors='ignore').read(8000)
    except: return None
    v=[1 if any(k in s for k in kw) else 0 for kw in CONCEPT.values()]
    if sum(v)==0: return None
    return v
rows=[];names=[]
for f in files:
    v=label(f)
    if v: rows.append(v); names.append(os.path.basename(f))
print(f"脚本 {len(files)} 个, 有机制标签的 {len(rows)} 个")
print()
CN=list(CONCEPT)
print("="*88)
print("一、每个机制, 被多少个脚本用到")
print("="*88)
print()
freq=[sum(r[i] for r in rows) for i in range(len(CN))]
N=len(rows)
for nm,c in sorted(zip(CN,freq),key=lambda x:-x[1]):
    bar='#'*int(40*c/N)
    print(f"  {nm:<14}{c:>4}个 {100*c/N:>4.0f}%  {bar}")
print()
import numpy as np
M=np.array(rows,dtype=float)
print("="*88)
print("二、★ 哪些机制【总是成对出现】? (共现相关 top15)")
print("="*88)
print()
C=np.corrcoef(M.T)
pairs=[]
for i in range(len(CN)):
    for j in range(i+1,len(CN)):
        pairs.append((C[i,j],CN[i],CN[j]))
print(f"  {'机制A':<14}{'机制B':<14}{'相关系数'}")
print("  "+"-"*46)
for c,a,b in sorted(pairs,reverse=True)[:15]:
    print(f"  {a:<14}{b:<14}{c:+.2f}")
print()
print("  ★ 负相关最强的 (互斥机制):")
for c,a,b in sorted(pairs)[:5]:
    print(f"  {a:<14}{b:<14}{c:+.2f}")
print()
print("="*88)
print("三、★ 主成分: 373个脚本实际在探索几个维度?")
print("="*88)
print()
Mc=M-M.mean(0)
U,S,Vt=np.linalg.svd(Mc,full_matrices=False)
e=S**2; e=e/e.sum()
cum=np.cumsum(e)
for k in [1,2,3,4,5,8]:
    print(f"  前{k}个主成分 解释方差 {100*cum[k-1]:.1f}%")
print()
print("  ★ 前3个主成分的'载荷' (它们代表什么):")
for pc in range(3):
    ld=[(Vt[pc,i],CN[i]) for i in range(len(CN))]
    top=sorted(ld,key=lambda x:-abs(x[0]))[:5]
    print(f"    PC{pc+1}: " + ", ".join(f"{n}({v:+.2f})" for v,n in top))
print()
eig=0
print(f"  ★ 关键: 前5个主成分就解释了 {100*cum[4]:.0f}% 的方差")
print(f"  → 也就是说: 373个脚本, 其实只在探索【5个左右】的独立维度")
print()
print(f"用时 {time.time()-t0:.2f}s")
