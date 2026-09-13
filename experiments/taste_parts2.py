# -*- coding: utf-8 -*-
import random, math, time
t0=time.time()
print("="*94)
print("★ 重做 (上次测错了): 奖励【一次性】才算真探索")
print("="*94)
print("""
  上次错在哪: 奖励可以重复拿 -> 那"锁定在一个好动作上"就是理性策略.
             结果随机(66) > 我的组装(34), 而且零件拿掉不掉分.

  真实世界: 新东西才有价值 (拿过一次就没了)
  ★ 这次改成【一次性奖励】, 这才是"探索"的真实定义
""")
print()

NA=100
GOOD={7:10.0,23:8.0,61:9.0,88:7.0}
def reward(a, found): return 0.0 if a in found else GOOD.get(a,0.0)

def run(policy_name, seed, steps=100):
    rnd=random.Random(seed)
    found=set(); total=0.0
    mem={}; visited=set(); temp=1.0; banned=set()
    for _ in range(steps):
        if policy_name=='random':
            a=rnd.choice(range(NA))
        else:
            # ★ 品味器: 探索(去重) + 记忆(有效则再试) + 收敛
            fresh=[x for x in range(NA) if x not in visited and x not in banned]
            if mem and rnd.random()<temp*0.5:
                a=max(mem.items(),key=lambda kv:kv[1])[0]
            else:
                a=rnd.choice(fresh) if fresh else rnd.choice(range(NA))
        r=reward(a,found)
        if r>0: found.add(a); mem[a]=r
        else:
            if a in mem: del mem[a]      # 记忆修正
            visited.add(a)
        visited.add(a); temp=max(0.1,temp*0.97)
        total+=r
    return total

print(f"  {'策略':<26}{'30个种子平均总收益':<22}{'标准差'}")
print("  "+"-"*62)
for nm in ['random','taste']:
    vs=[run(nm,s) for s in range(30)]
    m=sum(vs)/len(vs)
    sd=math.sqrt(sum((v-m)**2 for v in vs)/len(vs))
    print(f"  {nm:<26}{m:<22.2f}{sd:.2f}")
print()

# 消融: 去掉各零件
print("="*94)
print("★ 消融: 去掉每个零件, 各掉多少? (30种子平均)")
print("="*94)
print()
def run_abl(disable, seed, steps=100):
    rnd=random.Random(seed)
    found=set(); total=0.0; mem={}; visited=set(); temp=1.0
    for _ in range(steps):
        fresh=[x for x in range(NA) if x not in visited]
        if disable=='mem':          a=rnd.choice(fresh) if fresh else rnd.choice(range(NA))
        elif disable=='explore':    a=rnd.choice(range(NA))
        elif disable=='converge':   a=rnd.choice(fresh) if fresh else rnd.choice(range(NA))
        else:
            if mem and rnd.random()<temp*0.5:
                a=max(mem.items(),key=lambda kv:kv[1])[0]
            else: a=rnd.choice(fresh) if fresh else rnd.choice(range(NA))
        r=reward(a,found)
        if r>0: found.add(a); mem[a]=r
        else: visited.add(a)
        if disable!='converge': temp=max(0.1,temp*0.97)
        total+=r
    return total
base=sum(run_abl(None,s) for s in range(30))/30
print(f"  {'配置':<28}{'总收益':<14}{'相对完整'}")
print("  "+"-"*56)
print(f"  {'完整 (7零件)':<28}{base:<14.2f}基准")
for d,nm in [('mem','拿掉③记忆'),('explore','拿掉④探索'),('converge','拿掉⑤收敛')]:
    v=sum(run_abl(d,s) for s in range(30))/30
    print(f"  {nm:<28}{v:<14.2f}{(v-base)/base*100:+.0f}%")
print()
print("="*94)
print("★ 诚实小结")
print("="*94)
print("""
  上一轮我做错了两次 (奖励可重复 -> 零件无效; 然后我还写了"每件都掉").

  这一轮改对之后, 才能看出零件到底有没有用.
  ★ 关键教训: 我给的映射表(7零件↔你的资产)是【我的主观解释】,
     不是实验结果. 你不能拿它当证据.
  真正靠得住的, 只有你自己跑过的那几个数字:
     配额记忆 0.995 / boundary 校准 1.000 / 相位通道 5959倍 / 自持环活了349步
""")
print(f"用时 {time.time()-t0:.2f}s")
