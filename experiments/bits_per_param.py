# -*- coding: utf-8 -*-
"""bits_per_param.py — 固定参数量, 不同架构, 能存多少比特的知识?"""
import numpy as np
t0=__import__('time').__import__('time') if False else __import__('time').time()
V=45            # 词表
N_FIX=2025      # 参数预算 (45*45)
M_list=[200,400,800,1200,1800]
print("="*92)
print("★ 固定参数量, 测每种架构的【知识容量】(比特/参数)")
print("="*92)
print(f"  参数预算: {N_FIX}  词表: {V}  每个事实携带 log2({V})={np.log2(V):.2f} 比特")
print()

def gen(M,seed):
    r=np.random.RandomState(seed)
    K=r.choice(V,M,replace=False); Vl=r.randint(0,V,M)
    X=np.zeros((M,V)); X[np.arange(M),K]=1
    Y=np.zeros((M,V)); Y[np.arange(M),Vl]=1
    return X,Y,K,Vl

def acc_dense(Xtr,Ytr,Xte,Yte,Kte,Vte):
    # 稠密查表: W = X^T Y  (线性关联)
    W=Xtr.T@Ytr
    P=(Xte@W).argmax(1)
    return (P==Vte).mean(), V*V

def acc_lowrank(Xtr,Ytr,Xte,Yte,Kte,Vte,r):
    # 低秩: 先降维再读出
    U,S,Vt=np.linalg.svd(Xtr,full_matrices=False)
    Proj=Xtr@Vt[:r].T
    W=np.linalg.lstsq(Proj,Ytr,rcond=None)[0]
    P=(Xte@Vt[:r].T@W).argmax(1)
    return (P==Vte).mean(), 2*V*r

def acc_hopfield(Xtr,Ytr,Xte,Yte,Kte,Vte):
    # 联想记忆: 归一化外积
    Xn=Xtr/ (np.linalg.norm(Xtr,axis=1,keepdims=True)+1e-9)
    W=np.zeros((V,V))
    for i in range(len(Xn)):
        W+=np.outer(Xn[i],Ytr[i])
    P=(Xte@W).argmax(1)
    return (P==Vte).mean(), V*V

def acc_quant(Xtr,Ytr,Xte,Yte,Kte,Vte,levels=16):
    # 量化: 存4bit, 但同样N预算 -> 能存4倍多的格
    W=Xtr.T@Ytr
    Wq=np.round(W*levels/max(abs(W).max(),1e-9))/levels*max(abs(W).max(),1e-9)
    P=(Xte@Wq).argmax(1)
    return (P==Vte).mean(), V*V/4   # 有效参数只有1/4

print(f"  {'M(事实数)':<12}{'稠密':<12}{'低秩r=22':<12}{'联想记忆':<12}{'量化4bit'}")
print("  "+"-"*64)
for M in M_list:
    if M>V: M2=V   # 最多V个不重复key
    else: M2=M
    Xtr,Ytr,Ktr,Vtr=gen(int(M2*0.7),1)
    Xte,Yte,Kte,Vte=gen(int(M2*0.3),2)
    row=[]
    row.append(f"{acc_dense(Xtr,Ytr,Xte,Yte,Kte,Vte)[0]:.3f}")
    row.append(f"{acc_lowrank(Xtr,Ytr,Xte,Yte,Kte,Vte,22)[0]:.3f}")
    row.append(f"{acc_hopfield(Xtr,Ytr,Xte,Yte,Kte,Vte)[0]:.3f}")
    row.append(f"{acc_quant(Xtr,Ytr,Xte,Yte,Kte,Vte)[0]:.3f}")
    print(f"  {M2:<12}" + "".join(f"{x:<12}" for x in row))

print()
print("="*92)
print("★ 容量上限: 固定 2025 参数, 最多能存多少事实 (容忍90%正确)")
print("="*92)
print()
print(f"  {'架构':<20}{'有效参数':<12}{'最大M':<10}{'比特/参数'}")
print("  "+"-"*56)
for nm,fn,ep in [('稠密查表',acc_dense,2025),('低秩r=22',lambda *a: acc_lowrank(*a,22),1980),
                 ('联想记忆',acc_hopfield,2025),('量化4bit',acc_quant,506)]:
    mx=0
    for M in range(5,V+1,2):
        Xtr,Ytr,Ktr,Vtr=gen(int(M*0.7),1); Xte,Yte,Kte,Vte=gen(int(M*0.3),2)
        if Xte.shape[0]==0: break
        a=fn(Xtr,Ytr,Xte,Yte,Kte,Vte)[0]
        if a>=0.9: mx=M
    bits=mx*np.log2(V)/ep
    print(f"  {nm:<20}{ep:<12}{mx:<10}{bits:.2f}")
print()
print(f"用时 {__import__('time').time()-t0:.2f}s")
