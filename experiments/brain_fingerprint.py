#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_fingerprint.py — 脑的动力学指纹 (形式量测量工具)
四个标准量, 跨轨迹稳定(变异<8%): D2 相关维数 / H 谱熵 / RR 递归率 / tau 自相关时间
用法: from brain_fingerprint import fingerprint
"""
import numpy as np
SIG = np.tanh
DT=0.05; ETA,GAMMA,KAPPA=0.5,0.18,0.6; G0,RHO,MU=0.35,0.02,1.8

def make_brain(D=12,NB=3,scale=1.2,seed=0):
    d=D//NB; r=np.random.RandomState(seed); A=np.zeros((D,D))
    for b in range(NB):
        s=b*d; e=s+d; sub=r.randn(d,d)
        A[s:e,s:e]=sub*(1.15/np.abs(np.linalg.eigvals(sub)).max())
    return A*scale

def traj(A,seed=1,L=800,burn=200):
    D=A.shape[0]; r=np.random.RandomState(seed)
    x=r.randn(D,1)*0.5; F=np.zeros_like(x); E=np.full((1,1),0.4); X=[]
    for t in range(L):
        a=SIG(x); F=np.clip(F+DT*RHO*(a*a-F),0,2); g=E/(KAPPA+E)
        x=x+DT*(g*(A@a-MU*F*x)-G0*x)
        E=np.maximum(E+DT*(ETA*(a*a).sum(0,keepdims=True)-GAMMA*E),0.)
        X.append(x[:,0])
    return np.array(X)[burn:]

def fingerprint(X,n=300):
    """返回 (D2, H, RR, tau)"""
    L=len(X); idx=np.random.RandomState(0).choice(L,min(L,n),replace=False); Y=X[idx]
    dd=np.linalg.norm(Y[:,None,:]-Y[None,:,:],axis=2)[np.triu_indices(len(Y),1)]
    rs=np.percentile(dd,np.linspace(5,60,8)); C=np.array([(dd<r).mean() for r in rs]); ok=C>0
    D2=float(np.polyfit(np.log(rs[ok]),np.log(C[ok]),1)[0])
    RR=float((dd<dd.mean()*0.1).mean())
    f=X[:,0]-X[:,0].mean(); P=np.abs(np.fft.rfft(f))**2; P=P/P.sum(); P=P[P>1e-12]
    H=float(-(P*np.log(P)).sum()/np.log(len(P)))
    fm=X.mean(1)-X.mean(1).mean(); ac=np.correlate(fm,fm,'full')[len(fm)-1:]; ac/=ac[0]+1e-12
    i=np.where(ac<0.5)[0]; tau=float(i[0]) if len(i) else float(len(fm))
    return np.array([D2,H,RR,tau])

def lyapunov(A,seed=1,steps=600,eps=1e-8):
    """参考量(临界系统变异大)"""
    D=A.shape[0]; r=np.random.RandomState(seed)
    x=r.randn(D); y=x+eps; s=0.0
    for t in range(steps):
        a1=SIG(x); a2=SIG(y)
        F=np.clip(DT*RHO*(a1*a1),0,2); g=Ei=0.4/(KAPPA+0.4)
        x=x+DT*(g*(A@a1-MU*F*x)-G0*x); y=y+DT*(g*(A@a2-MU*F*y)-G0*y)
        d=np.linalg.norm(y-x)
        if d>1e-30: s+=np.log(d/eps); y=x+(y-x)*(eps/d)
    return s/steps

NAMES=['D2相关维数','H谱熵','RR递归率','tau自相关']

if __name__=='__main__':
    print('【脑的动力学指纹 — 形式量测量工具】')
    print('%-14s %-12s %-12s %s'%('脑状态','D2','H','RR / tau'))
    for sc,nm in [(0.3,'死(0.3活性)'),(1.2,'活(1.2活性)'),(1.8,'高活(1.8)')]:
        A=make_brain(scale=sc); V=np.array([fingerprint(traj(A,seed=s+1)) for s in range(3)]).mean(0)
        print('%-14s %-12.4f %-12.4f %.4f / %.1f'%(nm,V[0],V[1],V[2],V[3]))
