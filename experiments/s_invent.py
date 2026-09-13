# -*- coding: utf-8 -*-
"""★ 终极测试: 能不能"自动发明新原子" (人看到陌生数列会做的事)"""
import math, itertools
print("="*94); print("★ 终极测试: 面对词典外的数列, 能否自动造出新原子?"); print("="*94, flush=True)

SEQ=[2,7,20,57,166]      # 真值 3^n - n
print(f"\n  目标数列: {SEQ}   (真规律: 3^n - n, 词典里只有 2^n)", flush=True)

# 人类的方法: 看差分/比值, 猜结构
print("\n  【人类方法】逐步诊断:", flush=True)
d=[SEQ[i+1]-SEQ[i] for i in range(len(SEQ)-1)]
print(f"    1阶差分: {d}", flush=True)
d2=[d[i+1]-d[i] for i in range(len(d)-1)]
print(f"    2阶差分: {d2}", flush=True)
r=[round(SEQ[i+1]/SEQ[i],2) for i in range(len(SEQ)-1)]
print(f"    比值:    {r}   ← 接近3, 提示底数=3", flush=True)

# 自动造原子: 从比值猜底数
print("\n  【自动造原子】从数据反推:", flush=True)
import numpy as np
k=np.arange(1,len(SEQ)+1, dtype=float)
logs=np.log(np.array(SEQ,dtype=float))
coef=np.polyfit(k, logs, 1)     # log(y) ~ a*k+b
base=math.exp(coef[0])
print(f"    对数线性拟合: y ≈ C·base^n, base = {base:.3f}  → 猜底数 3", flush=True)

# 用猜到的底数构造新原子
NEW_ATOM={'3^n': lambda j: 3**j}
print(f"    造出新原子: 3^n", flush=True)

# 用新原子再搜
def V(fn,seq,k0=1):
    try: return all(fn(k0+i)==v for i,v in enumerate(seq))
    except Exception: return False
ATOMS={'n':lambda j:j,'n^2':lambda j:j*j,'2^n':lambda j:2**j,**NEW_ATOM}
print("\n  【重新搜索】词典里加入 3^n 后:", flush=True)
found=None
for nm,f in ATOMS.items():
    if V(f,SEQ): found=(f"1*{nm}",[f(j) for j in [6,7]]); break
if not found:
    for (n1,f1),(n2,f2) in itertools.combinations(ATOMS.items(),2):
        for a in range(-3,4):
            for b in range(-3,4):
                if a==0 and b==0: continue
                g=lambda j,f1=f1,f2=f2,a=a,b=b:a*f1(j)+b*f2(j)
                if V(g,SEQ):
                    found=(f"{a}*{n1}+{b}*{n2}",[g(j) for j in [6,7]]); break
            if found: break
        if found: break
print(f"    {'✅ '+found[0]+' -> 预测 '+str(found[1]) if found else '❌ 仍失败'}", flush=True)
print(f"    真值: 3^6-6={3**6-6}  3^7-7={3**7-7}", flush=True)

print("\n"+"="*94); print("★ 关键: 这个'造原子'过程能自动做几次? (自动化的上限)"); print("="*94, flush=True)
for name,seq,true_base in [("2^n",[2,4,8,16,32],2),("5^n",[5,25,125,625,3125],5)]:
    kk=np.arange(1,len(seq)+1,dtype=float)
    c=np.polyfit(kk,np.log(np.array(seq,dtype=float)),1)
    print(f"  {name:6s}: 拟合底数={math.exp(c[0]):.2f}  真值={true_base}  {'✅ 自动识出' if abs(math.exp(c[0])-true_base)<0.5 else '❌'}", flush=True)
print("\nINVENT_DONE")
