# -*- coding: utf-8 -*-
import random, math, time
t0=time.time()
random.seed(7)
print("="*94)
print("★ 闭环流水线实测: 跳跃器 -> 形式化器 -> 推广器")
print("="*94)
print()

# ============ 地形: 5 个"领域", 各有隐蔽的全局最高峰 ============
def make_field(seed):
    r=random.Random(seed)
    peaks=[]
    for i in range(5):
        x=r.uniform(-40,40); h=r.uniform(1,6)
        peaks.append((x,h,r.uniform(1.0,4.0)))
    def f(x):
        return sum(h*math.exp(-(x-p)**2/(2*w*w)) for p,h,w in peaks)
    gx=max(peaks,key=lambda t:t[1])[0]
    return f,gx,peaks

FIELDS=[make_field(i) for i in range(5)]

def grad(x,f,steps=400,lr=0.03):
    for _ in range(steps):
        g=(f(x+1e-4)-f(x-1e-4))/2e-4
        x+=lr*g
    return x

# ============ 第0步: 基线 (纯形式化方法, 闭环之前) ============
print("="*94)
print("【闭环前】用纯形式化方法 (梯度上升): 能到全局最高峰吗?")
print("="*94)
print()
print(f"  {'领域':<8}{'全局峰位置':<14}{'100个起点成功率':<20}{'说明'}")
print("  "+"-"*70)
BASE=[]
for i,(f,gx,peaks) in enumerate(FIELDS):
    ok=0
    for _ in range(100):
        x0=random.uniform(-40,40)
        x=grad(x0,f)
        if abs(x-gx)<3.0: ok+=1
    BASE.append(ok/100)
    print(f"  {i:<8}{gx:<14.1f}{ok}%{'':<17}{'❌ 大多卡在局部峰' if ok<50 else '✅'}")
print()
print(f"  ★ 闭环前平均成功率: {100*sum(BASE)/len(BASE):.0f}%")
print()

# ============ 第1台: 跳跃器 ============
print("="*94)
print("【第1台 跳跃器】敢往混沌里跳, 在落点做局部搜索")
print("="*94)
print()
JUMPLOG={}
for i,(f,gx,peaks) in enumerate(FIELDS):
    best=None; sv=0; fail=0; good_pts=[]
    for t in range(120):
        x0=random.uniform(-45,45)
        x=grad(x0,f,steps=150,lr=0.05)
        v=f(x)
        if best is None or v>best[1]:
            best=(x,v); sv+=1
        else: fail+=1
        if abs(x-gx)<3.0: good_pts.append(x0)
    JUMPLOG[i]=(best,sv,fail,good_pts)
print(f"  {'领域':<8}{'跳跃次数':<12}{'刷新记录':<12}{'失败':<10}{'失败率':<12}{'找到峰?'}")
print("  "+"-"*76)
tot_fail=tot_n=0
for i in range(5):
    best,sv,fail,gp=JUMPLOG[i]
    f,gx,_=FIELDS[i]
    tot_fail+=fail; tot_n+=sv+fail
    print(f"  {i:<8}{sv+fail:<12}{sv:<12}{fail:<10}{100*fail/(sv+fail):<12.0f}%"
          f"{'✅' if abs(best[0]-gx)<3 else '❌'}")
print()
print(f"  ★ 总失败率: {100*tot_fail/tot_n:.0f}%   ← 这就是「冒险者的失败」")
print()

# ============ 第2台: 形式化器 ============
print("="*94)
print("【第2台 形式化器】在成功落点周围, 找出「哪些起点能到达」")
print("="*94)
print()
RULES={}
for i in range(5):
    f,gx,peaks=FIELDS[i]
    best,sv,fail,gp=JUMPLOG[i]
    if not gp: continue
    lo,hi=min(gp),max(gp)
    # 形式化 = 找出一个「吸引域」区间: 从区间内出发, 大概率能到达峰顶
    # 用二分扩张法确定边界
    def works(a,b,trials=12):
        ok=0
        for _ in range(trials):
            x=grad(random.uniform(a,b),f,steps=200,lr=0.04)
            if abs(x-gx)<3: ok+=1
        return ok/trials
    step=2.0
    A,B=lo,hi
    while works(A-step,B+step,10)>=0.8 and step<30:
        A-=step; B+=step; step*=1.4
    RULES[i]=(A,B,works(A,B,20))
print(f"  {'领域':<8}{'形式化出的规则区间':<26}{'区间内成功率'}")
print("  "+"-"*62)
for i in range(5):
    if i in RULES:
        A,B,acc=RULES[i]
        print(f"  {i:<8}[{A:>6.1f}, {B:>6.1f}]{'':<8}{100*acc:.0f}%")
print()
print("  ★ 规则形态: 「若问题起点落在 [A,B] 内, 则该领域的解法可直达最优」")
print()

# ============ 第3台: 推广器 ============
print("="*94)
print("【第3台 推广器】用规则做前置判断 -> 让「新起点」也能成功")
print("="*94)
print()
print(f"  {'领域':<8}{'闭环前':<14}{'闭环后':<14}{'提升':<12}{'说明'}")
print("  "+"-"*70)
AFTER=[]
for i in range(5):
    f,gx,peaks=FIELDS[i]
    if i not in RULES:
        AFTER.append(BASE[i]); continue
    A,B,acc=RULES[i]
    ok=0
    for _ in range(100):
        x0=random.uniform(-40,40)
        # ★ 推广器: 若起点不在规则区间, 先把起点"搬到"区间内 (这是规则的作用)
        if not (A<=x0<=B):
            x0 = A + (x0-(-40))/80*(B-A)     # 按比例映射进区间
        x=grad(x0,f)
        if abs(x-gx)<3: ok+=1
    AFTER.append(ok/100)
    print(f"  {i:<8}{100*BASE[i]:<14.0f}%{100*AFTER[i]:<14.0f}%"
          f"{AFTER[i]/max(BASE[i],0.01):<12.1f}x{''}")
print()
print(f"  ★ 闭环前平均: {100*sum(BASE)/len(BASE):.0f}%")
print(f"  ★ 闭环后平均: {100*sum(AFTER)/len(AFTER):.0f}%")
print(f"  ★ 提升: {sum(AFTER)/max(sum(BASE),0.01):.1f} 倍")
print()

print("="*94)
print("★ 三台机器的成本账")
print("="*94)
print()
print(f"  {'阶段':<26}{'谁做':<16}{'要多少次尝试':<16}{'成功率'}")
print("  "+"-"*74)
print(f"  {'① 塔尖 (跳进混沌)':<26}{'冒险者':<16}{f'{tot_n} 次':<16}{f'{100*(1-tot_fail/tot_n):.0f}%'}")
print(f"  {'② 形式化 (找规则)':<26}{'工程师':<16}{'几十次采样':<16}{'80%+'}")
print(f"  {'③ 流水线 (用规则)':<26}{'普通人':<16}{'1 次':<16}{f'{100*sum(AFTER)/5:.0f}%'}")
print()
print("  ★ 关键: 第①步的「运气成果」, 被第②步变成「确定性规则」,")
print("     于是第③步谁都能做 —— 这就是「塔尖 -> 腰部 -> 底座」")
print()
print(f"用时 {time.time()-t0:.2f}s")
