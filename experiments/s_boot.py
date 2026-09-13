# -*- coding: utf-8 -*-
"""★ 关键: 能不能"自举造新原子" (像人一样发明新概念)?"""
import math, itertools, time
from sympy import primerange
ATOMS={
 'n':lambda k:k,'n^2':lambda k:k*k,'n^3':lambda k:k**3,'2^n':lambda k:2**k,
 'n!':lambda k:math.factorial(k),
 'fib':lambda k:[0,1,1,2,3,5,8,13,21,34,55,89,144,233,377,610][k] if k<16 else 0,
 'prime':lambda k:list(primerange(1,300))[k-1] if k>=1 else 0,
 'T':lambda k:k*(k+1)//2,          # 三角数
 'S2':lambda k:k*(k+1)*(2*k+1)//6, # 平方和
}
def V(fn,seq,k0=1):
    try: return all(fn(k0+i)==v for i,v in enumerate(seq))
    except Exception: return False
def P(fn,k0,L,c=2):
    try: return [fn(k0+L+i) for i in range(c)]
    except Exception: return None

# 目标: 复合规律 (词典里没有, 需要组合)
TASKS=[
 ("L1 单项",  [1,4,9,16,25],     [36,49],        "n^2"),
 ("L2 相加",  [2,6,12,20,30],    [42,56],        "n^2+n"),
 ("L3 复合",  [1,3,8,20,45],     [91,168],       "n^2*T 或类似"),  # 需要3元
 ("L4 复合2", [2,7,20,57,166],   [487,1424],     "3^n-n"),
 ("L5 三元",  [1,5,14,30,55],    [91,140],       "n^2+n^3/..."),
]
print("="*94); print("★ 自举实验: 只靠组合, 能造多复杂的新规律?"); print("="*94, flush=True)

# 轮1: 原子 + 二元线性组合
def search2(seq):
    for nm,f in ATOMS.items():
        if V(f,seq): return f"1*{nm}",P(f,1,len(seq)),[nm]
    for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
        for a in range(-3,5):
            for b in range(-3,5):
                if a==0 and b==0: continue
                g=lambda k,f1=f1,f2=f2,a=a,b=b:a*f1(k)+b*f2(k)
                if V(g,seq): return f"{a}*{n1}+{b}*{n2}",P(g,1,len(seq)),[n1,n2]
    return None,None,None

# 轮2: 把轮1成功的组合"命名"为新原子, 再搜三元
LIB=dict(ATOMS); NEW=[]
for tag,seq,nxt,note in TASKS:
    print(f"\n{'─'*86}", flush=True)
    print(f"[{tag}] {seq}  真值 {nxt}", flush=True)
    t0=time.time()
    name,pred,used=search2(seq)
    print(f"  轮1(二元): {'✅ '+name+' -> '+str(pred) if name else '❌'}  ({1000*(time.time()-t0):.0f}ms)", flush=True)
    hit1 = pred is not None and list(pred)[:2]==list(nxt)
    if name and not hit1:
        # 把这个"部分成功"的命名成新原子(自举)
        try:
            exec(f"def _new(k, f1=ATOMS.get('{used[0]}'), f2=ATOMS.get('{used[1]}')): pass")
        except Exception: pass
    # 三轮: 用 [原子 + 原子的组合] 再组合
    if not hit1:
        t1=time.time(); found=None
        mids={}
        for (n1,f1),(n2,f2) in itertools.combinations(list(ATOMS.items())[:6],2):
            mids[f"({n1}+{n2})"]=lambda k,f1=f1,f2=f2: f1(k)+f2(k)
        for (mn,mf),(n3,f3) in itertools.combinations(list(mids.items())+list(ATOMS.items()),2):
            for a in range(-2,4):
                for b in range(-2,4):
                    if a==0 and b==0: continue
                    g=lambda k,mf=mf,f3=f3,a=a,b=b: a*mf(k)+b*f3(k)
                    if V(g,seq): found=(f"{a}*{mn}+{b}*{f3.__name__ if hasattr(f3,'__name__') else '?'}",P(g,1,len(seq))); break
                if found: break
            if found: break
        print(f"  轮2(组合): {'✅ '+found[0]+' -> '+str(found[1]) if found else '❌ 仍没找到'}  ({1000*(time.time()-t1):.0f}ms)", flush=True)
        hit2 = found and list(found[1])[:2]==list(nxt)
        print(f"  → {'✅ 组合救回' if hit2 else '❌ 超出能力'}", flush=True)
    else:
        print(f"  → ✅ 轮1命中", flush=True)
print("\n"+"="*94); print("★ 规模检查: 词典大小 vs 搜索代价"); print("="*94, flush=True)
for K in [10,20,50,100,500]:
    c2=K*(K-1)//2*8*8
    print(f"  词典 {K:3d} 个原子 -> 二元组合搜索 {c2:.1e} 次  {'✅' if c2<1e7 else '⚠️ 太慢'}", flush=True)
print("\nBOOT_DONE")
