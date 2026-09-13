#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_verify.py — 闭环跑够长, 还停得住吗?"""
import numpy as np
D,DT=24,0.05
ETA,GAMMA,KAPPA=0.5,0.18,0.6
G0,RHO,MU=0.35,0.02,1.8
SIG=np.tanh; H,K=32,16
def renorm(A,r=0.98):
    w=np.abs(np.linalg.eigvals(A)).max(); return A*(r/max(w,1e-9))
def bstep(A,X,F,E,inj=None):
    act=SIG(X); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
    core=A@act-MU*F*X
    if inj is not None: core=core+inj
    X=X+DT*(g*core-G0*X)
    E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
    return X,F,E
def ib(K,seed=1):
    r=np.random.RandomState(seed)
    return dict(W1=r.randn(H,D)/np.sqrt(D),b1=np.zeros(H),W2=r.randn(K,H)/np.sqrt(H),
                b2=np.zeros(K),Wd=r.randn(D,K)/np.sqrt(K),bd=np.zeros(D))
def enc(B,X):
    Hh=np.tanh(B['W1']@X+B['b1'][:,None]); return B['W2']@Hh+B['b2'][:,None],Hh
def sm(z):
    z=z-z.max(0,keepdims=True); p=np.exp(z); return p/p.sum(0,keepdims=True)
def tr_b(B,Xa,iters=500,lr=0.01):
    M=Xa.shape[1]; B={k:v.copy() for k,v in B.items()}
    ms={k:np.zeros_like(v) for k,v in B.items()}; vs={k:np.zeros_like(v) for k,v in B.items()}
    for it in range(iters+1):
        lg,Hh=enc(B,Xa); P=sm(lg); Xd=B['Wd']@P+B['bd'][:,None]
        dX=2.0*(Xd-Xa)/M
        G=dict(Wd=dX@P.T,bd=dX.sum(1)); dP=B['Wd'].T@dX
        dlg=P*(dP-(dP*P).sum(0,keepdims=True))
        G['W2']=dlg@Hh.T; G['b2']=dlg.sum(1)
        dpre=(B['W2'].T@dlg)*(1-Hh**2); G['W1']=dpre@Xa.T; G['b1']=dpre.sum(1)
        for k in B:
            ms[k]=0.9*ms[k]+0.1*G[k]; vs[k]=0.999*vs[k]+0.001*(G[k]**2)
            B[k]-=lr*(ms[k]/(1-0.9**(it+1)))/(np.sqrt(vs[k]/(1-0.999**(it+1)))+1e-8)
    return B
rng=np.random.RandomState(0); A=renorm(rng.randn(D,D)); W_in=rng.randn(D,K)/np.sqrt(K)
X0=(np.random.RandomState(99).randn(D,1)*0.5)
# 训桥用的数据: 裸脑轨迹
X=(np.random.RandomState(99).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4); tr=[]
for t in range(3000):
    X,F,E=bstep(A,X,F,E); tr.append(X[:,0].copy())
B=tr_b(ib(K), np.array(tr)[::5].T, iters=500)
print("="*88); print("闭环长度效应: 同一个闭环, 不同观测时长"); print("="*88)
for EPS in [0.0, 0.05, 0.2]:
    for STEPS in [120, 600, 3000, 10000]:
        X=(np.random.RandomState(77).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4)
        seq=[]
        for t in range(STEPS):
            lg,_=enc(B,X); P=sm(lg); seq.append(int(lg.argmax(0)[0]))
            inj = None if EPS==0 else EPS*(W_in@P)
            X,F,E=bstep(A,X,F,E,inj)
        u=len(set(seq)); 
        # 转移次数(语言是否在推进)
        ntr=sum(1 for a,b in zip(seq,seq[1:]) if a!=b)
        mx=1;c=1
        for a,b in zip(seq,seq[1:]):
            c=c+1 if a==b else 1; mx=max(mx,c)
        print("  eps=%-5.2f 步数=%-6d 符号=%2d/%d  转移=%4d次  最长停滞=%4d步"
              %(EPS,STEPS,u,K,ntr,mx))
    print()
print("含义: 若步数够长, 符号数和转移数应该涨 — 那说明闭环没死, 只是尺度过大")
