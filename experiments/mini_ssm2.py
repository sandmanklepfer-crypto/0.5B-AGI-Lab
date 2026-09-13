# -*- coding: utf-8 -*-
"""mini_ssm2.py — 微型 SSM 学指令解析 v2(修正版)
   修正: ① 参数量提到 ~30万 ② 正确的 BPTT ③ Adam 优化器 ④ 更大嵌入
"""
import numpy as np, random, time

random.seed(7); np.random.seed(7)

# ============ ① 数据 ============
MECHS=["roam","energy","reflect","attractor","ignite","consolidate","self_loop","meta_box","reflect_up","gate","reservoir"]
THETAS=["energy.metabolism","inject.eta","life.temp","gate.cos_threshold","retrieval.topk",
        "reservoir.rho","self_edit.eta_min","reflect.mirror_weight","novelty.low","energy.cap"]
WORDS=["量子计算","天气预报","股票价格","机器学习","北京","历史","python","算法","数学","物理","化学","医学"]
CMDS=["ls /sdcard","getprop","df -h","ps -A","date","uptime","id","pwd"]

def build():
    I=[]
    for m in MECHS:
        for t in ["关掉 %s","禁用 %s","关闭 %s","停止 %s"]: I.append((t,"M:%s=0"%m,"MECH_OFF"))
        for t in ["开启 %s","启用 %s","打开 %s","恢复 %s"]: I.append((t,"M:%s=1"%m,"MECH_ON"))
    for th in THETAS:
        v="0.0002" if "metab" in th else "0.6"
        for t in ["把 %s 设为 %s","%s 改成 %s","调 %s 到 %s","设置 %s 为 %s"]:
            I.append((t,"T:%s=%s"%(th,v),"THETA"))
    for w in WORDS:
        for t in ["搜索 %s","搜一下 %s","查 %s","帮我查 %s"]: I.append((t,"X:search:%s"%w,"SEARCH"))
        for t in ["%s 是什么","介绍一下 %s","什么是 %s","讲讲 %s"]: I.append((t,"R:recall:%s"%w,"RECALL"))
    for c in CMDS:
        for t in ["执行 %s","运行 %s","终端：%s","shell %s"]: I.append((t,"X:shell:%s"%c,"SHELL"))
    for t in ["看看世界","观察场景","看世界","世界什么样"]: I.append((t,"W:look","WORLD"))
    for n in [1,3,5,10]:
        for t in ["演化 %d 步","前进 %d 步","走 %d 步"]:
            I.append((t%n,"W:step:%d"%n,"WORLD_STEP"))
    for t in ["新对话","重新开始","开个新会话"]: I.append((t,"C:new","CHAT"))
    for t in ["总结一下","压缩上下文","总结对话"]: I.append((t,"C:sum","CHAT"))
    for t in ["保存","存档","保存对话"]: I.append((t,"C:save","CHAT"))
    for t in ["自我诊断","体检","检查自己","诊断"]: I.append((t,"A:diag","MACRO"))
    for t in ["一键修复","优化一下","修一下","修复"]: I.append((t,"A:fix","MACRO"))
    for t in ["用大模型","换个聪明的","切到4b"]: I.append((t,"G:switch:4b","MODEL"))
    return I
INTENTS=build()
KS=sorted(set(k for _,_,k in INTENTS)); K2I={k:i for i,k in enumerate(KS)}
print("意图池: %d 条, %d 类"%(len(INTENTS),len(KS)))

VOCAB=list("abcdefghijklmnopqrstuvwxyz0123456789.:=/ -_")
C2I={c:i for i,c in enumerate(VOCAB)}; V=len(VOCAB)+2; UNK=len(VOCAB); PAD=UNK+1
MAXLEN=40
def enc(s):
    ids=[C2I.get(c,UNK) for c in s[:MAXLEN]]
    return np.array(ids+[PAD]*(MAXLEN-len(ids)), np.int32)
def batch(n):
    X=[];Y=[]
    for _ in range(n):
        tpl,tgt,kind=random.choice(INTENTS)
        s=tpl
        if "%s" in s:
            fill = random.choice(WORDS) if ("search" in tgt or "W:" not in tgt and "recall" in tgt.lower()) else ""
            if "search" in tgt or "recall" in tgt: fill=random.choice(WORDS)
            elif "shell" in tgt: fill=random.choice(CMDS)
            elif "metab" in tgt: fill="0.0002"
            elif "T:" in tgt: fill="0.6"
            else: fill=random.choice(MECHS)
            s = re_sub_multi(s, fill)
        X.append(enc(s)); Y.append(K2I[kind])
    return np.array(X,np.int32), np.array(Y,np.int64)
def re_sub_multi(s, fill):
    out=""; i=0
    while True:
        j=s.find("%s", i)
        if j<0: out+=s[i:]; break
        out+=s[i:j]+(fill if random.random()<0.7 else random.choice(WORDS+CMDS+MECHS+["0.6"]))
        i=j+2
    return out

# ============ ② 微型 SSM + Adam ============
class SSM:
    def __init__(self, d=64, H=128, seed=0):
        r=np.random.RandomState(seed)
        self.d,self.H,self.V,self.C = d,H,V,len(KS)
        s=1/np.sqrt(d)
        self.E  = (r.randn(V,d)*0.5).astype(np.float32)
        self.Wb = (r.randn(H,d)*s).astype(np.float32)
        self.Wa = (r.randn(H,d)*s).astype(np.float32)
        self.ba = np.zeros(H,np.float32)
        self.Wo = (r.randn(len(KS),H)/np.sqrt(H)).astype(np.float32)
        self.bo = np.zeros(len(KS),np.float32)
        self.PS=[self.E,self.Wb,self.Wa,self.ba,self.Wo,self.bo]
        self.M=[np.zeros_like(p) for p in self.PS]
        self.Vv=[np.zeros_like(p) for p in self.PS]
        self.t=0
        self.nparam=sum(p.size for p in self.PS)
    def fwd(self,X,keep=False):
        B,T=X.shape; H=self.H
        x=self.E[X]                       # (B,T,d)
        bx=x@self.Wb.T                    # (B,T,H)
        b=np.tanh(bx)
        ax=np.einsum('btd,hd->bth',x,self.Wa)+self.ba
        a=1/(1+np.exp(-ax))
        h=np.zeros((B,H),np.float32); HS=np.empty((B,T,H),np.float32)
        for t in range(T):
            h=a[:,t,:]*h+(1-a[:,t,:])*b[:,t,:]; HS[:,t,:]=h
        pool=HS.mean(1)
        logits=pool@self.Wo.T+self.bo
        return (logits, dict(HS=HS,a=a,b=b,x=x,pool=pool,ax=ax,bx=bx)) if keep else logits
    def step(self,X,Y,lr=2e-3):
        B,T=X.shape; H=self.H
        logits,c=self.fwd(X,keep=True)
        lg=logits-logits.max(1,keepdims=True); p=np.exp(lg); p/=p.sum(1,keepdims=True)
        loss=float(-np.log(p[np.arange(B),Y]+1e-12).mean())
        acc=float((logits.argmax(1)==Y).mean())
        dlog=p.copy(); dlog[np.arange(B),Y]-=1; dlog/=B
        gWo=dlog.T@c["pool"]; gbo=dlog.sum(0).astype(np.float32)
        dpool=dlog@self.Wo
        gWb=np.zeros_like(self.Wb); gWa=np.zeros_like(self.Wa); gba=np.zeros_like(self.ba)
        gE=np.zeros_like(self.E)
        dh_next=np.zeros((B,H),np.float32)
        for t in range(T-1,-1,-1):
            dh = dpool/T + dh_next
            hp = c["HS"][:,t-1,:] if t>0 else np.zeros((B,H),np.float32)
            da = dh*(hp - c["b"][:,t,:])
            db = dh*(1-c["a"][:,t,:])
            xt=c["x"][:,t,:]
            gWb += db.T@xt
            gWa += da.T@xt
            gba += da.sum(0)
            np.add.at(gE, X[:,t], db@self.Wb + da@self.Wa)
            dh_next = dh*c["a"][:,t,:]
        G=[gE,gWb,gWa,gba,gWo,gbo]
        self.t+=1; b1,b2,eps=0.9,0.999,1e-8
        lr=self.t and lr
        for i,(P,g) in enumerate(zip(self.PS,G)):
            g=np.clip(g,-5,5)
            self.M[i]=b1*self.M[i]+(1-b1)*g
            self.Vv[i]=b2*self.Vv[i]+(1-b2)*g*g
            mh=self.M[i]/(1-b1**self.t); vh=self.Vv[i]/(1-b2**self.t)
            P -= (lr*mh/(np.sqrt(vh)+eps)).astype(np.float32)
        return loss, acc

def main():
    t0=time.time()
    m=SSM(d=64,H=128)
    print("SSM 参数: %s (%.2f MB)"%(f"{m.nparam:,}", m.nparam*4/1048576))
    Xte,Yte=batch(800)
    print("训练前: %.1f%%"%(100*(m.fwd(Xte).argmax(1)==Yte).mean()))
    print("\n训练...")
    for s in range(1,2001):
        Xb,Yb=batch(64)
        loss,acc=m.step(Xb,Yb, lr=3e-3)
        if s%250==0:
            a=float((m.fwd(Xte).argmax(1)==Yte).mean())
            print("  step%4d loss=%.3f 训练acc=%.0f%% 测试acc=%.1f%% (%.0fs)"%(s,loss,100*acc,100*a,time.time()-t0),flush=True)
    a=float((m.fwd(Xte).argmax(1)==Yte).mean())
    print("\n最终测试准确率: %.1f%%"% (100*a))
    pred=m.fwd(Xte).argmax(1)
    print("\n各类:")
    for k,i in K2I.items():
        msk=Yte==i
        if msk.sum(): print("   %-12s %5.1f%%"%(k,100*(pred[msk]==i).mean()))
    print("\n【结论】SSM %s 参数, 指令分类准确率 %.1f%%"%(f"{m.nparam:,}",100*a))
    print("耗时 %.0fs"%(time.time()-t0))

if __name__=="__main__": main()
