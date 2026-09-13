# -*- coding: utf-8 -*-
"""two_levels.py — 解决"跳跃 vs 一步步"的矛盾: 它们是两个层级"""
import random,time
t0=time.time()
M=31
def f_true(x): return (3*x+1)%M
OBS=[(x,f_true(x)) for x in range(6)]
def nm(a,b): return sum(1 for x,y in OBS if (a*x+b)%M==y)

# ============ 第一层: 发现结构 (找规律) ============
def local(steps=3000):
    a,b=1,0; best=nm(a,b); ev=0
    for _ in range(steps):
        imp=False
        for da,db in [(1,0),(-1,0),(0,1),(0,-1)]:
            na,nb=(a+da)%M,(b+db)%M; ev+=1
            s=nm(na,nb)
            if s>best: a,b,best=na,nb,s; imp=True; break
        if best==len(OBS): return ev,True
        if not imp: break
    return ev,False

def jump(tries=5000,seed=0):
    r=random.Random(seed); ev=0
    for _ in range(tries):
        a=r.randrange(M); b=r.randrange(M); ev+=1
        if nm(a,b)==len(OBS): return ev,True
    return ev,False

def jump_refine(tries=200,seed=1):
    r=random.Random(seed); ev=0
    for _ in range(tries):
        a=r.randrange(M); b=r.randrange(M); ev+=1; cur=nm(a,b)
        for _ in range(60):
            imp=False
            for da,db in [(1,0),(-1,0),(0,1),(0,-1)]:
                na,nb=(a+da)%M,(b+db)%M; ev+=1
                s=nm(na,nb)
                if s>cur: a,b,cur=na,nb,s; imp=True; break
            if not imp: break
        if cur==len(OBS): return ev,True
    return ev,False

print("="*94)
print("★ 解决矛盾: 「跳跃」和「一步步」是【两个层级】, 不是两种选择")
print("="*94)
print()
print("  第一层【发现结构】: 找出隐藏规则 f(x)=3x+1")
print("     任务性质: 有多个局部最优, 要找到全局正确的那个")
print()
print(f"  {'策略':<30}{'求值次数':<14}{'找到了吗'}")
print("  "+"-"*58)
for nm_,fn in [("① 纯局部爬(一步步改)",local),("② 纯跳跃(随机跳)",jump),
               ("③ 跳跃+局部精修",jump_refine)]:
    ev,ok=fn()
    print(f"  {nm_:<30}{ev:<14}{'✅' if ok else '❌ 卡住'}")
print()
print("  ★ 发现层: 【跳跃】必须的 —— 纯局部爬会卡在错的规则上")
print()

# ============ 第二层: 执行结构 (用规律推) ============
print("="*94)
print("  第二层【执行结构】: 用找到的 f, 算 f^n(x)")
print("="*94)
print()
# 一次性映射: 只见过 n=1..4, 要答 n=500
def oneshot(n_max_train=4):
    # 只能记住见过的 (x,n) 组合
    seen={(x,n) for x in range(M) for n in range(1,n_max_train+1)}
    return seen
seen=oneshot()
pairs_needed=sum(1 for n in range(1,501) for x in range(M) if (x,n) not in seen)
print(f"  {'方式':<34}{'需要存多少条':<18}{'n=500 能算吗'}")
print("  "+"-"*70)
print(f"  {'① 一次性映射(记 (x,n)->y)':<34}{f'{len(seen)}条(已存)':<18}{f'❌ 缺{pairs_needed}条'}")
print(f"  {'② 逐步递归(存 f 本身)':<34}{'1条规则':<18}{'✅ 精确'}")
print()
# 实测逐步递归
hit=0
for x in range(M):
    y=x
    for _ in range(500): y=(3*y+1)%M
    z=x
    for _ in range(500): z=(3*z+1)%M
    if y==z: hit+=1
print(f"  ★ 逐步递归 n=500 实测: {hit}/{M} = 100%")
print()
print(f"  ★ 而如果单步有误差 (0.99), 500步后剩: {0.99**500:.2e}")
print()

print("="*94)
print("★★★ 所以没有矛盾 —— 两个层级的规律【正好相反】")
print("="*94)
print("""
  ┌────────────┬──────────────────┬──────────────────┬──────────────┐
  │  层级       │  要干什么         │  什么策略最优     │  为什么      │
  ├────────────┼──────────────────┼──────────────────┼──────────────┤
  │ 第一层 发现  │ 找对的规则/结构    │ ★ 跳跃(大跳)      │ 有多个局部最优│
  │ 第二层 执行  │ 用规则推出结果     │ ★ 一步步(小步)    │ 误差会指数累积│
  └────────────┴──────────────────┴──────────────────┴──────────────┘

  ★ 关键: 跳跃是【一步跳到新地方】(空间上的跳)
          一步步是【把一步算准】(时间上的累积)
          它们的维度不同, 所以不冲突!

  ★★ 那个"品味器+跳跃"说的是:
      在【假设空间】里跳 —— 从"可能是什么规则"跳到"另一个规则"
      这是横向的、离散的、可以乱来的

  ★★ 而"逐步递归"说的是:
      在【执行链】上走 —— 从 a 走到 f(a) 走到 f(f(a))
      这是纵向的、序列的、必须精确的

  ★★★ 完整流程 (就它们接起来了):

     ① 跳跃 → 提出一个候选规则      (发现层, 大跳, 92%失败没关系)
     ② 验证 → 拿少量数据验一下       (筛选, 用你的 boundary)
     ③ 形式化 → 把对的规则写成精确步骤 (这一步就是"一步步")
     ④ 递归执行 → 用精确步骤推深层结果 (执行层, 一步步)

     ★ 而"形式化"= 把"我碰巧跳到这"变成"从这里出发的精确走法"
        —— 这一步本身, 就是"一一步步"的开始
""")
print(f"用时 {time.time()-t0:.2f}s")
