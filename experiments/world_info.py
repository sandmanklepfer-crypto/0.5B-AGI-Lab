#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_info.py — 决定性: 信息量 × 世界复杂度 × 核写活"""
import numpy as np, time
t0=time.time()
D,K=64,4
rng=np.random.RandomState(0)
Ww=rng.randn(D,D)/np.sqrt(D); Vw=rng.randn(D,K)/np.sqrt(D)
def ans_nonlin(x): return int(np.argmax(np.tanh(x@Ww)@Vw))
def ans_lin(x):    return int(np.argmax(x@Vw))
Q,_=np.linalg.qr(rng.randn(D,D)); A0=Q*1.15; I=np.eye(D)
def run(ans_fn, fb, mode, steps=1200, lr=0.08, delta=0.03):
    A=A0.copy(); W=rng.randn(K,D)*0.01; base=0.0; hist=[]
    for t in range(steps):
        x=rng.randn(D)*0.5
        h=0.5*x+0.5*np.tanh(A@x)
        z=W@h; p=np.exp(z-z.max()); p/=p.sum()
        pred=int(rng.choice(K,p=p))
        true=ans_fn(x); correct=(pred==true); hist.append(1.0 if correct else 0.0)
        if fb=='1bit':   r=1.0 if correct else 0.0
        else:            r=1.0 if correct else -1.0   # 有"错"的方向信息
        base=0.99*base+0.01*r; sig=r-base
        g=np.zeros(K); g[pred]=1.0
        W=W+lr*sig*np.outer(g-p,h); W=np.clip(W,-3,3)
        if mode=='tape':
            v=x/(np.linalg.norm(x)+1e-9); u=A@x; u=u/(np.linalg.norm(u)+1e-9)
            A=A@(I+delta*sig*(np.outer(v,u)-np.outer(u,v)))
            if t%200==199: Qq,_=np.linalg.qr(A); A=Qq*1.15
    return hist[:300], hist[-600:]
print('★ 信息量 × 世界 × 核写活 (最终正确率)')
print()
print('  %-12s %-12s %-14s %-14s'%('世界','反馈','核冻结','核写活'))
for wname,fn in [('线性',ans_lin),('非线性',ans_nonlin)]:
    for fb in ['1bit','±1']:
        a=run(fn,fb,'freeze'); b=run(fn,fb,'tape')
        print('  %-12s %-12s %-14.4f %-14.4f'%(wname,fb,np.mean(a[1]),np.mean(b[1])))
print()
print('  随机基线=0.2500')
print('  用时%.2fs'%(time.time()-t0))
