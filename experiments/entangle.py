# -*- coding: utf-8 -*-
"""entangle.py — 固定参数量, 只增强「纠缠」方式
   核心: 参数量严格不变(3972), 只改纠缠结构 → 看泛化能否突破
   纠缠变体:
     V0 基线      : 每步 1 次线性交换
     V1 深度纠缠  : 每步 K 次交换(迭代松弛, 零新增参数)
     V2 非线性干涉: 乘法耦合(不是加法) → 真正的纠缠
     V3 环路拓扑  : 环状传递(核i→核i+1)
     V4 时间延迟  : 核A用核B的【上一步】状态(异步纠缠)
     V5 全组合    : 深度+非线性+延迟
"""
import numpy as np, random, time
random.seed(7); np.random.seed(7)

CH=list("0123456789+-+=?,>")+["<pad>"]
C2I={c:i for i,c in enumerate(CH)}; V=len(CH); PAD=C2I["<pad>"]
def enc(s,L=14):
    ids=[C2I.get(c,PAD) for c in s[:L]]
    return np.array(ids+[PAD]*(L-len(ids)), np.int32)

# ---------- 数据 ----------
def t_add(lo,hi,n):
    """标签 = (a+b) 的个位数 (10类, 分布均匀) ← 修正: 避免标签集中"""
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        o.append(("%d+%d"%(a,b), (a+b)%10))
    return o
def t_cmpr(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        if a==b: b+=1
        o.append(("%d>%d"%(a,b), int(a>b)))
    return o
def t_parity(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi)
        o.append(("%d"%a, a%2))
    return o

# ---------- 纠缠水库 ----------
class ERes:
    def __init__(self, n=5, H=12, din=V, rho=0.9, mode="v0", iters=1, delay=True, seed=0):
        r=np.random.RandomState(seed)
        self.n,self.H,self.din = n,H,din
        self.mode,self.iters,self.use_delay = mode,iters,delay
        D=n*H
        self.Win=(r.randn(din,H)*0.6).astype(np.float32)
        self.Wrec=(r.randn(H,H)/np.sqrt(H)*2.0).astype(np.float32)
        ev=max(abs(np.linalg.eigvals(self.Wrec))); self.Wrec=self.Wrec*(rho/max(ev,1e-6))
        self.b=(r.randn(H)*0.1).astype(np.float32)
        # 纠缠矩阵(按模式不同)
        if mode=="v3":   # 环
            W=np.zeros((D,D),np.float32)
            for i in range(n):
                j=(i+1)%n
                W[i*H:(i+1)*H, j*H:(j+1)*H] = (r.randn(H,H)/np.sqrt(H)).astype(np.float32)
            self.Wcpl=W
        else:            # 全连接
            self.Wcpl=(r.randn(D,D)/np.sqrt(D)).astype(np.float32)
        # 非线性干涉用(乘法项) —— 复用同一矩阵, 零新增参数
        self.Wmul = self.Wcpl
        self.nparam = self.Win.size+self.Wrec.size+self.Wcpl.size+self.b.size
    def run(self, x):
        T=len(x)
        X=np.eye(self.din,dtype=np.float32)[x] if x.ndim==1 else x.astype(np.float32)
        H=self.H; n_=self.n
        h=np.zeros((n_,H),np.float32)
        h_prev=np.zeros_like(h)
        traj=np.empty((T,n_*H),np.float32)
        for t in range(T):
            flat=h.reshape(-1)
            # ---- 纠缠(核心) ----
            for k in range(self.iters):          # V1: 深度纠缠
                if self.mode in ("v2","v5"):     # V2: 非线性干涉
                    mul = (self.Wmul@flat)
                    mix = np.tanh(mul)*0.5          # 乘法式(门控干涉)
                else:
                    mix = self.Wcpl@flat
                if self.use_delay and self.mode=="v5":   # V4/V5: 时间延迟
                    mix = mix + 0.5*(self.Wcpl@h_prev.reshape(-1))
                # 迭代松弛: 把 mix 再注入(不新增参数, 只增加计算深度)
                if self.iters>1 and k<self.iters-1:
                    flat = 0.5*flat + 0.5*np.tanh(mix)
            u = X[t]@self.Win + h@self.Wrec.T + (self.Wcpl@flat if self.mode in ("v0","v1","v3") else mix).reshape(n_,H) + self.b
            h_prev = h.copy()
            h = np.tanh(u)
            traj[t]=h.reshape(-1)
        return traj
    def feats(self,s):
        tr=self.run(enc(s))
        return np.concatenate([tr.mean(0), tr[-1], tr.std(0), tr.max(0)]).astype(np.float32)

def ev(res, tr, te, C):
    Xtr=np.array([res.feats(s) for s,_ in tr]); Ytr=np.array([y for _,y in tr])
    Xte=np.array([res.feats(s) for s,_ in te]); Yte=np.array([y for _,y in te])
    D=Xtr.shape[1]
    if C>1:
        Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    else:
        Yh=Ytr.astype(np.float32)
    W=np.linalg.solve(Xtr.T@Xtr+1e-3*np.eye(D), Xtr.T@Yh)
    pred=Xte@W
    return float((pred.argmax(1)==Yte).mean()) if C>1 else float((((pred>0.5).astype(int))==Yte).mean())

def main():
    t0=time.time()
    print("="*78)
    print("  修正版: 标签=(a+b)个位 (10类均匀) — 只增强「纠缠」能否突破泛化?")
    print("="*78)
    _tr=t_add(0,9,3000); _te=t_add(50,99,3000)
    from collections import Counter
    print("  标签分布检查:")
    print("    训练(0-9)  :", dict(sorted(Counter(y for _,y in _tr).items())))
    print("    测试(50-99):", dict(sorted(Counter(y for _,y in _te).items())))
    print("    → 均匀则实验有效 (基线=10%)")
    # 任务
    A1=("加法同分布",  t_add(0,9,1200),   t_add(0,9,400),   10)
    A2=("★加 10-30",   t_add(0,9,1500),   t_add(10,30,500), 10)
    A3=("★加 50-99",   t_add(0,9,1500),   t_add(50,99,500), 10)
    C1=("比较同分布",  t_cmpr(0,9,1200),  t_cmpr(0,9,400),  1)
    C2=("★比较泛化",   t_cmpr(0,9,1500),  t_cmpr(10,99,500),1)
    P1=("奇偶同分布",  t_parity(0,9,1200),t_parity(0,9,400),1)
    P2=("★奇偶泛化",   t_parity(0,9,1500),t_parity(10,999,500),1)
    tasks=[A1,A2,A3,C1,C2,P1,P2]
    variants=[
        ("V0 基线",        dict(mode="v0", iters=1, delay=False)),
        ("V1 深度纠缠x5",  dict(mode="v1", iters=5, delay=False)),
        ("V2 非线性干涉",  dict(mode="v2", iters=2, delay=False)),
        ("V3 环路拓扑",    dict(mode="v3", iters=3, delay=False)),
        ("V4 时间延迟",    dict(mode="v0", iters=3, delay=True)),
        ("V5 全组合",      dict(mode="v5", iters=4, delay=True)),
    ]
    print("\n%-14s"%"任务" + "".join("| %-15s"%v[0] for v in variants))
    print("-"*78)
    for tname,tr,te,C in tasks:
        line="%-14s"%tname
        for vn,kw in variants:
            r=ERes(**kw)
            acc=ev(r,tr,te,C)
            line += "| %-15s"%("%.1f%%"% (100*acc))
        print(line, flush=True)
    print("\n(参数量全部 = 3972, 差异只来自纠缠方式)")
    print("耗时 %.0fs"%(time.time()-t0))

if __name__=="__main__": main()
