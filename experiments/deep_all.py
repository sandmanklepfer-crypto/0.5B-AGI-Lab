# -*- coding: utf-8 -*-
"""deep_all.py — 把能用的机制全上, 测【深度推理】到底提升多少
   深度推理 = 需要多步、且每步依赖上一步的任务
"""
import math,random,time
from collections import Counter,defaultdict
import numpy as np
t0=time.time()

# ============ 任务: 深度组合推理 ============
# 给 a, 要算 f^n(a)  (n 步复合), 训练见 n=1,2 测 n=5,8  -> 真深度外推
import itertools
def make_task(op='add3'):
    if op=='add3':
        f=lambda x:(x+3)%32
    else:
        f=lambda x:(x*3+1)%32
    X=[];Y=[]
    for a in range(32):
        for n in [1,2]:
            y=a
            for _ in range(n): y=f(y)
            v=np.zeros(32); v[a]=1
            X.append(v); Y.append(y)
    Xte=[];Yte=[]
    for a in range(32):
        for n in [5,8]:
            y=a
            for _ in range(n): y=f(y)
            v=np.zeros(32); v[a]=1
            Xte.append(v); Yte.append(y)
    return np.array(X),np.array(Y),np.array(Xte),np.array(Yte),f

def layer(kind,D,steps,rho,seed=0):
    r=np.random.RandomState(seed)
    act={'tanh':np.tanh,'linear':lambda z:z,'sin':np.sin,'relu':lambda z:np.maximum(z,0)}[kind]
    W=r.randn(32,D)/np.sqrt(32)
    if kind=='linear':
        R=r.randn(D,D)*rho
    else:
        R=r.randn(D,D); R=R*(rho/max(abs(np.linalg.eigvals(R)).max(),1e-9))
    def phi(X):
        H=act(X@W)
        for _ in range(steps): H=act(H@R.T)
        return H
    return phi

# ============ 各种机制 ============
def m_pca(Xtr,k=8):
    U,S,Vt=np.linalg.svd(Xtr-Xtr.mean(0),full_matrices=False)
    return (Xtr-Xtr.mean(0))@Vt[:k].T,(lambda X:(X-Xtr.mean(0))@Vt[:k].T)
def m_ring_ensemble(Xtr,D=32,eps=0.5,seed=0):
    """ring 耦合集成 (今天测出的最优耦合)"""
    r=np.random.RandomState(seed)
    W1=r.randn(32,D)/np.sqrt(32); W2=r.randn(32,D)/np.sqrt(32)
    W3=r.randn(32,D)/np.sqrt(32); W4=r.randn(32,D)/np.sqrt(32)
    def phi(X):
        h1=np.tanh(X@W1); h2=np.tanh(X@W2); h3=np.tanh(X@W3); h4=np.tanh(X@W4)
        for _ in range(3):
            m=(h1+h2+h3+h4)/4
            h1=0.5*np.tanh(h1)+0.5*m; h2=0.5*np.tanh(h2)+0.5*m
            h3=0.5*np.tanh(h3)+0.5*m; h4=0.5*np.tanh(h4)+0.5*m
        return np.hstack([h1,h2,h3,h4])
    return phi

def evaluate(name,phi,Xtr,Ytr,Xte,Yte,k=32):
    A=phi(Xtr);B=phi(Xte)
    if k==32:
        W=np.linalg.lstsq(np.hstack([A,np.ones((len(A),1))]),Ytr,rcond=None)[0]
        P=np.round(np.hstack([B,np.ones((len(B),1))])@W).astype(int)%32
    return (P==Yte).mean()

print("="*92)
print("★ 全机制上阵: 深度推理 (f^n, 训练n=1,2 测 n=5,8)")
print("="*92)
print()
for op in ['add3','mul3']:
    Xtr,Ytr,Xte,Yte,f=make_task(op)
    print(f"  【任务 {op}】 训练 n=1,2 | 测试 n=5,8   (随机=1/32=0.031)")
    print(f"  {'机制':<34}{'n=5':<10}{'n=8':<10}{'平均'}")
    print("  "+"-"*64)
    res={}
    # 1 裸线性
    r=evaluate('裸线性',lambda X:X,Xtr,Ytr,Xte,Yte)
    print(f"  {'① 裸线性(直通)':<34}{r:<10.3f}{r:<10.3f}{r:.3f}")
    # 2 循环
    for s in [2,4]:
        phi=layer('tanh',64,s,0.9)
        r=evaluate('rnn',phi,Xtr,Ytr,Xte,Yte)
        print(f"  {f'② 循环 tanh 步={s}':<34}{r:<10.3f}{r:<10.3f}{r:.3f}")
    # 3 ring 集成
    phi=m_ring_ensemble(Xtr)
    r=evaluate('ring',phi,Xtr,Ytr,Xte,Yte)
    print(f"  {'③ ring耦合集成(x4)':<34}{r:<10.3f}{r:<10.3f}{r:.3f}")
    # 4 ring + 循环
    def phi2(X):
        H=layer('tanh',64,3,0.9)(X)
        return np.tanh(H)
    r=evaluate('r',phi2,Xtr,Ytr,Xte,Yte)
    print(f"  {'④ 循环+非线性':<34}{r:<10.3f}{r:<10.3f}{r:.3f}")
    print()
print(f"用时 {time.time()-t0:.2f}s")
