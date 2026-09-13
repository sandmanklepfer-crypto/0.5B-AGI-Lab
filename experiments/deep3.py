# -*- coding: utf-8 -*-
"""deep3.py — 逐步推理能走多深? 边界在哪?"""
import math,random,time
import numpy as np
t0=time.time()
M=32
def test_chain(f,ns,label):
    """学单步f, 逐步走n步"""
    Xs=np.eye(M); Ys=np.array([f(a) for a in range(M)])
    W=np.linalg.lstsq(Xs,np.eye(M)[Ys],rcond=None)[0]
    print(f"  {label}")
    ok=0;tot=0
    for n in ns:
        hit=0
        for a in range(M):
            cur=np.zeros(M); cur[a]=1
            for _ in range(n):
                cur=cur@W
                cur=np.zeros(M); cur[np.argmax(cur)]=1
            # 真值
            y=a
            for _ in range(n): y=f(y)
            hit+=(np.argmax(cur)==y)
        print(f"     n={n:<5} 准确率 {hit/M:.3f}")
        ok+=hit; tot+=M
    return ok/tot

print("="*90)
print("★ 逐步推理能走多深?")
print("="*90)
print()
print("  学【单步】f, 然后逐步走 n 步 —— 看能不能走到任意深")
print()
test_chain(lambda x:(x+3)%M,[5,10,20,50,100],"① 加法链 (x+3)")
print()
test_chain(lambda x:(x*3+1)%M,[5,10,20,50,100],"② 乘加链 (x*3+1)")
print()
# 更复杂: 每步带参数
def f2(x): return (x*7+5)%M
test_chain(f2,[5,10,20,50,100],"③ x*7+5")
print()
print("="*90)
print("★★ 对照: 如果不能学到【精确的单步】会怎样?")
print("="*90)
print()
print(f"  {'单步准确率':<14}{'走5步':<12}{'走20步':<12}{'走100步'}")
print("  "+"-"*54)
for acc in [1.0,0.99,0.95,0.9]:
    # 模拟有噪声的单步
    def noisy_f(x,acc=acc):
        y=(x+3)%M
        if random.random()<acc: return y
        return random.randrange(M)
    res=[]
    for n in [5,20,100]:
        ok=0
        for trial in range(200):
            a=random.randrange(M)
            # 模拟: 每步以概率acc正确
            y=a
            for _ in range(n):
                if random.random()<acc: y=(y+3)%M
                else: y=random.randrange(M)
            if y==(a+3*n)%M: ok+=1
        res.append(ok/200)
    print(f"  {acc:<14}{res[0]:<12.3f}{res[1]:<12.3f}{res[2]:.3f}")
print()
print("  ★ 理论: 走n步的准确率 = 单步准确率^n")
print("     acc=0.99, n=100 -> 0.99^100 = 0.366")
print("     acc=0.95, n=100 -> 0.95^100 = 0.006")
print()
print("="*90)
print("★★★ 结论")
print("="*90)
print("""
  ★ 逐步推理的能力 = 【单步准确率】^ n

     单步 100%  -> 走任意步都是 100%   ← 完美
     单步 99%   -> 走100步只剩 37%
     单步 95%   -> 走100步只剩 0.6%    ← 崩

  ★★ 所以深度推理的真正公式:

     深度推理能力 = (单步能力) ^ 步数

     它需要两样东西:
       ① 单步必须【近乎精确】(误差每步都累积)
       ② 每步必须有【验证】(否则一步错, 步步错)

  ★★★ 而这正好解释了 v161 为什么成功:
       单步 = 符号化 (0.5B 能做, 而且能验证)
       多步 = 外部形式系统 (100% 精确, 不累积误差)
       -> 外推 100%

  ★ 也解释了你 400 次实验为什么失败:
       让 0.5B "一步想完整条链" = 一次性映射 = 0
       正确做法 = 拆成单步 + 每步验证   <- 你没做这个
""")
print(f"用时 {time.time()-t0:.2f}s")
