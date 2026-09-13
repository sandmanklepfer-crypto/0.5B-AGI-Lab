#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_mem2.py — 修正版: 延迟匹配任务 (正确配置 D=96, 每块4维)"""
import numpy as np, time
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D,NB=96,24; d=D//NB

def make(scale=1.2,seed=0):
    r=np.random.RandomState(seed); A=np.zeros((D,D))
    for b in range(NB):
        s=b*d; e=s+d
        sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
    return A*scale

def run(A,delay,gain=8.0,steps=12000,seed=1,p_in=1.0):
    rng=np.random.RandomState(seed)
    x=rng.randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4)
    W_in=rng.randn(D,1)/np.sqrt(D)
    X=[];B=[]
    for t in range(steps):
        b=float(rng.randint(0,2))
        u=W_in*(b if rng.rand()<p_in else 0.0)
        act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
        x=x+DT*(g*(A@act-MU*F*x+gain*u)-G0*x)
        E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
        X.append(x[:,0].copy()); B.append(b)
    return np.array(X),np.array(B)

def readout(X,B,delay,ntr=0.6):
    # 在时刻 t 读出 delay 步前的 bit:  X[delay:]  <->  B[:-delay]
    Xd=X[delay:]; yd=B[:len(X)-delay] if delay>0 else B
    n=len(Xd)
    mu=Xd[:int(n*ntr)].mean(0); Xc=Xd-mu
    k=int(n*ntr)
    W=np.linalg.solve(Xc[:k].T@Xc[:k]+0.5*np.eye(D), Xc[:k].T@(yd[:k]*2-1))
    return float(((Xc[k:]@W>0).astype(int)==yd[k:]).mean())

print('='*80)
print('修正版 延迟匹配任务 | D=%d, %d块×%d维 | 瞎猜=0.5'%(D,NB,d))
print('='*80)
print()
print('%-8s %-10s %-12s %-12s %s'%('scale','延迟','有效维','读出准确率','判定'))
for scale in [1.2]:
    A=make(scale)
    for delay in [0,1,10,40,120,300]:
        X,B=run(A,delay)
        acc=readout(X,B,delay)
        ns=X[-5000:]; ww=np.sort(np.linalg.eigvalsh(np.cov(ns.T)))[::-1]
        ed=float((ww.sum()**2)/max((ww**2).sum(),1e-12))
        print('%-8.1f %-10d %-12.2f %-12.3f %s'%(scale,delay,ed,acc,
              '★ 记住了' if acc>0.75 else ('✓' if acc>0.6 else '')))
    print()
print('对照: 若把输入直接延迟 (完美延迟线) = 1.000')
print('用时%.0fs'%(time.time()-t0))
