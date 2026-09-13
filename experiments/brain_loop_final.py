#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_loop_final.py — 完整闭环 · 最终版
=========================================
综合前三版的所有结论:
  ① 脑: 非对称自持核 (f 永不接收梯度)
  ② 桥: 非线性编解码 + 离散符号瓶颈 (梯度只到这里)
  ③ 内化: 极弱剂量 (eps<=0.05), 走连续状态通道
  ④ 前提: 脑的状态必须有【低维结构】, 语言才能说出它

闭环三层:
   脑 --x--> 桥 --符号--> 嘴(语言)
    ^                      |
    +---- 内化回流(弱) ------+
"""
import numpy as np

D, DT = 24, 0.05
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8
SIG = np.tanh
H, K = 32, 16
EPS = 0.05                 # 内化强度: 极弱(前测证明 >0.2 会削弱生命)

def renorm(A, r=0.98):
    w = np.abs(np.linalg.eigvals(A)).max(); return A * (r / max(w, 1e-9))

def brain_step(A, X, F, E, inj=None):
    act = SIG(X)
    F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
    g = E / (KAPPA + E)
    core = A @ act - MU * F * X
    if inj is not None: core = core + inj
    X = X + DT * (g * core - G0 * X)
    E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
    return X, F, E

def init_bridge(K, seed=1):
    r = np.random.RandomState(seed)
    return dict(W1=r.randn(H, D)/np.sqrt(D), b1=np.zeros(H),
                W2=r.randn(K, H)/np.sqrt(H), b2=np.zeros(K),
                Wd=r.randn(D, K)/np.sqrt(K), bd=np.zeros(D))

def enc(B, X):
    Hh = np.tanh(B['W1'] @ X + B['b1'][:, None])
    return B['W2'] @ Hh + B['b2'][:, None], Hh

def softmax(z):
    z = z - z.max(0, keepdims=True); p = np.exp(z); return p/p.sum(0, keepdims=True)

def train_bridge(B, Xall, iters=400, lr=0.01):
    M = Xall.shape[1]
    B = {k: v.copy() for k, v in B.items()}
    ms = {k: np.zeros_like(v) for k, v in B.items()}
    vs = {k: np.zeros_like(v) for k, v in B.items()}
    for it in range(iters+1):
        lg, Hh = enc(B, Xall); P = softmax(lg)
        Xd = B['Wd'] @ P + B['bd'][:, None]
        dX = 2.0*(Xd - Xall)/M
        G = dict(Wd=dX @ P.T, bd=dX.sum(1))
        dP = B['Wd'].T @ dX
        dlg = P*(dP - (dP*P).sum(0, keepdims=True))
        G['W2'] = dlg @ Hh.T; G['b2'] = dlg.sum(1)
        dpre = (B['W2'].T @ dlg)*(1 - Hh**2)
        G['W1'] = dpre @ Xall.T; G['b1'] = dpre.sum(1)
        for k in B:
            ms[k]=0.9*ms[k]+0.1*G[k]; vs[k]=0.999*vs[k]+0.001*(G[k]**2)
            B[k] -= lr*(ms[k]/(1-0.9**(it+1)))/(np.sqrt(vs[k]/(1-0.999**(it+1)))+1e-8)
    return B

def self_err(B, X):
    lg,_ = enc(B, X); idx = lg.argmax(0)
    S = np.zeros((lg.shape[0], X.shape[1])); S[idx, np.arange(X.shape[1])] = 1.0
    Xd = B['Wd'] @ S + B['bd'][:, None]
    return float(np.linalg.norm(Xd - X)/np.linalg.norm(X))

def writeup(B, X):
    lg,_ = enc(B, X); return lg.argmax(0)

def life(A, B=None, W_in=None, eps=0.0, steps=4000, seed=99, mode='P', nstart=None):
    X0 = (nstart if nstart is not None else np.random.RandomState(seed).randn(D,1)*0.5)
    X = X0.copy(); F = np.zeros_like(X); E = np.full((1, X.shape[1]), 0.4); tr=[]
    for t in range(steps):
        inj = None
        if B is not None and eps>0:
            lg,_ = enc(B, X); P = softmax(lg)
            inj = eps*(W_in @ (P if mode=='P' else np.eye(K)[lg.argmax(0)].T))
        X, F, E = brain_step(A, X, F, E, inj)
        tr.append(X[:,0].copy())
    tr = np.array(tr)
    motion = float(np.linalg.norm(np.diff(tr,axis=0),axis=1).mean())
    ns = tr[-1500:]
    w = np.clip(np.linalg.eigvalsh(np.cov(ns.T)),0,None)
    effdim = float((w.sum()**2)/max((w**2).sum(),1e-12))
    sub = ns[::25]
    Dm = np.linalg.norm(sub[:,None,:]-sub[None,:,:],axis=2)
    i=np.arange(len(sub)); mask=np.abs(i[:,None]-i[None,:])>5
    nov = float(np.where(mask,Dm,np.inf).min(1).mean())/(np.linalg.norm(sub,axis=1).mean()+1e-9)
    return motion, effdim, nov

def death(A,B=None,W_in=None,eps=0.0,steps=5000,cut=1200,mode='P'):
    X0 = np.random.RandomState(5).randn(D,32)*0.5
    X=X0.copy(); F=np.zeros_like(X); E=np.full((1,32),0.4); post=[]
    for t in range(steps):
        inj=None
        if B is not None and eps>0:
            lg,_=enc(B,X); P=softmax(lg)
            inj = eps*(W_in @ (P if mode=='P' else np.eye(K)[lg.argmax(0)].T))
        et = 0.0 if t>=cut else ETA
        act=SIG(X); F=np.clip(F+DT*RHO*(act**2-F),0,2); g=E/(KAPPA+E)
        core = A@act - MU*F*X
        if inj is not None: core = core + inj
        X = X + DT*(g*core - G0*X)
        E = np.maximum(E+DT*(et*(act**2).sum(0,keepdims=True)-GAMMA*E),0.0)
        if t>=cut: post.append(np.linalg.norm(X,axis=0).mean())
    return float(np.mean(post[-50:]))

# ==================== 主实验 ====================
rng = np.random.RandomState(0)
A = renorm(rng.randn(D,D))
W_in = rng.randn(D,K)/np.sqrt(K)
U = np.random.RandomState(2).randn(3,D)          # 脑状态所在的3维流形
Wm = np.random.RandomState(3).randn(D,3)          # 把流形坐标映到脑状态

def make_struct_X(n, seed):
    r = np.random.RandomState(seed)
    Z = r.randn(3,n)                               # 低维结构坐标
    return (Wm @ Z), Z                             # (D,n), (3,n)

Xtr,_ = make_struct_X(96,11)
Xte,_ = make_struct_X(48,12)

print("="*96)
print("完整闭环 · 最终版 | 脑D=%d(自持核) | 桥(%d符号,梯度只到这) | 内化eps=%.2f(极弱)"%(D,K,EPS))
print("="*96)

X0 = np.random.RandomState(99).randn(D,1)*0.5
m0,e0,n0 = life(A, nstart=X0)
q0 = death(A)
print("\n[基线] 裸脑: 运动=%.5f 有效维=%.1f 新奇=%.3f | 断流后|x|=%.4f %s"
      %(m0,e0,n0,q0,"真死✅" if q0<0.02 else "没死❌"))
base_err = float(np.linalg.norm(Xte-Xte.mean(1,keepdims=True))/np.linalg.norm(Xte))
print("        自表达基线(啥都不说)=%.4f"%base_err)

print("\n[阶段1] 训桥 (脑冻结, 梯度只到桥)...")
B = train_bridge(init_bridge(K), Xtr, iters=500, lr=0.01)
er_open = self_err(B, Xte)
print("  开环自表达误差=%.4f  (相对基线 %.2fx)  %s"%(er_open, er_open/base_err,
      "✅能说出自己" if er_open<base_err else "❌"))

print("\n[阶段2] 闭环内化 (s回流脑, 仍只训桥, eps=%.2f)..."%EPS)
Bc = {k:v.copy() for k,v in B.items()}
for it in range(4):
    Xs=[]
    Xc=Xtr.copy(); Fc=np.zeros_like(Xc); Ec=np.full((1,Xc.shape[1]),0.4)
    for t in range(8):
        lg,_=enc(Bc,Xc); P=softmax(lg)
        Xc,Fc,Ec = brain_step(A,Xc,Fc,Ec, EPS*(W_in@P))
        Xs.append(Xc.copy())
    Bc = train_bridge(Bc, np.concatenate(Xs,1), iters=100, lr=0.008)
Xte_c=[]; Xc=Xte.copy(); Fc=np.zeros_like(Xc); Ec=np.full((1,Xc.shape[1]),0.4)
for t in range(8):
    lg,_=enc(Bc,Xc); P=softmax(lg)
    Xc,Fc,Ec = brain_step(A,Xc,Fc,Ec, EPS*(W_in@P)); Xte_c.append(Xc.copy())
Xte_c=np.concatenate(Xte_c,1)
er_cl = self_err(Bc, Xte_c)
print("  闭环自表达误差=%.4f  (相对基线 %.2fx)  %s"%(er_cl, er_cl/base_err,
      "✅闭环没退化" if er_cl<base_err*1.1 else "❌闭环退化"))

print("\n[闭环后] 脑还活着吗?")
m1,e1,n1 = life(A,Bc,W_in,EPS,nstart=X0)
q1 = death(A,Bc,W_in,EPS)
print("  闭环脑: 运动=%.5f 有效维=%.1f 新奇=%.3f (保留 %.0f%%)"%(m1,e1,n1,100*n1/n0))
print("  断流即死: 后段|x|=%.4f  %s"%(q1,"真死✅" if q1<0.02 else "没死❌"))

print("\n[扫描] 词表大小 K → 自表达能力 (有结构的脑)")
print("  %-6s %-14s %-14s %s"%("K","自表达误差","相对基线","判断"))
print("  %-6s %-14.4f %-14s %s"%("(不说)",base_err,"1.00","参照"))
for kk in [2,4,8,16,32,64]:
    Bk = train_bridge(init_bridge(kk), Xtr, iters=500, lr=0.01)
    er = self_err(Bk, Xte)
    print("  %-6d %-14.4f %-14.2f %s"%(kk,er,er/base_err,"✅" if er<base_err else "❌"))

print("\n[说出的话] 闭环脑跑60步, 逐帧说出符号")
X = (np.random.RandomState(77).randn(D,1)*0.5); F=np.zeros_like(X); E=np.full((1,1),0.4)
seq=[]
for t in range(60):
    lg,_=enc(Bc,X); idx=int(lg.argmax(0)[0]); seq.append(idx)
    P=softmax(lg)
    X,F,E = brain_step(A,X,F,E, EPS*(W_in@P))
print("  "+" ".join("%X"%s for s in seq))
print("  用了 %d/%d 个符号"%(len(set(seq)),K))
tr=np.zeros((K,K))
for x,y in zip(seq[:-1],seq[1:]): tr[x,y]+=1
nz=(tr.sum(1)>0)
print("  非零转移行: %d/%d"%(nz.sum(),K))
