# -*- coding: utf-8 -*-
"""deep2.py — 真正的【逐步推理】: 每步用上一步的结果"""
import math,random,time
import numpy as np
from collections import Counter
t0=time.time()
M=32
def task(op):
    f={'add3':lambda x:(x+3)%M,'mul3':lambda x:(x*3+1)%M}[op]
    def run(a,n):
        y=a
        for _ in range(n): y=f(y)
        return y
    return f,run
print("="*94)
print("★ 逐步推理 vs 一次性映射 (这是深度推理的定义)")
print("="*94)
print()
for op in ['add3','mul3']:
    f,runf=task(op)
    print(f"  【{op}】训练见 n=1..4, 测试 n=5..8")
    print()
    # ==== 方式A: 一次性映射 (给a, 直接给n步后的值) ====
    def oneshot(train_ns,test_ns):
        X=[];Y=[]
        for a in range(M):
            for n in train_ns:
                v=np.zeros(M*4); v[a]=1; v[M+min(n,3)]=1
                X.append(v); Y.append(runf(a,n))
        Xte=[];Yte=[]
        for a in range(M):
            for n in test_ns:
                v=np.zeros(M*4); v[a]=1; v[M+min(n,3)]=1
                Xte.append(v); Yte.append(runf(a,n))
        X=np.array(X);Y=np.array(Y);Xte=np.array(Xte);Yte=np.array(Yte)
        W=np.linalg.lstsq(np.hstack([X,np.ones((len(X),1))]),np.eye(M)[Y],rcond=None)[0]
        P=(np.hstack([Xte,np.ones((len(Xte),1))])@W).argmax(1)
        return (P==Yte).mean()
    # ==== 方式B: 逐步推理 (每步: 用当前的premise + 一次f, 走到n) ====
    def stepwise(train_ns,test_ns):
        # 学单步 f
        Xs=[];Ys=[]
        for a in range(M):
            v=np.zeros(M); v[a]=1; Xs.append(v); Ys.append(f(a))
        Ws=np.linalg.lstsq(Xs,np.eye(M)[Ys],rcond=None)[0]
        # 测: 从a逐步走n步
        hit=0;tot=0
        for a in range(M):
            for n in test_ns:
                cur=np.zeros(M); cur[a]=1
                for _ in range(n):
                    cur=(cur@Ws); cur=np.where(cur==cur.max(),1,0)
                    if cur.sum()>1: cur=np.zeros(M); cur[np.argmax(cur@Ws)]=1
                tot+=1
                if np.argmax(cur)==runf(a,n): hit+=1
        return hit/tot
    print(f"  {'方式':<30}{'n=5..8 平均'}")
    print("  "+"-"*46)
    A=oneshot([1,2,3,4],[5,6,7,8])
    B=stepwise([1,2,3,4],[5,6,7,8])
    print(f"  {'① 一次性映射(给a和n直接出结果)':<30}{A:.3f}")
    print(f"  {'② ★逐步推理(每步用f走一步)':<30}{B:.3f}")
    print(f"  {'随机':<30}{1/M:.3f}")
    print()
print("="*94)
print("★★★ 结论")
print("="*94)
print("""
  ★ 判据: 如果【逐步推理】远好于【一次性映射】, 就说明:
     "深度推理 = 把多步拆成单步 + 每步用上一步的结果"

  ★ 而这正是 v161 干的事:
     脑做符号化(单步) + 形式系统做运算(走多步)
""")
print(f"用时 {time.time()-t0:.2f}s")
