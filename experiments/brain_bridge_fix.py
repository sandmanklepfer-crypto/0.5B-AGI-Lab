#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_bridge_fix.py — 桥训练诊断: 是训练不够还是结构不行?
修掉 v1 的死代码, 用干净的反传, 看训练曲线
"""
import numpy as np, time, math
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D,NB=96,24; d=D//NB
r=np.random.RandomState(0); A=np.zeros((D,D))
for b in range(NB):
    s=b*d; e=s+d
    sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
A=A*2.5
x=np.random.RandomState(99).randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4); tr=[]
for t in range(20000):
    act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
    x=x+DT*(g*(A@act-MU*F*x)-G0*x); E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
    tr.append(x[:,0].copy())
tr=np.array(tr); mu=tr[:10000].mean(0); trc=tr-mu
print('脑 20000步 %.1fs'%(time.time()-t0))
# 数据
Xtr=trc[:12000][::10].T     # 1200 样本
Xte=trc[14000:19000][::10].T
print('训练 %d 样本, 测试 %d 样本'%(Xtr.shape[1],Xte.shape[1]))
K=32; SEG=11
# ★ 率失真理论上限
ev=np.linalg.eigvalsh(np.cov(Xte.T))[::-1]; ev=np.clip(ev,1e-12,None); tot=ev.sum()
def rd_err(bits):
    lo,hi=1e-12,float(ev.max())*10
    for _ in range(80):
        th=(lo+hi)/2
        b=0.5*np.sum(np.log2(np.maximum(ev/th,1.0))[ev>th])
        if b>bits: lo=th
        else: hi=th
    th=(lo+hi)/2
    return float(np.sqrt(np.sum(np.minimum(ev,th))/tot))
print('理论上限(率失真): %d符号x5bit=%d bit → 误差 %.1f%%'%(SEG,SEG*5,100*rd_err(SEG*5)))
print('                              (上一轮实测 77.5%%)')
print()
# ★ 干净的反传
r=np.random.RandomState(7)
Wenc=r.randn(K*SEG,D)/np.sqrt(D); Emb=r.randn(D,K*SEG)/np.sqrt(K*SEG)
def fwd(X):
    lg=(Wenc@X).reshape(K,SEG,X.shape[1])
    z=lg-lg.max(0,keepdims=True); P=np.exp(z); P/=P.sum(0,keepdims=True)
    Xd=Emb@P.reshape(K*SEG,X.shape[1])
    return P,Xd,m
def step(X,lr):
    global Wenc,Emb
    m=X.shape[1]
    lg=(Wenc@X).reshape(K,SEG,m)
    z=lg-lg.max(0,keepdims=True); P=np.exp(z); P/=P.sum(0,keepdims=True)
    Pf=P.reshape(K*SEG,m)
    Xd=Emb@Pf
    diff=Xd-X
    L=float((diff**2).sum()/m)
    dX=2.0*diff/m
    G_Emb=dX@Pf.T
    dPf=Emb.T@dX
    dP=dPf.reshape(K,SEG,m)
    dlg=P*(dP-(dP*P).sum(0,keepdims=True))
    G_enc=dlg.reshape(K*SEG,m)@X.T
    Emb-=lr*G_Emb; Wenc-=lr*G_enc
    return L
def evl(X):
    m=X.shape[1]
    lg=(Wenc@X).reshape(K,SEG,m)
    z=lg-lg.max(0,keepdims=True); P=np.exp(z); P/=P.sum(0,keepdims=True)
    Xd=Emb@P.reshape(K*SEG,m)
    se=float(np.linalg.norm(Xd-X)/np.linalg.norm(X))
    base=float(np.linalg.norm(X-X.mean(1,keepdims=True))/np.linalg.norm(X))
    return se,base
print('%-8s %-12s %-12s %s'%('迭代','训练loss','测试误差','vs基线'))
LR=0.05
L=0.0
done=0
for target in [0,50,200,600,1400,3000,6000]:
    while done<target:
        L=step(Xtr,LR); done+=1
        if done%3000==0: LR*=0.7
    se,base=evl(Xte)
    print('%-8d %-12.4f %-12.4f %.2fx'%(done,L,se,se/base))
print()
print('判据: 误差若随迭代持续下降 → 训练不够(可救); 若卡住 → 结构不行')
print('总耗时 %.1fs'%(time.time()-t0))
