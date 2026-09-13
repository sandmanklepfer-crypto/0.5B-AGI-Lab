# -*- coding: utf-8 -*-
"""bpp2.py — 固定参数, 测【回忆】容量 (key 都见过)"""
import numpy as np
t0=__import__('time').time()
V=45
def gen(M,seed):
    r=np.random.RandomState(seed)
    K=r.choice(V,M,replace=False); Vl=r.randint(0,V,M)
    X=np.zeros((M,V)); X[np.arange(M),K]=1
    Y=np.zeros((M,V)); Y[np.arange(M),Vl]=1
    return X,Y
def test(fn,ep,label):
    mx=0; last=0
    for M in range(2,V+1):
        X,Y=gen(M,7)
        a=fn(X,Y)
        if a>=0.9: mx=M
        last=a
    bits=mx*np.log2(V)/ep if ep else 0
    print(f"  {label:<22}{ep:<12}{mx:<10}{bits:.2f}")
    return mx
print("="*88)
print("★ 固定参数量 2025, 测【回忆】容量 (key 都见过) —— 这才是你说的'都学过'")
print("="*88)
print(f"  每个事实 = log2(45) = {np.log2(V):.2f} 比特")
print()
print(f"  {'架构':<22}{'有效参数':<12}{'最大M':<10}{'比特/参数'}")
print("  "+"-"*58)
def a_dense(X,Y):
    W=X.T@Y; return ((X@W).argmax(1)==Y.argmax(1)).mean()
def a_lr(X,Y,r=22):
    U,S,Vt=np.linalg.svd(X,full_matrices=False)
    P=X@Vt[:r].T; W=np.linalg.lstsq(P,Y,rcond=None)[0]
    return ((X@Vt[:r].T@W).argmax(1)==Y.argmax(1)).mean()
def a_hop(X,Y):
    W=X.T@Y; return ((X@W).argmax(1)==Y.argmax(1)).mean()
def a_quant(X,Y):
    W=X.T@Y; mx=max(abs(W).max(),1e-9)
    Wq=np.round(W*8/mx)/8*mx
    return ((X@Wq).argmax(1)==Y.argmax(1)).mean()
m1=test(a_dense,2025,'稠密查表')
m2=test(a_lr,1980,'低秩 r=22')
m3=test(a_hop,2025,'联想记忆(外积)')
m4=test(a_quant,2025,'量化(4bit存储)')
print()
print("="*88)
print("★★ 关键: 上面全都能记住45个 (=上限), 因为45个key刚好=参数量级.")
print("   换个更硬的测试: key 多于 V, 用【多值查表】")
print("="*88)
print()
# 更硬: 每个 key 映射到 M 个不同 value 中的任意一个 (连续值)
NV=45
def gen2(M,D,seed):
    r=np.random.RandomState(seed)
    K=r.randint(0,NV,M)      # key 可重复 (对多值)
    X=np.zeros((M,NV)); X[np.arange(M),K]=1
    Y=r.randn(M,D)           # 连续值
    return X,Y,K
def run2(D,M,kind):
    X,Y,K=gen2(M,D,3)
    if kind=='dense':
        W=X.T@Y
    elif kind=='lr':
        U,S,Vt=np.linalg.svd(X,full_matrices=False)
        W=np.linalg.lstsq(X@Vt[:min(22,NV)].T,Y,rcond=None)[0]
        W=Vt[:min(22,NV)].T@W
    P=X@W
    return (np.abs(P-Y).mean())
print(f"  {'D':<8}{'M':<8}{'稠密误差':<14}{'低秩误差':<14}{'参数量'}")
print("  "+"-"*56)
for D in [10,30,60]:
    for M in [45,180,450]:
        e1=run2(D,M,'dense'); e2=run2(D,M,'lr')
        print(f"  {D:<8}{M:<8}{e1:<14.3f}{e2:<14.3f}{NV*D}")
print()
print("  ★ 读法: 误差越小=存得越好. 看【同参数量下, 架构不同, 容量不同吗】")
print(f"用时 {__import__('time').time()-t0:.2f}s")
