# -*- coding: utf-8 -*-
"""scale50x.py — 50倍扩大 + 深度对照, 测真推理
   严格: 训练只见 50% 组合 → 测试另 50% (随机=10%)
   变量: 宽度 / 深度 / 特征
"""
import numpy as np, random, time
random.seed(7); np.random.seed(7)

def feat_onehot(c):
    v=np.zeros(20,np.float32)
    v[int(c[0])%10]=1.0; v[10+int(c[1])%10]=1.0
    return v
def feat_num(c):
    return np.array([c[0]%10/9.0, c[1]%10/9.0], np.float32)

class MLP:
    def __init__(s,din,H,C=10,nl=2,seed=0):
        r=np.random.RandomState(seed); s.H=H; s.nl=nl
        s.W=[]; s.b=[]; s.PS=[]
        prev=din
        for i in range(nl):
            W=(r.randn(H,prev)/np.sqrt(prev)).astype(np.float32); b=np.zeros(H,np.float32)
            s.W.append(W); s.b.append(b); s.PS += [W,b]; prev=H
        s.Wo=(r.randn(C,H)/np.sqrt(H)).astype(np.float32); s.bo=np.zeros(C,np.float32)
        s.PS += [s.Wo,s.bo]
        s.M=[np.zeros_like(p) for p in s.PS]; s.V=[np.zeros_like(p) for p in s.PS]; s.t=0
        s.nparam=sum(p.size for p in s.PS)
    def fwd(s,X,keep=False):
        hs=[]; zs=[]; h=X
        for i in range(s.nl):
            z=h@s.W[i].T+s.b[i]; zs.append(z); h=np.maximum(z,0); hs.append(h)
        lg=h@s.Wo.T+s.bo
        return (lg,hs,zs) if keep else lg
    def fit(s,X,Y,ep=250,lr=1e-3,bs=128):
        N=len(X); C=s.Wo.shape[0]
        Yh=np.zeros((N,C),np.float32); Yh[np.arange(N),Y]=1
        for e in range(ep):
            idx=np.random.permutation(N)
            for i in range(0,N,bs):
                ii=idx[i:i+bs]; xb=X[ii]; yb=Yh[ii]
                lg,hs,zs=s.fwd(xb,keep=True)
                m=lg.max(1,keepdims=True); p=np.exp(lg-m); p/=p.sum(1,keepdims=True)
                g=(p-yb)/len(ii)
                gWo=g.T@hs[-1]; gbo=g.sum(0)
                gW=[]; gb=[]
                gh=g@s.Wo
                for i in range(s.nl-1,-1,-1):
                    gh=gh*(zs[i]>0)
                    inp = xb if i==0 else hs[i-1]
                    gW.append(gh.T@inp); gb.append(gh.sum(0))
                    if i>0: gh=gh@s.W[i]
                gW=gW[::-1]; gb=gb[::-1]
                G=[]
                for i in range(s.nl): G += [gW[i],gb[i]]
                G += [gWo,gbo]
                s.t+=1; b1,b2,eps=.9,.999,1e-8
                for j,(P,gg) in enumerate(zip(s.PS,G)):
                    np.clip(gg,-3,3,out=gg)
                    s.M[j]=b1*s.M[j]+(1-b1)*gg
                    s.V[j]=b2*s.V[j]+(1-b2)*gg*gg
                    mh=s.M[j]/(1-b1**s.t); vh=s.V[j]/(1-b2**s.t)
                    P-=(lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return s
    def acc(s,X,Y): return float((s.fwd(X).argmax(1)==Y).mean())

def test(feat,H,nl,ep=250,task="add"):
    combos=[(a,b) for a in range(10) for b in range(10)]
    random.shuffle(combos); k=int(len(combos)*0.5)
    seen,unseen=combos[:k],combos[k:]
    def lab(a,b): return (a+b)%10 if task=="add" else (a*b)%10
    Xs=np.array([feat(c) for c in seen]); Ys=np.array([lab(*c) for c in seen])
    Xu=np.array([feat(c) for c in unseen]); Yu=np.array([lab(*c) for c in unseen])
    t0=time.time()
    m=MLP(Xs.shape[1],H,10,nl,seed=1).fit(Xs,Ys,ep=ep)
    return m.acc(Xs,Ys), m.acc(Xu,Yu), m.nparam, time.time()-t0

print("="*84)
print("  50倍扩大 + 深度对照 — 真推理 (训练50%组合 → 测另50%, 随机=10%)")
print("="*84)
cfgs=[
 ("基线 H256 x2层 (288KB)", feat_onehot, 256, 2),
 ("H512  x4层",            feat_onehot, 512, 4),
 ("H1024 x4层",            feat_onehot, 1024,4),
 ("H1024 x8层 (深)",       feat_onehot, 1024,8),
 ("H256  x2层 +数值特征",   feat_num,    256, 2),
 ("H1024 x8层 +数值特征",   feat_num,    1024,8),
]
print("\n%-26s %-12s %-10s %-10s %-10s %s"%("配置","参数","占用","见过","未见","判定"))
print("-"*84)
for name,feat,H,nl in cfgs:
    a1,a2,npar,dt=test(feat,H,nl,ep=250)
    kb=npar*4/1024
    u="%.1f KB"%kb if kb<1024 else "%.1f MB"%(kb/1024)
    j="✅真会算" if a2>0.9 else ("⚠️部分" if a2>0.4 else "❌查表")
    print("%-26s %-12s %-10s %-10s %-10s %s (%.0fs)"%(name,f"{npar:,}",u,
          "%.1f%%"%(100*a1),"%.1f%%"%(100*a2),j,dt),flush=True)

print("\n"+"-"*84)
print("  乘法任务对照")
print("-"*84)
for name,feat,H,nl in [("H256 x2层",feat_onehot,256,2),("H1024 x8层",feat_onehot,1024,8)]:
    a1,a2,npar,dt=test(feat,H,nl,ep=250,task="mul")
    print("%-26s 见过 %5.1f%% | 未见 %5.1f%%"%(name,100*a1,100*a2),flush=True)
