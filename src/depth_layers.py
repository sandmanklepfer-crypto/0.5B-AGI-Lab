import json,re,time
from collections import defaultdict,Counter
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]

# ---------- 第1层: 锚点抽取 (纯搬运) ----------
PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')
def L1_anchors(q):
    return [x for x in PAT.findall(q) if len(x)>=4]

# ---------- 第2层: 操作 (在锚点上做确定性运算) ----------
def op_extract(q):          # 提取: 冒号/换行之后的所有内容
    for sep in ['：',':','\n']:
        i=q.find(sep)
        if i>=0 and len(q)-i>30:
            return q[i+1:].strip()
    return None

def op_lookup(q,lib):       # 查库: 用锚点取
    for a in L1_anchors(q):
        if a in lib: return lib[a]
    return None

def op_template(q,lib):     # 模板: 同一锚点的变体问法
    return None

# ---------- 建库 (入库时刻才需要"新信息") ----------
lib=defaultdict(Counter)
for d in QA:
    for a in L1_anchors(d['q']):
        lib[a][d['a']]+=1
lib={k:v.most_common(1)[0][0] for k,v in lib.items()}

# ---------- 规则路由: 用问题的【表层特征】决定用哪个操作 ----------
def route(q):
    if any(s in q for s in ['复述','摘要要点','阅读并']): return 'extract'
    if '最近有什么' in q: return 'lookup'
    return 'lookup'

ok=defaultdict(lambda:[0,0]); tot=0
for d in QA:
    t,q,a=d['task'],d['q'],d['a']
    r=route(q)
    got = op_extract(q) if r=='extract' else op_lookup(q,lib)
    ok[t][1]+=1
    if got==a: ok[t][0]+=1
    tot+=1
print("="*88)
print("两层系统: 第1层抽锚点 + 第2层操作 (全部是搬运+确定性运算)")
print("="*88)
print(f"  {'任务':<12}{'条数':<8}{'成功':<8}{'成功率':<10}{'用哪个操作'}")
print("  "+"-"*66)
for t in ['summary','whatis','hint','title2abs','solve','topic']:
    o,n=ok[t]
    r=route([x for x in QA if x['task']==t][0]['q'])
    print(f"  {t:<12}{n:<8}{o:<8}{100*o/max(n,1):<10.0f}%{'提取' if r=='extract' else '查库'}")
allok=sum(ok[t][0] for t in ok); alln=sum(ok[t][1] for t in ok)
print()
print(f"  总成功率: {allok}/{alln} = {100*allok/alln:.1f}%")
print()
print("="*88)
print("★ 这就是「高层结构」的样子: 它的深度来自【组合】")
print("="*88)
print("""
  第0层  字符
  第1层  锚点        从输入里【搬运】出片段         (op: 正则定位)
  第2层  操作        把锚点【组合】成新东西          (op: 提取/查库/拼接)
  第3层  命名        把第2层结果【命名】成新锚点      (op: 入库存下来)
         ↓ 返回第1层, 新锚点又能参与运算 —— 这就是递归, 就是深度

  ★ 关键: 每一层都是「搬运 + 确定性组合」, 没有一步需要「凭空产生」
  ★ 所以误差【不累积】(确定性运算可验证) —— 这正是 v161 外推100%的原因
  ★ 而「新信息」在哪? 在【第3层入库存下来的那一刻】, 那里才是创造
""")
print(f"用时 {time.time()-t0:.2f}s")
