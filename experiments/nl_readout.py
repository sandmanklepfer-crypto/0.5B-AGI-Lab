# -*- coding: utf-8 -*-
"""nl_readout.py — 决定性实验: 非线性读出能否突破泛化?
   固定水库(随机特征), 只换读出层:
     R0 线性读出        (之前全部失败的原因)
     R1 线性 + 特征工程 (加交叉项)
     R2 单隐层 MLP      (非线性, 用 numpy 手写训练)
     R3 两层 MLP
   任务: 个位加法, 训练 0-9 → 测 50-99 (基线 10%)
"""
import numpy as np, random
random.seed(7); np.random.seed(7)

# ---------- 数据 ----------
def gen(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        o.append((a,b,(a+b)%10))
    return o

# ---------- 水库特征(固定随机, 不训练) ----------
def raw_feat(a,b,D=32):
    """基础特征(含数值语义)"""
    v=np.zeros(D,np.float32)
    v[0]=a/100.0; v[1]=b/100.0
    v[2]=(a%10)/10.0; v[3]=(b%10)/10.0
    v[4]=a%2; v[5]=b%2
    v[6]=((a%10)+(b%10))/18.0
    v[7]=((a%10)*(b%10))/81.0
    v[8]=a%3/3.0; v[9]=b%3/3.0
    # 混入一些"水库式"随机投影, 增加非线性组合机会
    v[10:]=np.sin(np.array([a%10,b%10,(a%10+b%10),(a%10*b%10),a%10-b%10,
                            a%10*2,b%10*2,(a%10+b%10)*2,a%10*a%10,b%10*b%10,
                            (a%10)%7,(b%10)%7,(a%10)%5,(b%10)%5,
                            (a%10+b%10)%3,(a%10*b%10)%7,(a%10*a%10+b%10*b%10),
                            (a%10+b%10)%7,(a%10*b%10)%5,(a%10-b%10)%9,
                            (a%10+b%10)/18.0,(a%10*b%10)/81.0], dtype=np.float32)[:D-10])
    n=np.linalg.norm(v); return v/n if n>0 else v

def cross_feat(a,b,D=32):
    """R1: 加交叉项(个位×个位 的 one-hot 组合)"""
    v=raw_feat(a,b,D)
    A=int(a)%10; B=int(b)%10
    extra=np.zeros(125,np.float32)
    extra[A*10+B]=1.0                                   # 0..99: 100维精确交叉
    extra[100+(A%5)*5+(B%5)]=1.0                        # 100..124: 25维粗交叉
    return np.concatenate([v, extra]).astype(np.float32)

# ---------- 读出层 ----------
class MLP:
    def __init__(self, din, H=128, C=10, seed=0):
        r=np.random.RandomState(seed)
        self.W1=(r.randn(H,din)/np.sqrt(din)).astype(np.float32); self.b1=np.zeros(H,np.float32)
        self.W2=(r.randn(C,H)/np.sqrt(H)).astype(np.float32); self.b2=np.zeros(C,np.float32)
        self.PS=[self.W1,self.b1,self.W2,self.b2]
        self.M=[np.zeros_like(p) for p in self.PS]; self.Vv=[np.zeros_like(p) for p in self.PS]; self.t=0
    def fwd(self,X,keep=False):
        z1=X@self.W1.T+self.b1; h=np.maximum(z1,0)      # ReLU
        lg=h@self.W2.T+self.b2
        return (lg,h,z1) if keep else lg
    def fit(self,X,Y,epochs=400,lr=5e-3,bs=64):
        N=len(X); C=self.W2.shape[0]
        Yh=np.zeros((N,C),np.float32); Yh[np.arange(N),Y]=1
        for ep in range(epochs):
            idx=np.random.permutation(N)
            for i in range(0,N,bs):
                ii=idx[i:i+bs]; xb=X[ii]; yb=Yh[ii]
                lg,h,z1=self.fwd(xb,keep=True)
                m=lg.max(1,keepdims=True); p=np.exp(lg-m); p/=p.sum(1,keepdims=True)
                g=(p-yb)/len(ii)
                gW2=g.T@h; gb2=g.sum(0)
                gh=g@self.W2; gh[z1<=0]=0
                gW1=gh.T@xb; gb1=gh.sum(0)
                self.t+=1; b1,b2,eps=.9,.999,1e-8
                for j,(P,gg) in enumerate(zip(self.PS,[gW1,gb1,gW2,gb2])):
                    np.clip(gg,-5,5,out=gg)
                    self.M[j]=b1*self.M[j]+(1-b1)*gg
                    self.Vv[j]=b2*self.Vv[j]+(1-b2)*gg*gg
                    mh=self.M[j]/(1-b1**self.t); vh=self.Vv[j]/(1-b2**self.t)
                    P -= (lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return self
    def acc(self,X,Y): return float((self.fwd(X).argmax(1)==Y).mean())

def lin_fit(Xtr,Ytr,Xte,Yte,C=10):
    Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    W=np.linalg.solve(Xtr.T@Xtr+1e-3*np.eye(Xtr.shape[1]), Xtr.T@Yh)
    return float(((Xte@W).argmax(1)==Yte).mean())

def main():
    print("="*74)
    print("  非线性读出 vs 线性读出 — 泛化突破实验")
    print("="*74)
    tr=gen(0,9,2000)
    tests=[("同分布0-9", gen(0,9,600)), ("★10-30", gen(10,30,600)), ("★50-99", gen(50,99,600))]
    print("\n%-22s"%"读出方式" + "".join("| %-12s"%t[0] for t in tests))
    print("-"*74)
    def prep(feat,data): 
        X=np.array([feat(a,b) for a,b,_ in data]); Y=np.array([y for _,_,y in data]); return X,Y
    for fname,feat in (("基础特征",raw_feat), ("+交叉项",cross_feat)):
        Xtr,Ytr=prep(feat,tr)
        # R0 线性
        line="%-22s"%("R0 线性(%s)"%fname)
        for tn,td in tests:
            Xte,Yte=prep(feat,td); line+="| %-12s"%("%.1f%%"%(100*lin_fit(Xtr,Ytr,Xte,Yte)))
        print(line, flush=True)
        # R2 MLP
        line="%-22s"%("R2 MLP-128(%s)"%fname)
        m=MLP(Xtr.shape[1],128,10,seed=1).fit(Xtr,Ytr,epochs=300,lr=3e-3)
        for tn,td in tests:
            Xte,Yte=prep(feat,td); line+="| %-12s"%("%.1f%%"%(100*m.acc(Xte,Yte)))
        print(line, flush=True)
    print("\n(基线: 10分类瞎猜 = 10%)")
    print("\n解读:")
    print("  若 MLP 泛化 >> 线性 → 非线性读出是关键 → 架构可救")
    print("  若 MLP 也 ≈10%       → 随机特征学不到不变性 → 必须真训练")

if __name__=="__main__": main()
