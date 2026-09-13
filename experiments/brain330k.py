# -*- coding: utf-8 -*-
"""brain330k.py — 330KB 小核的「推理与泛化」极限测试
   核心设计: 训练用小数字, 测试用大数字
        → 若模型只记住答案, 换数字必崩
        → 若学到"算法", 能泛化到未见范围
   任务:
     ① 加法      train a,b∈[0,15]   test a,b∈[50,99]   ← 跨范围泛化
     ② 比较      train a,b∈[0,15]   test a,b∈[50,99]
     ③ 逻辑链    train 3链          test 5链            ← 跨长度泛化
     ④ 序列规律  train 步长≤3       test 步长≤7
   模型: 微型 GRU(约8万参数 ≈ 320KB)
"""
import numpy as np, random, time
random.seed(7); np.random.seed(7)

# ==================== 分词: 逐位数字 ====================
CH = list("0123456789+=?<>") + ["<pad>","<eos>"]
C2I = {c:i for i,c in enumerate(CH)}
PAD = C2I["<pad>"]; EOS = C2I["<eos>"]; V = len(CH)
MAXLEN = 16
def enc(s):
    ids = [C2I.get(c,PAD) for c in s[:MAXLEN]]
    return np.array(ids + [PAD]*(MAXLEN-len(ids)), np.int32)

# ==================== 任务定义 ====================
def task_add(lo, hi, n):
    """a+b → 结果字符串(逐位)"""
    out=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        q="%d+%d="%(a,b); ans="%d"%(a+b)
        if len(q)>MAXLEN-4: continue
        out.append((q, ans))
    return out

def task_cmp(lo, hi, n):
    """a?b → < 或 >  (等价推理: 比大小)"""
    out=[]
    for _ in range(n):
        a=random.randint(lo,hi); b=random.randint(lo,hi)
        if a==b: a+=1
        q="%d?%d="%(a,b); ans="<" if a<b else ">"
        out.append((q,ans))
    return out

def task_chain(ln, n):
    """A>B,B>C,...  问 A?最后 → 传递性推理(链越长越难)"""
    out=[]
    names=list("ABCDEFGH")[:ln+1]
    for _ in range(n):
        if len(names)<ln+1: continue
        q="".join("%s>%s"%(names[i],names[i+1]) for i in range(ln))
        q += "?%s%s="%(names[0],names[-1])
        if len(q)>MAXLEN: continue
        out.append((q, ">"))
    return out

def task_seq(stepmax, n):
    """等差数列: 首项,公差 → 下一项"""
    out=[]
    for _ in range(n):
        a=random.randint(1,9); d=random.randint(1,stepmax); L=3
        s=[a+i*d for i in range(L)]
        q=",".join(str(x) for x in s)+"=?"; nxt=str(a+L*d)
        if len(q)>MAXLEN-3: continue
        out.append((q,nxt))
    return out

# ==================== 微型 GRU (numpy) ====================
class Gru:
    def __init__(self, d=64, H=128, seed=0):
        r=np.random.RandomState(seed)
        self.d,self.H = d,H
        s=1/np.sqrt(H)
        self.E = (r.randn(V,d)*0.3).astype(np.float32)
        # 三门: z(更新) r(重置) h(候选)
        self.Wz=(r.randn(H,d)*s).astype(np.float32); self.Uz=(r.randn(H,H)*s).astype(np.float32); self.bz=np.zeros(H,np.float32)
        self.Wr=(r.randn(H,d)*s).astype(np.float32); self.Ur=(r.randn(H,H)*s).astype(np.float32); self.br=np.zeros(H,np.float32)
        self.Wh=(r.randn(H,d)*s).astype(np.float32); self.Uh=(r.randn(H,H)*s).astype(np.float32); self.bh=np.zeros(H,np.float32)
        self.Wo=(r.randn(V,H)/np.sqrt(H)).astype(np.float32); self.bo=np.zeros(V,np.float32)
        self.PS=[self.E,self.Wz,self.Uz,self.bz,self.Wr,self.Ur,self.br,
                 self.Wh,self.Uh,self.bh,self.Wo,self.bo]
        self.M=[np.zeros_like(p) for p in self.PS]; self.Vv=[np.zeros_like(p) for p in self.PS]; self.t=0
        self.nparam=sum(p.size for p in self.PS)
    @staticmethod
    def sig(x): return 1.0/(1.0+np.exp(-np.clip(x,-30,30)))

    def fwd(self, X, keep=False):
        B,T = X.shape; H=self.H
        x = self.E[X]                                   # (B,T,d)
        h = np.zeros((B,H),np.float32)
        caches=[]
        for t in range(T):
            xt=x[:,t,:]
            z=self.sig(xt@self.Wz.T + h@self.Uz.T + self.bz)
            r=self.sig(xt@self.Wr.T + h@self.Ur.T + self.br)
            hc=np.tanh(xt@self.Wh.T + (r*h)@self.Uh.T + self.bh)
            hn=(1-z)*h + z*hc
            if keep: caches.append((xt,h,z,r,hc,hn))
            h=hn
        logits = h@self.Wo.T + self.bo
        return (logits, h, caches) if keep else logits

    def step(self, X, Y, lr=3e-3):
        """单步训练: 最后一个位置的 token 预测"""
        B,T=X.shape
        logits,h,caches = self.fwd(X,keep=True)
        lg=logits-logits.max(1,keepdims=True); p=np.exp(lg); p/=p.sum(1,keepdims=True)
        loss=float(-np.log(p[np.arange(B),Y]+1e-12).mean())
        acc=float((logits.argmax(1)==Y).mean())
        dlog=p.copy(); dlog[np.arange(B),Y]-=1; dlog/=B
        gWo=dlog.T@h; gbo=dlog.sum(0).astype(np.float32)
        dh=dlog@self.Wo
        gE=np.zeros_like(self.E)
        gWz=np.zeros_like(self.Wz); gUz=np.zeros_like(self.Uz); gbr_=np.zeros_like(self.bz)
        gWr=np.zeros_like(self.Wr); gUr=np.zeros_like(self.Ur); gbr2=np.zeros_like(self.br)
        gWh=np.zeros_like(self.Wh); gUh=np.zeros_like(self.Uh); gbb=np.zeros_like(self.bh)
        for t in range(T-1,-1,-1):
            xt,hp,z,r,hc,hn = caches[t]
            dz = dh*(hc-hp) * (z*(1-z))
            dhc= dh*z * (1-hc*hc)
            gWh += dhc.T@xt
            gbb += dhc.sum(0)
            gUh += dhc.T@(r*hp)
            drh = dhc@self.Uh
            dr = drh*hp*(r*(1-r))
            gWr += dr.T@xt; gUr += dr.T@hp; gbr2 += dr.sum(0)
            gWz += dz.T@xt; gUz += dz.T@hp; gbr_ += dz.sum(0)
            dh = dh*(1-z) + dz@self.Uz + dr@self.Ur + drh*r
            np.add.at(gE, X[:,t], dz@self.Wz + dr@self.Wr + dhc@self.Wh)
        Gh=[gE,gWz,gUz,gbr_,gWr,gUr,gbr2,gWh,gUh,gbb,gWo,gbo]
        self.t+=1; b1,b2,eps=0.9,0.999,1e-8
        for i,(P,g) in enumerate(zip(self.PS,Gh)):
            np.clip(g,-5,5,out=g)
            self.M[i]=b1*self.M[i]+(1-b1)*g
            self.Vv[i]=b2*self.Vv[i]+(1-b2)*g*g
            mh=self.M[i]/(1-b1**self.t); vh=self.Vv[i]/(1-b2**self.t)
            P -= (lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return loss,acc

    def predict(self, q):
        """预测答案首字符(评估用)"""
        X=enc(q).reshape(1,-1)
        return int(self.fwd(X)[0].argmax())

def eval_acc(m, data, kind="first"):
    ok=0
    for q,a in data:
        pred=m.predict(q)
        gold=enc(a)[0] if a else PAD
        ok += (pred==gold)
    return ok/max(len(data),1)

# ==================== 训练+测试 ====================
def run(name, tr, te_same, te_gen, steps=3000, bs=64, lr=3e-3):
    m=Gru()
    print("\n"+"="*66)
    print(" 【%s】"%name)
    print("="*66)
    print("  模型: %s 参数 (%.0f KB)"%(f"{m.nparam:,}", m.nparam*4/1024))
    print("  训练集 %d 条" % len(tr))
    t0=time.time()
    for s in range(1,steps+1):
        idx=[random.randrange(len(tr)) for _ in range(bs)]
        X=np.stack([enc(tr[i][0]) for i in idx])
        Y=np.array([enc(tr[i][1])[0] for i in idx])
        loss,acc=m.step(X,Y,lr)
        if s%800==0:
            a1=eval_acc(m,te_same); a2=eval_acc(m,te_gen)
            print("   step%5d loss=%.3f | 同分布 %.0f%% | 泛化 %.0f%%  (%.0fs)"%(
                s,loss,100*a1,100*a2,time.time()-t0),flush=True)
    a1=eval_acc(m,te_same); a2=eval_acc(m,te_gen)
    print("   ── 最终 ──")
    print("   同分布(见过的范围): %.1f%%"%(100*a1))
    print("   ★ 泛化(从未见过的范围): %.1f%% ★"%(100*a2))
    return m.nparam, a1, a2

if __name__=="__main__":
    print("="*66)
    print("  330KB 小核的推理与泛化极限")
    print("="*66)
    res=[]
    # ① 加法
    tr=task_add(0,15,4000); a=task_add(0,15,300); b=task_add(50,99,300)
    res.append(("加法(数位泛化)",)+run("加法: 训练0-15 → 测50-99", tr,a,b, steps=3000))
    # ② 比较
    tr=task_cmp(0,15,4000); a=task_cmp(0,15,300); b=task_cmp(50,99,300)
    res.append(("比较(数位泛化)",)+run("比较: 训练0-15 → 测50-99", tr,a,b, steps=2000))
    # ③ 逻辑链
    tr=task_chain(2,3000)+task_chain(3,3000); a=task_chain(3,300); b=task_chain(5,300)
    res.append(("传递推理(链长泛化)",)+run("逻辑链: 训练2-3链 → 测5链", tr,a,b, steps=2500))
    # ④ 数列
    tr=task_seq(3,4000); a=task_seq(3,300); b=task_seq(7,300)
    res.append(("数列(步长泛化)",)+run("数列: 训练步长≤3 → 测步长≤7", tr,a,b, steps=2500))

    print("\n"+"="*66)
    print("  总结 (参数量 %s / %.0f KB)"%(f"{res[0][1]:,}", res[0][1]*4/1024))
    print("="*66)
    print("  %-22s %-14s %s"%("任务","同分布","★泛化★"))
    print("  "+"-"*58)
    for name,np_,a1,a2 in res:
        tag = "✅ 学到了算法" if a2>0.6 else ("⚠️ 部分" if a2>0.3 else "❌ 只是记住")
        print("  %-22s %6.1f%% %12.1f%%  %s"%(name,100*a1,100*a2,tag))
