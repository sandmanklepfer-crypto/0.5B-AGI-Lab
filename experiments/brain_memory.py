#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_memory.py — 决定性实验: 脑的丰富度到底有没有价值?
==========================================================
任务: 延迟匹配 (经典记忆任务)
  t 时刻世界给随机 bit b_t; 要求 t+DELAY 时把它报出来
  脑充当局间记忆(水库); 嘴从脑状态读出答案
对照:
  R24 丰富脑 (24模块, 有效维~13)
  R06 中等脑 (6模块)
  R01 简单脑 (1模块, 有效维~1.6)
  RAW 无脑   (直接看当前输入)
判据: 延迟 DELAY 越长, 丰富脑的优势是否越大?
  若「优势随延迟增长」→ 脑的丰富度有真实价值 (这正是它存在的理由)
"""
import numpy as np, time
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D=24

def make_brain(NB,scale=2.5,seed=0):
    if NB<=1:
        r=np.random.RandomState(seed); A=r.randn(D,D)
        w=np.abs(np.linalg.eigvals(A)).max(); return A*(1.15/w)*scale
    d=D//NB; r=np.random.RandomState(seed); A=np.zeros((D,D))
    for b in range(NB):
        s=b*d; e=s+d
        sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
    return A*scale

def run(A,delay,steps=30000,seed=1,read_noise=0.0):
    """返回: 序列(用于读出), 标签"""
    rng=np.random.RandomState(seed)
    x=rng.randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4)
    W_in=rng.randn(D,1)/1.0
    X=[]; B=[]
    bits=rng.randint(0,2,steps)
    for t in range(steps):
        b=float(bits[t])
        inp=W_in*(b if rng.rand()<0.5 else 0.0)   # 稀疏输入(50%有信号)
        act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
        x=x+DT*(g*(A@act-MU*F*x+1.5*inp)-G0*x)
        E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
        X.append(x[:,0].copy()); B.append(b)
    X=np.array(X); B=np.array(B)
    return X,B

def readout(X,B,delay,ntr_frac=0.6):
    """在 t+delay 时刻从脑状态读 b_t"""
    n=len(X)-delay
    Xd=X[:n]; yd=B[delay:delay+n]
    mu=Xd[:int(n*ntr_frac)].mean(0); Xc=Xd-mu
    ntr=int(n*ntr_frac)
    # 岭回归(闭式, 快)
    lam=1e-2
    W=np.linalg.solve(Xc[:ntr].T@Xc[:ntr]+lam*np.eye(D), Xc[:ntr].T@(yd[:ntr]*2-1))
    pred=(Xc[ntr:]@W>0).astype(int)
    acc=float((pred==yd[ntr:]).mean())
    return acc

print('='*84)
print('决定性实验: 脑的丰富度有没有价值? (延迟匹配任务, %d步/组)'%30000)
print('='*84)
print()
for delay in [1,5,20,60,150]:
    print('延迟 DELAY=%d:'%delay)
    for NB,nm in [(1,'R01 简单脑(1块)'),(6,'R06 中等脑(6块)'),(24,'R24 丰富脑(24块)')]:
        A=make_brain(NB)
        X,B=run(A,delay)
        acc=readout(X,B,delay)
        mark='★' if acc>0.85 else ''
        print('   %-20s 读出准确率 = %.3f  %s'%(nm,acc,mark))
    # 无脑基线: 直接看当前输入
    print('   %-20s 读出准确率 = %.3f  (理论上界, 把输入直接延迟)'%('RAW 完美延迟线',1.0))
    print()
print('判据: 延迟越大, 丰富脑 应该领先简单脑越多 (那是脑存在的理由)')
print('用时 %.0fs'%(time.time()-t0))
