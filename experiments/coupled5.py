# -*- coding: utf-8 -*-
"""coupled5.py — 5 个 1.3KB 核「纠缠耦合」成时序系统
   做法: 耦合水库(Reservoir Computing)
     · 5 个核, 状态互相注入(纠缠耦合)
     · 内部连接随机固定(不训练) ← 这就是"河道已被地形决定"
     · 只训练读出层(线性)      ← 这就是"只改出口"
   对照: ① 1个核  ② 5个独立核(不耦合)  ③ 5个耦合核
   任务: 分类 / 加法 / 比较 / 奇偶 / 逻辑链 (含跨范围泛化)
"""
import numpy as np, random, time
random.seed(7); np.random.seed(7)

# ==================== 数据 ====================
CH = list("0123456789+-+=?,>") + ["<pad>"]
C2I = {c:i for i,c in enumerate(CH)}; V=len(CH); PAD=C2I["<pad>"]
def enc(s, L=14):
    ids=[C2I.get(c,PAD) for c in s[:L]]
    return np.array(ids+[PAD]*(L-len(ids)), np.int32)

def t_intent(n):
    M=["roam","energy","reflect"]; W=["量子","天气"]; C=["ls","df"]
    I=[]
    for m in M: I+=[("关掉 "+m,"OFF"),("开启 "+m,"ON")]
    for w in W: I+=[("搜索 "+w,"SEARCH"),(w+"是什么","ASK")]
    for c in C: I+=[("执行 "+c,"SHELL")]
    I+=[("看看世界","LOOK"),("新对话","CHAT"),("诊断","DIAG")]
    KS=sorted(set(k for _,k in I)); K={k:i for i,k in enumerate(KS)}
    o=[]
    for _ in range(n):
        tpl,kd=random.choice(I)
        if "%s" in tpl:
            pool=W if kd in("SEARCH","ASK") else (C if kd=="SHELL" else ["x"])
            tpl=tpl.replace("%s",random.choice(pool))
        o.append((tpl,K[kd]))
    return o, len(KS)

def t_add(lo,hi,n,ult=False):
    """加法: 预测个位数字(10类) 或 是否进位"""
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        if ult: o.append(("%d+%d"%(a,b), (a%10+b%10)%10))
        else:   o.append(("%d+%d"%(a,b), min(a+b,9)))
    return o

def t_cmp(lo,hi,n):
    return [("%d>%d"%(random.randint(lo,hi),random.randint(lo,hi)), None) for _ in range(n)]

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

def t_chain(ln,n):
    NS=list("ABCDEFGH")[:ln+1]; o=[]
    for _ in range(n):
        s="".join("%s>%s"%(NS[i],NS[i+1]) for i in range(ln))
        s+="?%s%s"%(NS[0],NS[-1])
        o.append((s, 1))
    return o

# ==================== 耦合水库 ====================
class Reservoir:
    def __init__(self, n_cores=5, H=32, din=V, rho=0.9, couple=1.0, seed=0):
        r=np.random.RandomState(seed)
        self.n, self.H, self.din = n_cores, H, din
        D = n_cores*H                       # 总状态维
        # 输入权重(共享)
        self.Win = (r.randn(din, H)*0.6).astype(np.float32)
        # 每核内部递归
        self.Wrec = (r.randn(H,H)/np.sqrt(H)*2.0).astype(np.float32)
        # 核间耦合(纠缠): 每个核读所有核的上一状态
        self.Wcpl = (r.randn(D, D)/np.sqrt(D)*couple).astype(np.float32)   # (D,D): 全状态→全状态
        # 每核偏置
        self.b = (r.randn(H)*0.1).astype(np.float32)
        # 谱半径归一(稳定)
        for i in range(n_cores):
            ev = max(abs(np.linalg.eigvals(self.Wrec)))
            self.Wrec = self.Wrec*(rho/max(ev,1e-6))
        self.nparam = self.Win.size + self.Wrec.size + self.Wcpl.size + self.b.size
    def run(self, x):
        """x: (T,) 或 (T,d) → 返回轨迹 (T, D) 和 特征"""
        T=len(x)
        if x.ndim==1: X=np.eye(self.din,dtype=np.float32)[x]
        else: X=x.astype(np.float32)
        H=self.H; n=self.n
        h=np.zeros((n,H),np.float32); traj=np.empty((T, n*H),np.float32)
        for t in range(T):
            flat=h.reshape(-1)
            # 每核: 输入 + 自身递归 + 其它核注入(纠缠)
            u = X[t]@self.Win + h@self.Wrec.T + (self.Wcpl@flat).reshape(n,H) + self.b
            h = np.tanh(u)
            traj[t]=h.reshape(-1)
        return traj
    def feats(self, s):
        """把一句文本 → 特征向量: 时间均值 + 末帧 + 方差"""
        tr = self.run(enc(s))
        return np.concatenate([tr.mean(0), tr[-1], tr.std(0)]).astype(np.float32)

# ==================== 读出层(闭式最小二乘, 零训练循环) ====================
def evaluate(res, tr, te, C, ridge=1e-3, multi=False):
    def build(data):
        X=np.array([res.feats(s) for s,_ in data])
        if multi:  # 多任务: one-hot 拼接
            Y=np.array([y for _,y in data])
        else: Y=np.array([y for _,y in data])
        return X,Y
    Xtr,Ytr=build(tr); Xte,Yte=build(te)
    D=Xtr.shape[1]
    if multi:
        Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
        W=np.linalg.solve(Xtr.T@Xtr+ridge*np.eye(D), Xtr.T@Yh)
    else:
        if C>1:
            Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
            W=np.linalg.solve(Xtr.T@Xtr+ridge*np.eye(D), Xtr.T@Yh)
        else:
            W=np.linalg.solve(Xtr.T@Xtr+ridge*np.eye(D), Xtr.T@Ytr)
    pred=(Xte@W)
    if C>1: acc=float((pred.argmax(1)==Yte).mean())
    else:   acc=float(((pred>0.5).astype(int)==Yte).mean())
    ntrain = D*C + Xtr.shape[1]*Xtr.shape[1]
    return acc

# ==================== 主实验 ====================
def main():
    t0=time.time()
    print("="*74)
    print("  5 个 1.3KB 核「纠缠耦合」成时序系统 —— 能力测试")
    print("="*74)

    # 三种配置
    cfgs=[
        ("1 个核 (1.3KB)",       dict(n_cores=1, H=12)),
        ("5 核 独立(不耦合)",     dict(n_cores=5, H=12, couple=0.0)),
        ("5 核 纠缠耦合",         dict(n_cores=5, H=12, couple=1.0)),
        ("5 核 强耦合",           dict(n_cores=5, H=12, couple=2.5)),
    ]

    # 任务集
    tr_i,C_i=t_intent(1500); te_i,_=t_intent(500)
    t_AD1=dict(name="个位加法(同分布)", tr=t_add(0,9,1200), te=t_add(0,9,400), C=10)
    t_AD2=dict(name="★加法跨范围泛化",  tr=t_add(0,9,1500), te=t_add(10,20,500), C=10)
    t_CM1=dict(name="比较(同分布)",     tr=t_cmpr(0,9,1200), te=t_cmpr(0,9,400), C=1)
    t_CM2=dict(name="★比较跨范围泛化",  tr=t_cmpr(0,9,1500), te=t_cmpr(10,99,500), C=1)
    t_PA1=dict(name="奇偶(同分布)",     tr=t_parity(0,9,1200), te=t_parity(0,9,400), C=1)
    t_PA2=dict(name="★奇偶跨范围泛化",  tr=t_parity(0,9,1500), te=t_parity(10,999,500), C=1)
    t_CH=dict(name="逻辑链3(传递)",     tr=t_chain(3,1200), te=t_chain(3,400), C=1)

    tasks=[("意图分类(10类)", tr_i, te_i, C_i, False)] + \
          [(d["name"], d["tr"], d["te"], d["C"], False) for d in
           (t_AD1,t_AD2,t_CM1,t_CM2,t_PA1,t_PA2,t_CH)]

    # 表头
    print("\n%-22s | %s" % ("任务", " | ".join("%-16s"%c[0] for c in cfgs)))
    print("-"*74)
    rows=[]
    for name, tr, te, C, multi in tasks:
        line="%-22s |" % name
        for cname, kw in cfgs:
            r=Reservoir(**kw)
            acc=evaluate(r, tr, te, C)
            line += " %-16s|" % ("%.1f%% (%s参数)"%(100*acc, f"{r.nparam:,}"))
        print(line, flush=True)
        rows.append((name, line))
    print("\n总耗时 %.0fs"%(time.time()-t0))

if __name__=="__main__": main()
