# -*- coding: utf-8 -*-
"""brute_arch.py — 固定参数, 穷举几十种动力学/架构, 看谁能提升【组合推理】"""
import numpy as np
t0=__import__('time').time()
n=10; D=64; TRI=40
# ★ 任务: (a+b) mod 10  ——  训练只给 (a,0) 和 (0,b), 测试全组合
rng=np.random.RandomState(0)
def onehot_tr():
    X=[];Y=[]
    for a in range(n):
        for b in range(n):
            if b==0 or a==0:
                v=np.zeros(2*n); v[a]=1; v[n+b]=1
                X.append(v); Y.append((a+b)%n)
    return np.array(X),np.array(Y)
def onehot_te():
    X=[];Y=[]
    for a in range(n):
        for b in range(n):
            if not(b==0 or a==0):
                v=np.zeros(2*n); v[a]=1; v[n+b]=1
                X.append(v); Y.append((a+b)%n)
    return np.array(X),np.array(Y)
Xtr,Ytr=onehot_tr(); Xte,Yte=onehot_te()

def build(kind, rho, steps, seed):
    r=np.random.RandomState(seed)
    W=r.randn(2*n,D)/np.sqrt(2*n)
    R=r.randn(D,D); R=R*(rho/max(abs(np.linalg.eigvals(R)).max(),1e-9))
    def act(z):
        if kind=='linear': return z
        if kind=='tanh': return np.tanh(z)
        if kind=='sin': return np.sin(z)
        if kind=='relu': return np.maximum(z,0)
        if kind=='silu': return z/(1+np.exp(-z))
        if kind=='sign': return np.sign(z)
        if kind=='norm': return z/(np.linalg.norm(z,axis=1,keepdims=True)+1e-9)
        return np.tanh(z)
    def phi(X):
        H=act(X@W)
        for _ in range(steps):
            H=act(H@R.T)
        return H
    return phi

def ev(kind,rho,steps,seed=0):
    phi=build(kind,rho,steps,seed)
    A=phi(Xtr); B=phi(Xte)
    Am=np.hstack([A,np.ones((len(A),1))]); Bm=np.hstack([B,np.ones((len(B),1))])
    W=np.linalg.lstsq(Am,np.eye(n)[Ytr],rcond=None)[0]
    P=(Bm@W).argmax(1)
    return (P==Yte).mean()

print("="*90)
print("★ 固定参数(64维), 穷举动力学×谱半径×迭代步数 -> 组合推理准确率")
print("="*90)
print(f"  任务: (a+b) mod 10, 训练只见 (a,0)/(0,b), 测试全组合. 随机基线={1/n:.2f}")
print()
KINDS=['linear','tanh','sin','relu','silu','sign','norm']
RHOS=[0.5,0.9,1.0,1.1,1.5]
STEPS=[1,2,4,8]
rows=[]
print(f"  {'动力学':<8}{'ρ':<6}{'步':<5}{'准确率'}")
print("  "+"-"*36)
res=[]
for k in KINDS:
    for rho in RHOS:
        for s in STEPS:
            a=ev(k,rho,s)
            res.append((a,k,rho,s))
res.sort(reverse=True)
for a,k,rho,s in res[:14]:
    print(f"  {k:<8}{rho:<6}{s:<5}{a:.3f}")
print("  ...")
for a,k,rho,s in res[-5:]:
    print(f"  {k:<8}{rho:<6}{s:<5}{a:.3f}")
print()
print(f"  最好: {res[0][1]} ρ={res[0][2]} 步={res[0][3]}  -> {res[0][0]:.3f}")
print(f"  最差: {res[-1][1]} ρ={res[-1][2]} 步={res[-1][3]}  -> {res[-1][0]:.3f}")
print(f"  平均: {sum(x[0] for x in res)/len(res):.3f}")
print(f"  超过随机的: {sum(1 for x in res if x[0]>1/n+0.1)}/{len(res)}")
print(f"用时 {__import__('time').time()-t0:.2f}s")
