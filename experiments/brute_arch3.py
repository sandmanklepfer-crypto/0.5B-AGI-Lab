# -*- coding: utf-8 -*-
"""brute_arch3.py 修正版: 用单值回归, 重新穷举架构"""
import numpy as np
t0=__import__('time').time()
n=10; D=64
Xtr=[];Ytr=[];Xte=[];Yte=[]
for a in range(n):
    for b in range(n):
        v=np.zeros(2*n); v[a]=1; v[n+b]=1
        if b==0 or a==0: Xtr.append(v); Ytr.append((a+b)%n)
        else: Xte.append(v); Yte.append((a+b)%n)
Xtr=np.array(Xtr);Ytr=np.array(Ytr,float);Xte=np.array(Xte);Yte=np.array(Yte,float)

def run(phi):
    A=phi(Xtr);B=phi(Xte)
    Am=np.hstack([A,np.ones((len(A),1))]);Bm=np.hstack([B,np.ones((len(B),1))])
    W=np.linalg.lstsq(Am,Ytr,rcond=1e-6)[0]
    P=np.round(Bm@W).astype(int)%n
    return (P==Yte.astype(int)).mean()

print("="*90)
print("★ 修正: 单值回归下, 重新穷举架构 (任务: (a+b) mod 10 组合外推)")
print("="*90)
print()
def ph_fourier(X):
    a=X[:,:n]@np.arange(n);b=X[:,n:]@np.arange(n);s=a+b
    return np.stack([np.sin(2*np.pi*s/n),np.cos(2*np.pi*s/n),
                     np.sin(2*np.pi*a/n),np.cos(2*np.pi*a/n),
                     np.sin(2*np.pi*b/n),np.cos(2*np.pi*b/n)],1)
def ph_plain(X):
    a=X[:,:n]@np.arange(n);b=X[:,n:]@np.arange(n)
    return np.stack([a,b],1).astype(float)
def ph_oracle(X):
    a=X[:,:n]@np.arange(n);b=X[:,n:]@np.arange(n)
    return np.stack([(a+b)%n],1).astype(float)
print(f"  {'编码':<30}{'准确率'}")
print("  "+"-"*44)
print(f"  {'上界: 直接给 (a+b)%n':<30}{run(ph_oracle):.3f}")
print(f"  {'傅里叶特征(周期结构)':<30}{run(ph_fourier):.3f}")
print(f"  {'裸 a,b':<30}{run(ph_plain):.3f}")
print(f"  {'随机基线':<30}{1/n:.3f}")
print()
print("  —— 神经网络架构 ——")
res=[]
KINDS={'linear':lambda z:z,'tanh':np.tanh,'sin':np.sin,'relu':lambda z:np.maximum(z,0),
       'silu':lambda z:z/(1+np.exp(-z)),'sign':np.sign,'gelu':lambda z:0.5*z*(1+np.tanh(0.797*z))}
for k,act in KINDS.items():
    for rho in [0.5,0.9,1.0,1.1,1.5]:
        for s in [1,2,4,8,16]:
            r=np.random.RandomState(0)
            W=r.randn(2*n,D)/np.sqrt(2*n)
            R=r.randn(D,D);R=R*(rho/max(abs(np.linalg.eigvals(R)).max(),1e-9))
            def phi(X,W=W,R=R,act=act,s=s):
                H=act(X@W)
                for _ in range(s): H=act(H@R.T)
                return H
            res.append((run(phi),k,rho,s))
res.sort(reverse=True)
print(f"  {'最好架构':<30}{res[0][0]:.3f}  ({res[0][1]} ρ={res[0][2]} 步={res[0][3]})")
print(f"  {'平均(175种)':<30}{sum(x[0] for x in res)/len(res):.3f}")
print(f"  {'超过随机(0.1)的':<30}{sum(1 for x in res if x[0]>0.2)}/{len(res)}")
print()
print("="*90)
print("★ 结论 (修正后)")
print("="*90)
print(f"""
  同样的任务, 同样的参数量:

     给对结构 (傅里叶)     -> {run(ph_fourier):.3f}   ✅
     最好神经网络架构      -> {res[0][0]:.3f}   {'✅ 也能!' if res[0][0]>0.5 else '❌ 不行'}
     神经网络平均          -> {sum(x[0] for x in res)/len(res):.3f}
     随机                 -> 0.100

  ★ {'★ 有些架构能接近结构法!' if res[0][0]>0.5 else '★ 所有架构都远不如结构法'}
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
