#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""world_loop2.py — 世界改成线性可分, 看能否学到上限"""
import numpy as np, time
t0=time.time()
D,K=64,4
rng=np.random.RandomState(0)
Vw = rng.randn(D,K)/np.sqrt(D)          # 线性世界 (读出层能完美学)
def world_answer(x): return int(np.argmax(x@Vw))
Q,_=np.linalg.qr(rng.randn(D,D)); A=Q*1.15; Qt=np.ascontiguousarray(A.T)
NPH=8; PHW=np.array([1.0,1.618,2.414,1.732,2.236,1.414,2.646,1.303]); ph0=rng.rand(NPH)*2*np.pi
def make_brain():
    ph=ph0.copy()
    def brain(x):
        nonlocal ph
        x=x.copy()
        for _ in range(3):
            x=0.5*x+0.5*np.tanh(x@Qt)
            d=ph[None,:]-ph[:,None]; ph=ph+0.05*(PHW+0.5*np.sin(d).mean(1))
        return x
    return brain
def run(mode,steps=2000,lr=0.05):
    W=rng.randn(K,D)*0.01; brain=make_brain(); base=0.0; hist=[]
    for t in range(steps):
        x=rng.randn(D)*0.5; h=brain(x)
        z=W@h; p=np.exp(z-z.max()); p/=p.sum()
        pred=int(rng.choice(K,p=p))
        correct=(pred==world_answer(x)); hist.append(1.0 if correct else 0.0)
        reward = (1.0 if correct else 0.0) if mode=='world' else (1.0 if rng.rand()<0.25 else 0.0)
        base=0.99*base+0.01*reward
        g=np.zeros(K); g[pred]=1.0
        W=W+lr*(reward-base)*np.outer(g-p,h); W=np.clip(W,-3,3)
    return np.array(hist)
print('='*58); print('线性可分世界 — 能否学到上限?'); print('='*58)
print('  %-18s %-11s %-11s %s'%('反馈','前400步','后800步','判定'))
for m,nm in [('world','★真世界'),('random','随机')]:
    h=run(m); a,b=h[:400].mean(),h[-800:].mean()
    print('  %-18s %-11.4f %-11.4f %s'%(nm,a,b,'✅' if b>a+0.1 else '❌'))
print('\n  随机基线=0.2500   用时%.2fs'%(time.time()-t0))
