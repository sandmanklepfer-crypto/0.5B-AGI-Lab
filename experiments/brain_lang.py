#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_lang.py — 脑自己的符号序列, 是不是「语言」?
===================================================
判据(可学性 = 嘴能不能学会映射的前提):
  L1 一致性: 同一状态 → 同一符号? (量化重建误差)
  L2 可预测: 符号序列能从前文猜后文? (n-gram 准确率)
  L3 有语法: 长程结构? (不同阶数的预测增益)
  对照: 打乱时序的同一序列 (破坏结构, 保留统计)
"""
import numpy as np, time
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D,NB=96,24; d=D//NB
r=np.random.RandomState(0); A=np.zeros((D,D))
for b in range(NB):
    s=b*d; e=s+d
    sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
A=A*2.5
x=np.random.RandomState(99).randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4); tr=[]
for t in range(30000):
    act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
    x=x+DT*(g*(A@act-MU*F*x)-G0*x); E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
    tr.append(x[:,0].copy())
tr=np.array(tr); tr=tr-tr.mean(0)
print('脑 30000步 [%.1fs]'%(time.time()-t0))

# ---------- L1: 量化成符号 (k-means, 用PCA降到6维加速) ----------
_,_,Vt=np.linalg.svd(tr-tr.mean(0),full_matrices=False)
Z=tr@Vt[:6].T
K=64
rng=np.random.RandomState(3)
C=Z[rng.choice(len(Z),K,replace=False)]
for _ in range(20):
    d2=((Z[:,None,:]-C[None,:,:])**2).sum(2); lab=d2.argmin(1)
    for k in range(K):
        if (lab==k).sum()>0: C[k]=Z[lab==k].mean(0)
# 重建误差(在6维子空间)
rec=np.sqrt(((Z-C[lab])**2).sum(1).mean())/np.sqrt((Z**2).sum(1).mean())
print()
print('L1 一致性 (量化成 %d 个符号):'%K)
print('   重建相对误差 = %.3f   %s'%(rec,'✅ 状态可分' if rec<0.3 else '⚠️ 状态重叠严重'))
cnt=np.bincount(lab,minlength=K)/len(lab); cnt=cnt[cnt>0]
H=float(-(cnt*np.log(cnt)).sum()/np.log(K))
print('   符号熵 = %.3f   用到的符号 = %d/%d'%(H,(np.bincount(lab,minlength=K)>len(lab)*0.001).sum(),K))

# ---------- L2/L3: 可预测性 ----------
seq=lab[-100000:] if len(lab)>100000 else lab
def pred_acc(seq,order,ntr_frac=0.7):
    n=len(seq); ntr=int(n*ntr_frac)
    from collections import defaultdict
    tab=defaultdict(lambda: np.zeros(K))
    for i in range(order,n):
        if i<ntr: tab[tuple(seq[i-order:i])][seq[i]]+=1
    hit=0; tot=0; fallback=np.bincount(seq[:ntr],minlength=K)/ntr
    for i in range(max(order,ntr),n):
        v=tab.get(tuple(seq[i-order:i]))
        p=(v/v.sum()) if (v is not None and v.sum()>0) else fallback
        if p.argmax()==seq[i]: hit+=1
        tot+=1
    return hit/max(tot,1)

print()
print('L2/L3 可预测性 (从前文猜下一个符号; 瞎猜=1/%d=%.3f):'%(K,1/K))
print('   %-10s %-14s %-14s %s'%('阶数','真实序列','打乱时序','结构增益'))
for order in [1,2,3,5]:
    a=pred_acc(seq,order)
    r2=np.random.RandomState(5); sh=seq.copy(); r2.shuffle(sh)
    b=pred_acc(sh,order)
    print('   %-10d %-14.3f %-14.3f %+.3f %s'%(order,a,b,a-b,'✅ 有结构' if a-b>0.05 else '⚠️ 无结构'))

# ---------- 判据 ----------
a3=pred_acc(seq,3); r2=np.random.RandomState(5); sh=seq.copy(); r2.shuffle(sh); b3=pred_acc(sh,3)
print()
print('='*70)
print('结论: 脑的符号序列是不是「语言」?')
print('='*70)
if a3>0.25 and (a3-b3)>0.05:
    print('  ★ 是。三阶预测 %.3f (瞎猜 %.3f, 打乱 %.3f)'%(a3,1/K,b3))
    print('    → 脑有自己的一致符号系统 + 可预测结构')
    print('    → 嘴可以学会这个映射 (你说得对)')
else:
    print('  ✗ 否。三阶预测 %.3f ≈ 瞎猜 %.3f'%(a3,1/K))
    print('    → 脑的符号序列像噪声, 嘴学不了')
print()
print('用时 %.1fs'%(time.time()-t0))
