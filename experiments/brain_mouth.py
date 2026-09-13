#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_mouth.py — 嘴学脑的语言: 时序结构有没有用?
==================================================
设定: 脑 + 世界(隐藏季节, 只有成败1bit可推断) → 脑状态里编码了季节(已验证86%可解码)
嘴的任务: 从脑状态输出"季节词"(人话)
对照(核心): 
  A 只看当前脑状态      (无时序)
  B 看一段脑状态窗口    (用时序结构)
  C 看当前符号          (离散化后)
若 B > A → 脑的时序结构对嘴有真实价值 = 你的方案成立
"""
import numpy as np, time
t0=time.time()
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8; SIG=np.tanh
D,NB=24,6; d=D//NB; NC=16
SWITCH_P=1.0/150.0; EPS_IN=1.5
r=np.random.RandomState(0); A=np.zeros((D,D))
for b in range(NB):
    s=b*d; e=s+d
    sub=r.randn(d,d); w=np.abs(np.linalg.eigvals(sub)).max(); A[s:e,s:e]=sub*(1.15/w)
A=A*2.5; W_in=r.randn(D,2)/np.sqrt(2)
C0=np.arange(0,8); C1=np.arange(8,16)
Pc=np.zeros((2,NC)); Pc[0,C0]=0.7/8; Pc[0,C1]=0.3/8
Pc[1,C1]=0.7/8; Pc[1,C0]=0.3/8; Pc+=1e-9; Pc/=Pc.sum(1,keepdims=True)

# ---- 生成: 脑+世界, 收集 (脑状态, 季节) ----
def collect(steps=25000,seed=1):
    rng=np.random.RandomState(seed)
    x=rng.randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4)
    tr0=tr1=0.0; season=0; X=[]; S=[]
    for t in range(steps):
        m=int(rng.rand()<0.5)
        c=int(rng.choice(NC,p=Pc[m]))
        ok=int((c in C0) if season==0 else (c in C1))
        inp=np.array([[tr0],[tr1]])
        act=SIG(x); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
        x=x+DT*(g*(A@act-MU*F*x+EPS_IN*(W_in@inp))-G0*x)
        E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
        if m==0: tr0=0.97*tr0+0.03*ok
        else:    tr1=0.97*tr1+0.03*ok
        if rng.rand()<SWITCH_P: season=1-season
        X.append(x[:,0].copy()); S.append(season)
    return np.array(X),np.array(S)

X,S=collect()
mu=X[:8000].mean(0); Xc=X-mu
print('脑+世界: %d步 [%.1fs]  季节占比 %.2f'%(len(X),time.time()-t0,S.mean()))

# ---- 嘴: 线性分类器 (简单, 快, 判据清楚) ----
def logistic(Xtr,ytr,Xte,yte,iters=400,lr=0.5):
    W=np.zeros(Xtr.shape[1]); b=0.0
    for it in range(iters):
        p=1/(1+np.exp(-(Xtr@W+b)))
        g=((p-ytr)@Xtr)/len(ytr); W-=lr*g; b-=lr*(p-ytr).mean()
        lr*=0.997
    pred=((Xte@W+b)>0).astype(int)
    return float((pred==yte).mean())

# 窗口拼接(用时序)
def windowize(Xc,W_win):
    n=len(Xc)-W_win
    return np.concatenate([Xc[i:i+n] for i in range(W_win)],axis=1), n

ntr=int(len(Xc)*0.6)
y=S.copy()   # 0/1 标签
print()
print('嘴学映射: 从脑 → 季节词   (瞎猜=0.5)')
print('%-34s %-12s %s'%('嘴看到什么','准确率','说明'))
# A 只看当前
acc=logistic(Xc[:ntr],y[:ntr],Xc[ntr:],y[ntr:])
print('%-34s %-12.3f %s'%('A 当前脑状态 (无时序)',acc,'基线'))
# B 窗口
for W_win in [2,5,10]:
    Xw,nw=windowize(Xc,W_win); ntrw=int(nw*0.6)
    yw=y[W_win-1:W_win-1+nw]          # 标签对齐到窗口末帧
    acc=logistic(Xw[:ntrw],yw[:ntrw],Xw[ntrw:],yw[ntrw:])
    print('%-34s %-12.3f %s'%('B 窗口%d帧 (用时序)'%W_win,acc,'★ 优于A' if acc>0.60 else ''))
# C 离散符号
Z=Xc@np.linalg.svd(Xc[::10],full_matrices=False)[2][:8].T
K=32; rng=np.random.RandomState(3); C=Z[rng.choice(len(Z),K,replace=False)].copy()
for _ in range(10):
    d2=((Z[:,None,:]-C[None,:,:])**2).sum(2); lab=d2.argmin(1)
    for k in range(K):
        m=(lab==k)
        if m.sum()>0: C[k]=Z[m].mean(0)
S1=np.zeros((len(lab),K)); S1[np.arange(len(lab)),lab]=1
acc=logistic(S1[:ntr],y[:ntr],S1[ntr:],y[ntr:])
print('%-34s %-12.3f %s'%('C 当前符号 (离散32)',acc,''))
# C2 符号窗口
W5=5
Sw=np.concatenate([S1[i:i+len(S1)-W5] for i in range(W5)],axis=1)
ntrw=int(len(Sw)*0.6)
yw5=y[W5-1:W5-1+len(Sw)]
acc=logistic(Sw[:ntrw],yw5[:ntrw],Sw[ntrw:],yw5[ntrw:])
print('%-34s %-12.3f %s'%('C2 符号窗口5 (离散+时序)',acc,''))
print()
print('判据: 若「时序」明显优于「无时序」→ 脑的结构对嘴有真实价值')
print('总耗时 %.1fs'%(time.time()-t0))
