#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""brain_rich.py — 终点诊断: 桥没问题, 脑太单调"""
import numpy as np
D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
SIG = np.tanh
H, K = 32, 16

def renorm(A, r):
    w=np.abs(np.linalg.eigvals(A)).max(); return A*(r/max(w,1e-9))
def brain_step(A,X,F,E,inj=None,G0=0.35,RHO=0.02,MU=1.8):
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
def traj(A,steps=8000,seed=99,G0=0.35,RHO=0.02,MU=1.8):
    X=(np.random.RandomState(seed).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4)
    tr=[]
    for t in range(steps):
        X,F,E=brain_step(A,X,F,E,None,G0,RHO,MU); tr.append(X[:,0].copy())
    return np.array(tr)
def metrics(tr):
    mv=float(np.linalg.norm(np.diff(tr,axis=0),axis=1).mean())
    ns=tr[-2000:]
    w=np.clip(np.linalg.eigvalsh(np.cov(ns.T)),0,None)
    ed=float((w.sum()**2)/max((w**2).sum(),1e-12))
    sub=ns[::30]
    Dm=np.linalg.norm(sub[:,None,:]-sub[None,:,:],axis=2)
    i=np.arange(len(sub)); mask=np.abs(i[:,None]-i[None,:])>5
    nov=float(np.where(mask,Dm,np.inf).min(1).mean())/(np.linalg.norm(sub,axis=1).mean()+1e-9)
    return mv,ed,nov

rng=np.random.RandomState(0); A0=renorm(rng.randn(D,D),0.98)
print("="*100); print("终点诊断: 桥没问题, 脑太单调"); print("="*100)
print("\n[① 裸脑自由跑8000步: 状态能分成几个符号?]")
B=train_bridge(init_bridge(K), traj(A0,2000)[::5].T, iters=500)
tr=traj(A0,8000); lg,_=enc(B,tr.T); seq=lg.argmax(0)
mv,ed,nov=metrics(tr)
print("  裸脑 运动=%.5f 有效维=%.1f 新奇=%.3f"%(mv,ed,nov))
print("  → 8000步中用了 %d/%d 个符号"%(len(set(seq.tolist())),K))
cnt=np.bincount(seq,minlength=K)/len(seq)
print("  符号分布: "+" ".join("%.2f"%c for c in cnt))
print("\n[② 扫脑参数: 谁能把新奇度顶上去?]")
best=None
for rho in [0.90,0.98,1.05,1.15]:
    for MU in [0.5,1.8,3.5]:
        for G0 in [0.15,0.35,0.6]:
            A=renorm(A0,rho); tr=traj(A,4000,G0=G0,MU=MU)
            mv,ed,nov=metrics(tr); lg,_=enc(B,tr.T); sq=lg.argmax(0); ns_=len(set(sq.tolist()))
            if best is None or nov>best[0]: best=(nov,rho,MU,G0,ed,mv,ns_)
print("  ★ 最丰富: rho=%.2f MU=%.1f G0=%.2f → 有效维=%.1f 新奇=%.3f 运动=%.5f 符号=%d/%d"
      %(best[1],best[2],best[3],best[4],best[0],best[5],best[6],K))
print("  基线  : rho=0.98 MU=1.8 G0=0.35 → 有效维=1.7 新奇=0.143")
print("\n[③ 细扫 rho (新奇的相变点)]")
print("  %-6s %-8s %-10s %-9s %-9s %s"%("rho","有效维","运动","新奇","符号数",""))
for rho in [0.95,0.98,1.02,1.06,1.10,1.15,1.20,1.30]:
    A=renorm(A0,rho); tr=traj(A,4000,G0=best[3],MU=best[2])
    mv,ed,nov=metrics(tr); lg,_=enc(B,tr.T); sq=lg.argmax(0); n_=len(set(sq.tolist()))
    star="★" if nov>0.3 else ""
    print("  %-6.2f %-8.1f %-10.5f %-9.3f %-9s %s"%(rho,ed,mv,nov,"%d/%d"%(n_,K),star))
