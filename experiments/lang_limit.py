# -*- coding: utf-8 -*-
"""lang_limit.py — 「小核学语言」规模曲线(干净版)
   真实语料, 字符级 GRU 语言模型, 扫隐藏维度
   指标: 验证集 bits/char (越低越好)
"""
import numpy as np, random, math, time
random.seed(7); np.random.seed(7)

txt = open("/workspace/raw_corpus.txt", encoding="utf-8", errors="ignore").read()[:200000]
chars = sorted(set(txt)); V=len(chars); C2I={c:i for i,c in enumerate(chars)}
data = np.array([C2I[c] for c in txt], np.int32)
print("语料 %d 字符 | 词表 %d | 随机猜测 %.2f bits/char"%(len(data),V,math.log2(V)))
sp=int(len(data)*0.9); tr_d,va_d=data[:sp],data[sp:]

from collections import Counter
f=Counter(data[:sp].tolist()); p0=np.array([f.get(i,0)+1 for i in range(V)],float); p0/=p0.sum()
print("  0阶(词频)   = %.3f"%(-np.mean([math.log2(p0[b]) for b in va_d])))
bi=np.ones((V,V)); 
for a,b in zip(tr_d[:-1],tr_d[1:]): bi[a,b]+=1
bi/=bi.sum(1,keepdims=True)
print("  1阶(bigram) = %.3f"%(-np.mean([math.log2(bi[a,b]) for a,b in zip(va_d[:-1],va_d[1:])])))

class GRU:
    def __init__(self,H=64,d=32,seed=0):
        r=np.random.RandomState(seed); self.H=H
        sc=1/np.sqrt(H)
        self.E=(r.randn(V,d)*0.15).astype(np.float32)
        self.Wz=(r.randn(H,d)*sc).astype(np.float32); self.Uz=(r.randn(H,H)*sc).astype(np.float32); self.bz=np.zeros(H,np.float32)
        self.Wr=(r.randn(H,d)*sc).astype(np.float32); self.Ur=(r.randn(H,H)*sc).astype(np.float32); self.br=np.zeros(H,np.float32)
        self.Wh=(r.randn(H,d)*sc).astype(np.float32); self.Uh=(r.randn(H,H)*sc).astype(np.float32); self.bh=np.zeros(H,np.float32)
        self.Wo=(r.randn(V,H)/np.sqrt(H)).astype(np.float32); self.bo=np.zeros(V,np.float32)
        self.PS=[self.E,self.Wz,self.Uz,self.bz,self.Wr,self.Ur,self.br,self.Wh,self.Uh,self.bh,self.Wo,self.bo]
        self.M=[np.zeros_like(p) for p in self.PS]; self.Vv=[np.zeros_like(p) for p in self.PS]; self.t=0
        self.nparam=sum(p.size for p in self.PS)
    @staticmethod
    def sg(x): return 1.0/(1.0+np.exp(-np.clip(x,-25,25)))
    def fwd(self,X,keep=False):
        B,T=X.shape; H=self.H
        xx=self.E[X]; h=np.zeros((B,H),np.float32); cs=[]
        for t in range(T):
            xt=xx[:,t,:]
            z=self.sg(xt@self.Wz.T+h@self.Uz.T+self.bz)
            r=self.sg(xt@self.Wr.T+h@self.Ur.T+self.br)
            hc=np.tanh(xt@self.Wh.T+(r*h)@self.Uh.T+self.bh)
            hn=(1-z)*h+z*hc
            if keep: cs.append((xt,h,z,r,hc))
            h=hn
        lg=h@self.Wo.T+self.bo
        return (lg,cs,h) if keep else lg
    def step(self,X,Y,lr=3e-3):
        B,T=X.shape
        lg,cs,hT=self.fwd(X,keep=True)
        m=lg.max(1,keepdims=True); p=np.exp(lg-m); p/=p.sum(1,keepdims=True)
        loss=float(-np.mean(np.log2(p[np.arange(B),Y]+1e-12)))
        g=p.copy(); g[np.arange(B),Y]-=1; g/=B
        gWo=g.T@hT; gbo=g.sum(0); dh=g@self.Wo
        gE=np.zeros_like(self.E)
        gWz=np.zeros_like(self.Wz); gUz=np.zeros_like(self.Uz); gbz=np.zeros_like(self.bz)
        gWr=np.zeros_like(self.Wr); gUr=np.zeros_like(self.Ur); gbr=np.zeros_like(self.br)
        gWh=np.zeros_like(self.Wh); gUh=np.zeros_like(self.Uh); gbh=np.zeros_like(self.bh)
        for t in range(T-1,-1,-1):
            xt,h,z,r,hc=cs[t]
            dz=dh*(hc-h)*(z*(1-z)); dhc=dh*z*(1-hc*hc)
            drh=dhc@self.Uh; dr=drh*h*(r*(1-r))
            gWz+=dz.T@xt; gUz+=dz.T@h; gbz+=dz.sum(0)
            gWr+=dr.T@xt; gUr+=dr.T@h; gbr+=dr.sum(0)
            gWh+=dhc.T@xt; gUh+=dhc.T@(r*h); gbh+=dhc.sum(0)
            np.add.at(gE,X[:,t],dz@self.Wz+dr@self.Wr+dhc@self.Wh)
            dh=dh*(1-z)+dz@self.Uz+dr@self.Ur+drh*r
        G=[gE,gWz,gUz,gbz,gWr,gUr,gbr,gWh,gUh,gbh,gWo,gbo]
        self.t+=1; b1,b2,eps=.9,.999,1e-8
        for i,(P,gg) in enumerate(zip(self.PS,G)):
            np.clip(gg,-3,3,out=gg)
            self.M[i]=b1*self.M[i]+(1-b1)*gg
            self.Vv[i]=b2*self.Vv[i]+(1-b2)*gg*gg
            mh=self.M[i]/(1-b1**self.t); vh=self.Vv[i]/(1-b2**self.t)
            P-=(lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return loss

def batch(d,B=32,T=48):
    idx=np.random.randint(0,len(d)-T-1,B)
    return np.stack([d[i:i+T] for i in idx]), np.array([d[i+T] for i in idx])
def bpc(m,data,n=15):
    ls=[]
    for _ in range(n):
        X,Y=batch(data); lg=m.fwd(X)
        mm=lg.max(1,keepdims=True); p=np.exp(lg-mm); p/=p.sum(1,keepdims=True)
        ls.append(-np.mean(np.log2(p[np.arange(len(Y)),Y]+1e-12)))
    return float(np.mean(ls))

print("\n"+"="*72)
print("  小核学语言: 规模曲线")
print("="*72)
print("\n%-12s %-12s %-10s %-14s %s"%("配置","参数量","占用","验证bits/char","评价"))
print("-"*72)
for H,steps in [(8,600),(16,600),(32,600),(64,600),(128,500),(256,400)]:
    t0=time.time()
    m=GRU(H=H)
    for s in range(steps):
        X,Y=batch(tr_d); m.step(X,Y)
    b=bpc(m,va_d)
    kb=m.nparam*4/1024
    u="%.1f KB"%kb if kb<1024 else "%.1f MB"%(kb/1024)
    tag = "随机水平" if b>math.log2(V)*0.9 else ("学到一点" if b<math.log2(V)*0.7 else "微弱")
    print("%-12s %-12s %-10s %-14.3f %s"%(f"H={H}", f"{m.nparam:,}", u, b, tag), flush=True)
print("\n(随机猜测=%.2f; 越低越好)"%math.log2(V))
