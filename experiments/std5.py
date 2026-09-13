# -*- coding: utf-8 -*-
import time, itertools, random
t0=time.time()
random.seed(1)
print("="*94)
print("★ 这台机器什么时候管用? 什么时候不管用?")
print("="*94)
print("""
  上一轮结果: 我手写的6个验证器, 5选1只挑对 31% (瞎猜20%) —— 基本无效.

  原因不是你, 也不是方法, 而是: 【验证器太弱, 给不出区分信号】

  ★ 所以「塔尖->腰部」这台机器有个精确的开关:
     转化率 = f(验证器强度)

     验证器强 (能真的判对错) -> ✅ 转化成功, 任务从塔尖搬到腰部
     验证器弱 (只会看表面)   -> ❌ 转化失败, 等于没搬
""")
print("="*94)
print("★ 三个档次的验证器, 转化率差多少? (用同一个生成器)")
print("="*94)
print()
# 任务: 找公式 f(x)=y
def make_task():
    a=random.randint(1,4); b=random.randint(0,9)
    xs=list(range(1,5))
    return a,b,[(x,a*x+b) for x in xs]
TASKS=[make_task() for _ in range(200)]

def gen_candidates(n=40):
    """生成器: 枚举候选公式"""
    return [(a,b) for a in range(1,6) for b in range(0,10)][:n]

GC=gen_candidates()
print(f"  生成器: 枚举 {len(GC)} 个候选公式 ax+b")
print(f"  任务: {len(TASKS)} 个「给定输入输出, 找公式」")
print()

# 三档验证器
def F(f): return lambda x: f[0]*x+f[1]
def v_weak(f,task):   # 弱: 只看输出范围对不对
    a,b,pts=task; g=F(f)
    return all(0<=g(x)<=100 for x,_ in pts)
def v_mid(f,task):    # 中: 只看1个数据点
    a,b,pts=task; g=F(f)
    return g(pts[0][0])==pts[0][1]
def v_strong(f,task): # 强: 全部数据点都对
    a,b,pts=task; g=F(f)
    return all(g(x)==y for x,y in pts)

print(f"  {'验证器':<28}{'挑对率':<14}{'说明'}")
print("  "+"-"*60)
for nm,v in [("弱 (只看输出范围)",v_weak),("中 (只看1个点)",v_mid),("强 (全部点都对)",v_strong)]:
    hit=0
    for task in TASKS:
        cands=[f for f in GC if v(f,task)]
        # 有多个合格品时, 取第一个
        if cands and cands[0]==(task[0],task[1]): hit+=1
        elif (task[0],task[1]) in cands:
            # 合格品里含正确解 -> 算"找到"但要再看纯度
            hit+=0.5
    print(f"  {nm:<28}{100*hit/len(TASKS):<14.1f}{''}")
print()
print("="*94)
print("★★ 决定性结论")
print("="*94)
print("""
  同一个生成器 (40个候选), 只换验证器:

     弱验证器 -> 挑不对 (候选池里混着一堆错的)
     强验证器 -> 100% 挑对 (而且能精确定位)

  ★★ 所以这台机器不是"一种新方法", 它是: 【把验证器做到够强】

  ★ 而"够强"的精确含义是:
     验证器能给出【和任务难点对齐】的信号

     算数题: "跑一遍看对不对"        -> 够强 ✅
     代码:   "跑单元测试"            -> 够强 ✅
     写诗:   "检查平仄押韵"          -> 只够搬"形式", 搬不动"美" ❌
     战略:   "复盘历史结果"          -> 只能事后, 不能事前 ❌

  ★ 所以你这台机器的真正名字, 和该做的唯一一件事:

     【验证器工厂】: 为每个领域的"塔尖任务", 找出一个够强的验证器

     验证器多强 -> 任务就能搬多远
     这不是算法问题, 是【领域知识问题】
""")
print(f"用时 {time.time()-t0:.2f}s")
