# -*- coding: utf-8 -*-
"""brute_arch4.py 任务改为 (a*b) mod 10 —— 线性外推【解不了】"""
import numpy as np
t0=__import__('time').time()
n=10; D=64
Xtr=[];Ytr=[];Xte=[];Yte=[]
for a in range(n):
    for b in range(n):
        v=np.zeros(2*n); v[a]=1; v[n+b]=1
        if b==1 or a==1: Xtr.append(v); Ytr.append((a*b)%n)   # 训练只见 ×1
        else: Xte.append(v); Yte.append((a*b)%n)
Xtr=np.array(Xtr);Ytr=np.array(Ytr,float);Xte=np.array(Xte);Yte=np.array(Yte,float)

def run(phi):
    A=phi(Xtr);B=phi(Xte)
    Am=np.hstack([A,np.ones((len(A),1))]);Bm=np.hstack([B,np.ones((len(B),1))])
    W=np.linalg.lstsq(Am,Ytr,rcond=1e-8)[0]
    P=np.round(Bm@W).astype(int)%n
    return (P==Yte.astype(int)).mean()

print("="*90)
print("★ 任务: (a*b) mod 10, 训练只见 ×1, 测试全组合")
print("★ 这个任务【线性外推解不了】(乘法非线性), 才是真推理测试")
print("="*90)
print()
a=Xte[:,:n]@np.arange(n); b=Xte[:,n:]@np.arange(n)
print(f"  {'编码':<30}{'准确率'}")
print("  "+"-"*44)
print(f"  {'上界: 直接给 (a*b)%n':<30}{1.0:.3f}")
print(f"  {'裸 a,b (线性)':<30}{run(lambda X: np.stack([X[:,:n]@np.arange(n),X[:,n:]@np.arange(n)],1)):.3f}")
print(f"  {'随机':<30}{1/n:.3f}")
print()
res=[]
KINDS={'linear':lambda z:z,'tanh':np.tanh,'sin':np.sin,'relu':lambda z:np.maximum(z,0),
       'silu':lambda z:z/(1+np.exp(-z)),'quad':lambda z:z*z,'abs':np.abs}
for k,act in KINDS.items():
    for rho in [0.5,0.9,1.0,1.1,1.5]:
        for s in [1,2,4,8]:
            r=np.random.RandomState(0)
            W=r.randn(2*n,D)/np.sqrt(2*n); R=r.randn(D,D)
            R=R*(rho/max(abs(np.linalg.eigvals(R)).max(),1e-9))
            def phi(X,W=W,R=R,act=act,s=s):
                H=act(X@W)
                for _ in range(s): H=act(H@R.T)
                return H
            res.append((run(phi),k,rho,s))
res.sort(reverse=True)
print(f"  {'最好架构':<30}{res[0][0]:.3f}  ({res[0][1]} ρ={res[0][2]} 步={res[0][3]})")
print(f"  {'平均(140种)':<30}{sum(x[0] for x in res)/len(res):.3f}")
print(f"  {'最好的前5':<30}"+" ".join(f"{x[0]:.2f}" for x in res[:5]))
print()
print("="*90)
print("★ 结论")
print("="*90)
print(f"""
  真正需要组合推理的任务 (乘法):

     随机              0.100
     最好神经网络架构    {res[0][0]:.3f}
     140种架构平均      {sum(x[0] for x in res)/len(res):.3f}

  ★ {'❌ 所有架构都远不如随机以上 —— 组合推理确实没被架构解决' if res[0][0]<0.4 else '✅ 有架构能解'}
  ★ 这就是「推理能力锁死」的真实样子: 换架构【解决不了】组合推理
""")
print(f"用时 {__import__('time').time()-t0:.2f}s")
