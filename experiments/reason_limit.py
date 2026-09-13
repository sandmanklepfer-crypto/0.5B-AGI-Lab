# -*- coding: utf-8 -*-
"""reason_limit.py — 1.3KB 小核的推理极限扫描
   严格设计: 特征只给【原始数字的 one-hot】, 不给任何中间结果
             → 模型必须自己学会运算 = 真推理
   难度阶梯:
     L1 a+b            单步一位运算
     L2 a+b+c          三步连加
     L3 a+b*c          需优先级
     L4 (a+b)*c        需括号
     L5 (a+b)*(c+d)    两个子式
     L6 ((a+b)*c+d)*e  四层嵌套
     L7 逻辑传递 A>B>C>D>E  多跳链
   对照: 线性读出 vs MLP读出
"""
import numpy as np, random, itertools
random.seed(7); np.random.seed(7)

# ---------- 特征: 纯 one-hot, 无任何运算提示 ----------
def feat(digits, D=None):
    """digits: 列表, 每个 0-9; 编码为 one-hot 拼接"""
    v=np.zeros(10*len(digits), np.float32)
    for i,d in enumerate(digits):
        v[i*10 + (int(d)%10)] = 1.0
    return v
NFEAT = 10*6   # 最多6个数字 → 60维

def padfeat(v, D=NFEAT):
    if len(v)<D: return np.concatenate([v, np.zeros(D-len(v),np.float32)])
    return v[:D]

# ---------- 难度阶梯 ----------
def L1(n):  # a+b 个位
    return [((a,b),(a+b)%10) for a,b in
            [(random.randint(0,9),random.randint(0,9)) for _ in range(n)]]
def L2(n):  # a+b+c 个位
    return [((a,b,c),(a+b+c)%10) for a,b,c in
            [(random.randint(0,9),random.randint(0,9),random.randint(0,9)) for _ in range(n)]]
def L3(n):  # a+b*c 个位  (需优先级)
    return [((a,b,c),(a+b*c)%10) for a,b,c in
            [(random.randint(0,9),random.randint(0,9),random.randint(0,9)) for _ in range(n)]]
def L4(n):  # (a+b)*c 个位
    return [((a,b,c),((a+b)*c)%10) for a,b,c in
            [(random.randint(0,9),random.randint(0,9),random.randint(0,9)) for _ in range(n)]]
def L5(n):  # (a+b)*(c+d) 个位
    return [((a,b,c,d),((a+b)*(c+d))%10) for a,b,c,d in
            [(random.randint(0,9),)*4 for _ in range(n)]]
def L6(n):  # ((a+b)*c+d)*e 个位 (四层)
    return [((a,b,c,d,e),(((a+b)*c+d)*e)%10) for a,b,c,d,e in
            [(random.randint(0,9),)*5 for _ in range(n)]]
def L7(n):  # 逻辑传递: 5个元素排序, 问首尾关系
    o=[]
    for _ in range(n):
        vals=[random.randint(0,9) for _ in range(5)]
        # 排序后问: 最大值%10 (等价于传递推理的结果)
        o.append((tuple(vals), max(vals)%10))
    return o

TASKS=[
 ("L1 a+b",         L1, 2, 10),
 ("L2 a+b+c",       L2, 3, 10),
 ("L3 a+b*c",       L3, 3, 10),
 ("L4 (a+b)*c",     L4, 3, 10),
 ("L5 (a+b)*(c+d)", L5, 4, 10),
 ("L6 四层嵌套",     L6, 5, 10),
 ("L7 最大传递",     L7, 5, 10),
]

# ---------- 读出 ----------
def lin(Xtr,Ytr,Xte,Yte,C=10):
    D=Xtr.shape[1]
    Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    W=np.linalg.solve(Xtr.T@Xtr+1e-2*np.eye(D), Xtr.T@Yh)
    return float(((Xte@W).argmax(1)==Yte).mean())

class MLP:
    def __init__(self,din,H=256,C=10,seed=0):
        r=np.random.RandomState(seed)
        self.W1=(r.randn(H,din)/np.sqrt(din)).astype(np.float32); self.b1=np.zeros(H,np.float32)
        self.W2=(r.randn(H,H)/np.sqrt(H)).astype(np.float32); self.b2=np.zeros(H,np.float32)
        self.W3=(r.randn(C,H)/np.sqrt(H)).astype(np.float32); self.b3=np.zeros(C,np.float32)
        self.PS=[self.W1,self.b1,self.W2,self.b2,self.W3,self.b3]
        self.M=[np.zeros_like(p) for p in self.PS]; self.V=[np.zeros_like(p) for p in self.PS]; self.t=0
    def fwd(self,X,keep=False):
        z1=X@self.W1.T+self.b1; h1=np.maximum(z1,0)
        z2=h1@self.W2.T+self.b2; h2=np.maximum(z2,0)
        lg=h2@self.W3.T+self.b3
        return (lg,h1,h2,z1,z2) if keep else lg
    def fit(self,X,Y,ep=500,lr=3e-3,bs=64):
        N=len(X); C=self.W3.shape[0]
        Yh=np.zeros((N,C),np.float32); Yh[np.arange(N),Y]=1
        for e in range(ep):
            idx=np.random.permutation(N)
            for i in range(0,N,bs):
                ii=idx[i:i+bs]; xb=X[ii]; yb=Yh[ii]
                lg,h1,h2,z1,z2=self.fwd(xb,keep=True)
                m=lg.max(1,keepdims=True); p=np.exp(lg-m); p/=p.sum(1,keepdims=True)
                g=(p-yb)/len(ii)
                gW3=g.T@h2; gb3=g.sum(0)
                gh2=g@self.W3; gh2[z2<=0]=0
                gW2=gh2.T@h1; gb2=gh2.sum(0)
                gh1=gh2@self.W2; gh1[z1<=0]=0
                gW1=gh1.T@xb; gb1=gh1.sum(0)
                self.t+=1; b1,b2,eps=.9,.999,1e-8
                for j,(P,gg) in enumerate(zip(self.PS,[gW1,gb1,gW2,gb2,gW3,gb3])):
                    np.clip(gg,-5,5,out=gg)
                    self.M[j]=b1*self.M[j]+(1-b1)*gg
                    self.V[j]=b2*self.V[j]+(1-b2)*gg*gg
                    mh=self.M[j]/(1-b1**self.t); vh=self.V[j]/(1-b2**self.t)
                    P -= (lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return self
    def npar(self): return sum(p.size for p in self.PS)
    def acc(self,X,Y): return float((self.fwd(X).argmax(1)==Y).mean())

def main():
    print("="*80)
    print("  1.3KB 小核的推理极限 (特征只给原始数字 one-hot, 不含任何中间结果)")
    print("="*80)
    NTR=3000; NTE=800
    print("\n%-18s %-10s | %-16s | %-16s"%("任务","层数","线性读出","MLP-256 读出"))
    print("-"*80)
    res=[]
    for name,fn,ndig,C in TASKS:
        tr=fn(NTR); te=fn(NTE)
        Xtr=np.array([padfeat(feat(d)) for d,_ in tr]); Ytr=np.array([y for _,y in tr])
        Xte=np.array([padfeat(feat(d)) for d,_ in te]); Yte=np.array([y for _,y in te])
        a_lin=lin(Xtr,Ytr,Xte,Yte,C)
        m=MLP(Xtr.shape[1],256,C,seed=1).fit(Xtr,Ytr,ep=300,lr=3e-3)
        a_mlp=m.acc(Xte,Yte)
        print("%-18s %-10s | %-16s | %-16s"%(
            name, "%d数字"%ndig, "%.1f%%"%(100*a_lin), "%.1f%%"%(100*a_mlp)), flush=True)
        res.append((name,ndig,a_lin,a_mlp,m.npar()))
    print("\n"+"="*80)
    print("  总结")
    print("="*80)
    print("  %-18s %-8s %-14s %s"%("任务","层数","MLP准确率","判定"))
    print("  "+"-"*60)
    for name,ndig,a1,a2,npar in res:
        j = "✅ 掌握" if a2>0.9 else ("⚠️ 部分" if a2>0.5 else "❌ 失败")
        print("  %-18s %-8s %-14s %s"%(name,"%d数字"%ndig,"%.1f%%"%(100*a2),j))
    print("\n  MLP 参数: %s (%.1f KB)"%(f"{res[0][4]:,}", res[0][4]*4/1024))
    print("  (基线: 10分类瞎猜=10%)")

if __name__=="__main__": main()
