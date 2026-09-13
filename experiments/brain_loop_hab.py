#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_loop_hab.py — 闭环的关键缺失: 内化项必须有「习惯化」
===========================================================
发现: 闭环成立后, 脑停住了(60步全说同一个符号, 只用1/16词)
诊断: 自反馈 = 自我强化 → 不动点。内化项绕过了脑的疲劳机制。
生物机制: 习惯化(habituation) — 持续刺激被自动调低。

对照三组 (都在 eps=0.05 弱剂量下):
  N 无习惯化      inj = eps*W_in@P                  ← 上一版, 会停住
  H 习惯化        inj 乘上慢适应变量 (被持续刺激则衰减)
  D 延迟内化      用 t-τ 时刻的符号 (避免即时自强化)
指标: 符号多样性 / 自表达误差 / 脑新奇度 / 断流即死
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H, K, EPS = 32, 16, 0.05
RHO_H, BETA_H = 0.01, 3.0        # 习惯化: 时间尺度 / 强度

def renorm(A, r=0.98):
    w=np.abs(np.linalg.eigvals(A)).max(); return A*(r/max(w,1e-9))
def brain_step(A,X,F,E,inj=None):
    act=SIG(X); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
    core=A@act-MU*F*X
    if inj is not None: core=core+inj
    X=X+DT*(g*core-G0*X)
    E=np.maximum(E+DT*(ETA*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
    return X,F,E
def init_bridge(K,seed=1):
    r=np.random.RandomState(seed)
    return dict(W1=r.randn(H,D)/np.sqrt(D),b1=np.zeros(H),
                W2=r.randn(K,H)/np.sqrt(H),b2=np.zeros(K),
                Wd=r.randn(D,K)/np.sqrt(K),bd=np.zeros(D))
def enc(B,X):
    Hh=np.tanh(B['W1']@X+B['b1'][:,None]); return B['W2']@Hh+B['b2'][:,None],Hh
def softmax(z):
    z=z-z.max(0,keepdims=True); p=np.exp(z); return p/p.sum(0,keepdims=True)
def train_bridge(B,Xall,iters=400,lr=0.01):
    M=Xall.shape[1]; B={k:v.copy() for k,v in B.items()}
    ms={k:np.zeros_like(v) for k,v in B.items()}; vs={k:np.zeros_like(v) for k,v in B.items()}
    for it in range(iters+1):
        lg,Hh=enc(B,Xall); P=softmax(lg); Xd=B['Wd']@P+B['bd'][:,None]
        dX=2.0*(Xd-Xall)/M
        G=dict(Wd=dX@P.T,bd=dX.sum(1))
        dP=B['Wd'].T@dX; dlg=P*(dP-(dP*P).sum(0,keepdims=True))
        G['W2']=dlg@Hh.T; G['b2']=dlg.sum(1)
        dpre=(B['W2'].T@dlg)*(1-Hh**2); G['W1']=dpre@Xall.T; G['b1']=dpre.sum(1)
        for k in B:
            ms[k]=0.9*ms[k]+0.1*G[k]; vs[k]=0.999*vs[k]+0.001*(G[k]**2)
            B[k]-=lr*(ms[k]/(1-0.9**(it+1)))/(np.sqrt(vs[k]/(1-0.999**(it+1)))+1e-8)
    return B
def self_err(B,X):
    lg,_=enc(B,X); idx=lg.argmax(0)
    S=np.zeros((lg.shape[0],X.shape[1])); S[idx,np.arange(X.shape[1])]=1.0
    Xd=B['Wd']@S+B['bd'][:,None]
    return float(np.linalg.norm(Xd-X)/np.linalg.norm(X))

rng=np.random.RandomState(0)
A=renorm(rng.randn(D,D)); W_in=rng.randn(D,K)/np.sqrt(K)
Wm=np.random.RandomState(3).randn(D,3)
def struct(n,seed): return Wm@np.random.RandomState(seed).randn(3,n)
Xtr=struct(96,11); Xte=struct(48,12)
base_err=float(np.linalg.norm(Xte-Xte.mean(1,keepdims=True))/np.linalg.norm(Xte))

B=train_bridge(init_bridge(K),Xtr,iters=500,lr=0.01)
print("="*92)
print("闭环 · 习惯化对照 | 桥已训好(自表达误差=%.4f, 基线=%.4f)"%(self_err(B,Xte),base_err))
print("="*92)

def run_closed(mode, steps=120, seed=77):
    X=(np.random.RandomState(seed).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4)
    Ah=np.zeros_like(X)          # 习惯化变量
    hist=[]; seq=[]; tr=[]
    for t in range(steps):
        lg,_=enc(B,X); P=softmax(lg); idx=int(lg.argmax(0)[0])
        s = P if mode!='D' else (tr[-3] if len(tr)>=3 else P)
        inj = EPS*(W_in@s)
        if mode=='H':
            inj = inj*np.exp(-BETA_H*Ah)         # 习惯化: 被习惯则衰减
            Ah = Ah + DT*RHO_H*(np.abs(inj)/(EPS+1e-9) - Ah)
        X,F,E = brain_step(A,X,F,E,inj)
        hist.append(X[:,0].copy()); seq.append(idx); tr.append(P.copy())
    hist=np.array(hist)
    ns=hist[-90:]
    sub=ns[::6]
    Dm=np.linalg.norm(sub[:,None,:]-sub[None,:,:],axis=2)
    i=np.arange(len(sub)); mask=np.abs(i[:,None]-i[None,:])>3
    nov=float(np.where(mask,Dm,np.inf).min(1).mean())/(np.linalg.norm(sub,axis=1).mean()+1e-9)
    uniq=len(set(seq[-60:])); 
    # 单符号最长连续
    mx=1;c=1
    for a,b in zip(seq,seq[1:]):
        c=c+1 if a==b else 1; mx=max(mx,c)
    return nov, uniq, mx, seq

print("\n%-14s %-16s %-16s %-16s"%("内化方式","符号多样性","最长停滞","脑新奇度"))
for mode,name in [('N','无习惯化'),('H','★习惯化'),('D','延迟内化')]:
    nov,uniq,mx,seq=run_closed(mode)
    print("%-14s %-16s %-16s %-16s"%(name,"%d/%d 个符号"%(uniq,K),"%d 步"%mx,"%.3f"%nov))

print("\n[说不出的话] 三种方式的符号序列 (前50步)")
for mode,name in [('N','无习惯化'),('H','★习惯化'),('D','延迟内化')]:
    _,_,_,seq=run_closed(mode)
    print("  %-10s "%name+" ".join("%X"%s for s in seq[:50]))

print("\n[闭环后脑状态]")
for mode,name in [('N','无习惯化'),('H','★习惯化')]:
    X=(np.random.RandomState(77).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4)
    Ah=np.zeros_like(X); trhist=[]
    for t in range(2500):
        lg,_=enc(B,X); P=softmax(lg)
        inj=EPS*(W_in@P)
        if mode=='H':
            inj=inj*np.exp(-BETA_H*Ah); Ah=Ah+DT*RHO_H*(np.abs(inj)/(EPS+1e-9)-Ah)
        X,F,E=brain_step(A,X,F,E,inj); trhist.append(X[:,0].copy())
    trhist=np.array(trhist); ns=trhist[-1000:]
    w=np.clip(np.linalg.eigvalsh(np.cov(ns.T)),0,None)
    ed=float((w.sum()**2)/max((w**2).sum(),1e-12))
    mv=float(np.linalg.norm(np.diff(trhist,axis=0),axis=1).mean())
    print("  %-10s 运动=%.5f 有效维=%.1f"%(name,mv,ed))
