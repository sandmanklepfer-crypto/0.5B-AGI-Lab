# -*- coding: utf-8 -*-
import json,re,time
from collections import Counter
t0=time.time()
QA=[json.loads(l) for l in open('/workspace/clean_train.jsonl',encoding='utf-8')]
print("="*94)
print("★ 标准编译器: 迭代地把「塔尖任务」编译成「腰部任务」")
print("="*94)
print()
print("  任务: 「怎么回答这个问题?」  <- 塔尖 (要选最好的答法)")
print("  目标: 编译成「生成候选 + 验证筛」    <- 腰部")
print()

PAT=re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')

def gen_candidates(q, pool):
    """候选生成器: 从池子里找所有'沾边'的答案"""
    keys=set()
    for a in PAT.findall(q):
        if len(a)>=4: keys.add(a)
    for w in re.findall(r'[\u4e00-\u9fff]{2,}', q):
        keys.add(w)
    out=[]
    for d in pool:
        for k in keys:
            if k in d['q']:
                out.append(d['a']); break
    return out

# ============ 迭代加严: 每一轮人给一条反馈, 规则变严 ============
# 训练集学规则, 测试集验证 (真实泛化测试)
half=len(QA)//2
TRAIN, TEST = QA[:half], QA[half:]
print(f"  训练 {len(TRAIN)} 条 (用来挖掘标准) | 测试 {len(TEST)} 条 (验证泛化)")
print()

# 第0轮标准: 只要沾边
def rule0(c, q):
    return True
# 第1轮: 答案不能是问题本身 (人反馈: "它在复读问题")
def rule1(c, q):
    return c.strip() != q.strip() and c[:20] not in q
# 第2轮: 答案要够长 (人反馈: "太短的没信息")
def rule2(c, q):
    return rule1(c,q) and len(c) >= 20
# 第3轮: 答案要包含问题里的锚点 (人反馈: "答非所问")
def rule3(c, q):
    ks=[a for a in PAT.findall(q) if len(a)>=4]
    if not ks: return rule2(c,q)
    return rule2(c,q) and any(k in c or k.replace('/',' ') in c for k in ks)
# 第4轮: 答案开头不能是问句 (人反馈: "它把问题还回来了")
def rule4(c, q):
    return rule3(c,q) and not c.strip().startswith(('What','How','I want','请','我'))

RULES=[("第0轮 只要沾边",rule0),("第1轮 +不能复读问题",rule1),
       ("第2轮 +长度>=20",rule2),("第3轮 +含锚点",rule3),
       ("第4轮 +不是问句",rule4)]

print("="*94)
print("★ 迭代过程 (每一轮 = 人给一条反馈 -> 加严标准)")
print("="*94)
print()
print(f"  {'标准':<24}{'平均候选数':<14}{'合格率':<12}{'命中率(测试集)'}")
print("  "+"-"*70)
best=None
for nm,rule in RULES:
    ncand=0; nok=0; hit=0; tot=0
    for d in TEST:
        cands=gen_candidates(d['q'], TRAIN)
        ncand+=len(cands)
        good=[c for c in cands if rule(c,d['q'])]
        nok+=len(good)
        tot+=1
        if d['a'] in good: hit+=1
    mc=ncand/tot; mr=nok/max(ncand,1)
    print(f"  {nm:<24}{mc:<14.1f}{mr:<12.2f}{100*hit/tot:.1f}%")
    if best is None or hit>best[1]: best=(nm,hit)
print()
print("  ★ 关键: 标准越严, 候选越少, 但【命中率不一定降】—— 因为筛掉的多是噪声")
print(f"  ★ 最优标准: {best[0]}  (命中 {best[1]}/{len(TEST)})")
print()

# ============ 决定性: 这台机器的"产物"是什么 ============
print("="*94)
print("★ 这台机器的产物: 一个「可复用的判定器」")
print("="*94)
print("""
  输入: 一个问题 + 一堆候选
  输出: 哪些候选合格

  ★ 它把"看哪个答案好"(人的活) 变成了 "跑一遍规则"(机器的活)
  ★ 而且规则【一旦写下, 永久有效, 零成本复用】

  ★ 这就是「塔尖 -> 腰部」的机器:
     塔尖任务: 靠人的【判断力】每次重新选
     腰部任务: 靠人的【判断力】写一次规则, 之后机器自动做
""")
print()
print("="*94)
print("★ 但有个铁律: 每加一条规则, 都有代价")
print("="*94)
print(f"  {'规则':<24}{'筛掉的候选':<16}{'漏掉的好答案(假阴性)'}")
print("  "+"-"*64)
for i in range(1,len(RULES)):
    nm=4
print("""  规则         好处                    坏处
  ---------------------------------------------------------
  越严         噪声越少                可能误杀正确解(假阴性)
  越松         不漏掉正确解            噪声多, 等于没筛

  ★ 所以存在一个【最优严格度】, 而且它取决于:
     生成器的质量 (生成得好, 可以筛得松)
     错误的代价   (错一次很贵, 就要筛得严)
""")
print(f"用时 {time.time()-t0:.2f}s")
