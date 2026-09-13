# -*- coding: utf-8 -*-
"""fractal.py — 分形树状纠缠
   结构(参数总量固定):
     底层 30 个极小核 → 每 6 个合并成 1 个中层核(5个) → 5个合并成1个顶层核
     同构: 6合1 的规则在两层重复(自相似)
   对照:
     F0 平铺(5核全连)
     F1 两层树(30→5)
     F2 三层树(30→5→1)
     F3 三层树 + 层间回溯(子→父→子, 双向)
   任务: 加法同分布 + 跨范围泛化(基线=10%)
"""
import numpy as np, random, hashlib
random.seed(7); np.random.seed(7)

def t_add(lo,hi,n):
    return [(random.randint(lo,hi),random.randint(lo,hi),(random.randint(lo,hi)+random.randint(lo,hi))%10) for _ in range(n)]
def t_add2(lo,hi,n):
    o=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        o.append((a,b,(a+b)%10))
    return o

# ---------- 输入编码 ----------
def enc_in(a,b,D=16):
    """把两个数编成输入向量(含个位信息, 避免纯字符缺陷)"""
    v=np.zeros(D,np.float32)
    v[0]=a/100.0; v[1]=b/100.0
    v[2]=(a%10)/10.0; v[3]=(b%10)/10.0
    v[4]=((a%10)+(b%10))/18.0
    v[5]=(a%10)*(b%10)/81.0
    v[6]=a%2; v[7]=b%2
    v[8]=a%3/3.0; v[9]=b%3/3.0
    v[10]=a%5/5.0; v[11]=b%5/5.0
    v[12]=(a//10)%10/10.0; v[13]=(b//10)%10/10.0
    return v

# ================= 分形纠缠水库 =================
class Fractal:
    """树状结构: L0(30极小) → L1(5中) → L2(1大)
       每层: 6合1 / 5合1, 同构重复"""
    def __init__(self, mode="F2", H0=6, seed=0, rho=0.9):
        r=np.random.RandomState(seed)
        self.H0=H0
        self.level=[6,5]            # 6合1, 再5合1
        self.mode=mode
        # L0: 30 个极小核, 每个 H0 维
        self.n0 = 30
        self.H0 = H0
        D0 = self.n0*self.H0
        # L1: 5 个中核, 每个 H1 维
        self.n1 = 5
        self.H1 = 24                # 5*24=120
        # L2: 1 个大核, H2 维
        self.H2 = 64
        # --- 参数 ---
        din = 16
        self.Win = (r.randn(din, self.H0)*0.8).astype(np.float32)          # 共享输入投影(30核共用)
        self.Wrec0= (r.randn(self.H0,self.H0)/np.sqrt(self.H0)*2).astype(np.float32)
        ev=max(abs(np.linalg.eigvals(self.Wrec0))); self.Wrec0=self.Wrec0*(rho/max(ev,1e-6))
        # 6合1: 从 L0(30核) → L1(5核): 每6个L0核 → 1个L1核
        self.Wu1 = (r.randn(self.n1, self.H1, 6*self.H0)/np.sqrt(6*self.H0)).astype(np.float32)
        # 5合1: L1(5核) → L2(1核)
        self.Wu2 = (r.randn(self.H2, 5*self.H1)/np.sqrt(5*self.H1)).astype(np.float32)
        # L1/L2 自身递归
        self.Wr1 = (r.randn(self.H1,self.H1)/np.sqrt(self.H1)*2).astype(np.float32)
        self.Wr2 = (r.randn(self.H2,self.H2)/np.sqrt(self.H2)*2).astype(np.float32)
        # 回溯(子←父): F3 用
        self.Wd1 = (r.randn(6*self.H0, self.H1)/np.sqrt(self.H1)*0.5).astype(np.float32)
        self.Wd2 = (r.randn(5*self.H1, self.H2)/np.sqrt(self.H2)*0.5).astype(np.float32)
        # 平铺模式(F0)用: 全连接
        self.Wflat = (r.randn(D0,D0)/np.sqrt(D0)).astype(np.float32)
        # 读出
        self.nparam = sum(p.size for p in [self.Win,self.Wrec0,self.Wu1,self.Wu2,self.Wr1,self.Wr2,self.Wd1,self.Wd2,self.Wflat])

    def run(self, x):
        """x: (din,) 输入 → 返回轨迹(T=8 迭代)"""
        T=8
        H0,self_H1 = self.H0, self.H1
        h0=np.zeros((self.n0,H0),np.float32)
        h1=np.zeros((self.n1,self.H1),np.float32)
        h2=np.zeros(self.H2,np.float32)
        traj=[]
        for t in range(T):
            u = x@self.Win
            # ---- L0: 30 个极小核各自递归(同构) ----
            h0_new = np.tanh(h0@self.Wrec0.T + u)
            if self.mode=="F0":
                f0=h0_new.reshape(-1)
                f0 = np.tanh(self.Wflat@f0)
                h0_new = (0.7*h0_new.reshape(-1)+0.3*f0).reshape(self.n0,H0)
            # 回溯(F3)
            if self.mode=="F3":
                h0_new = h0_new + 0.3*(h1@self.Wd1.reshape(self.n1,self.H1,6*H0).transpose(0,2,1).reshape(-1,6*H0).T if False else 0).reshape(self.n0,H0) if False else h0_new
            h0 = h0_new
            # ---- 6合1: 30 个核 → 5 个中核 ----
            g0 = h0.reshape(self.n1, 6*H0)              # 每6个一组
            z1 = np.einsum('nh,ih->ni', g0, self.Wu1.reshape(self.n1,self.H1,6*H0)[0]) if False else \
                 np.stack([self.Wu1[i]@g0[i] for i in range(self.n1)])
            h1_new = np.tanh(z1 + h1@self.Wr1.T)
            if self.mode=="F3":
                h1_new = h1_new + 0.3*(self.Wd2.reshape(5,self.H1,self.H2)@h2).transpose(0,2,1)[0] if False else h1_new
            h1 = h1_new
            # ---- 5合1: 5 个中核 → 1 个大核 ----
            z2 = self.Wu2 @ h1.reshape(-1)
            h2 = np.tanh(z2 + self.Wr2@h2)
            # 回溯: 大核 → 中核(F3)
            if self.mode=="F3":
                fb = (self.Wd2@h2).reshape(self.n1,self.H1)
                h1 = h1 + 0.3*fb
            traj.append(np.concatenate([h0.reshape(-1), h1.reshape(-1), h2]))
        return np.array(traj)
    def feats(self,a,b):
        tr=self.run(enc_in(a,b))
        return np.concatenate([tr.mean(0), tr[-1], tr.std(0)]).astype(np.float32)

def ev(m, tr, te, C=10):
    Xtr=np.array([m.feats(a,b) for a,b,_ in tr]); Ytr=np.array([y for _,_,y in tr])
    Xte=np.array([m.feats(a,b) for a,b,_ in te]); Yte=np.array([y for _,_,y in te])
    Yh=np.zeros((len(Ytr),C),np.float32); Yh[np.arange(len(Ytr)),Ytr]=1
    W=np.linalg.solve(Xtr.T@Xtr+1e-3*np.eye(Xtr.shape[1]), Xtr.T@Yh)
    return float(((Xte@W).argmax(1)==Yte).mean())

def main():
    print("="*70)
    print("  分形树状纠缠 (30极小→5中→1大, 自相似6合1)")
    print("="*70)
    tr=t_add2(0,9,1500)
    sets=[("同分布 0-9", t_add2(0,9,600)),
          ("★泛化 10-30", t_add2(10,30,600)),
          ("★泛化 50-99", t_add2(50,99,600))]
    print("\n%-16s"%"配置" + "".join("| %-14s"%s[0] for s in sets) + "| %s"%("参数"))
    print("-"*70)
    for mode,name in [("F0","F0 平铺全连"),("F2","F2 两层树(30→5)"),("F3","F3 三层树+回溯")]:
        m=Fractal(mode=mode, H0=6)
        line="%-16s"%name
        for sname,data in sets:
            line += "| %-14s"%("%.1f%%"%(100*ev(m,tr,data)))
        line += "| %s"%f"{m.nparam:,}"
        print(line, flush=True)
    print("\n(基线: 10分类瞎猜=10%)")

if __name__=="__main__": main()
