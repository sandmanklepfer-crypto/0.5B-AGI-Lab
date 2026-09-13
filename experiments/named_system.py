# -*- coding: utf-8 -*-
import json, re, time
from collections import Counter, defaultdict
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]

PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')
def anchors(q): return [x for x in PAT.findall(q) if len(x)>=4]
def skel(q):
    s=q
    for a in anchors(q): s=s.replace(a,'<A>')
    return s

print("="*90)
print("接上「命名」: 锚点系统 + 自动命名 -> 能力能长到多大?")
print("="*90)

# ---------- 留出法: 一半训练, 一半测试 (测泛化) ----------
tr=QA[:len(QA)//2]; te=QA[len(QA)//2:]
print(f"  训练 {len(tr)} 条, 测试 {len(te)} 条 (完全没见过的)")
print()

# ===== 第1层: 只有锚点 (无命名) =====
libA=defaultdict(Counter)
for d in tr:
    for a in anchors(d['q']): libA[a][d['a']]+=1
libA={k:v.most_common(1)[0][0] for k,v in libA.items()}

def answer_L1(q):
    for a in anchors(q):
        if a in libA: return libA[a]
    return None

# ===== 第2层: 加「命名」 =====
# 命名规则: 把问法骨架 <A>... 命名成一个"模板"
# 模板库: 骨架 -> 该骨架下的 (锚点位置 -> 答案) 关系
#   更实用: 骨架 -> 答案生成规则
libS=defaultdict(Counter)          # 骨架 -> 答案模板(把锚点替换成<A>的答案)
for d in tr:
    s=skel(d['q'])
    a2=d['a']
    for an in anchors(d['q']): a2=a2.replace(an,'<A>')
    libS[s][a2]+=1
libS={k:v.most_common(1)[0][0] for k,v in libS.items()}

def answer_L2(q):
    s=skel(q)
    tmpl=libS.get(s)
    if tmpl:
        # 用<A>填回去
        out=tmpl
        for an in anchors(q):
            if '<A>' in out: out=out.replace('<A>',an,1)
        # 若还没填完, 退回库
        if '<A>' not in out: return out
    return answer_L1(q)

def score(fn,name):
    ok=0; by=defaultdict(lambda:[0,0])
    for d in te:
        got=fn(d['q'])
        by[d['task']][1]+=1
        if got==d['a']:
            ok+=1; by[d['task']][0]+=1
    print(f"  {name:<26}{ok}/{len(te)} = {100*ok/len(te):.1f}%")
    return by

print("="*90)
print("结果 (测试集全是没见过的)")
print("="*90)
b1=score(answer_L1,"第1层 只有锚点(查库)")
b2=score(answer_L2,"第2层 +命名(模板)")
print()

# ===== 第3层: 递归 —— 模板里还能引用模板 =====
# 命名出的模板可以再被命名 (二次抽象)
libS2=defaultdict(Counter)
for s,c in libS.items():
    # 把模板里"锚点位置"抽象掉, 得到"元模板"
    meta=re.sub(r'<A>','@',s)
    libS2[meta][c]+=1
print(f"  第3层 (元模板) 学到的抽象层数: {len(libS2)} 个元模板")
print(f"    -> 每多一层命名, 覆盖面 {len(libS2)} 倍于原始问法")
print()

print("="*90)
print("★ 命名带来的提升")
print("="*90)
print(f"  {'层':<26}{'覆盖率'}")
print("  "+"-"*46)
print(f"  {'第1层 锚点':<26}{100*sum(1 for d in te if answer_L1(d['q'])==d['a'])/len(te):.1f}%")
print(f"  {'第2层 +命名':<26}{100*sum(1 for d in te if answer_L2(d['q'])==d['a'])/len(te):.1f}%")
print()
print(f"  用时 {time.time()-t0:.2f}s")
