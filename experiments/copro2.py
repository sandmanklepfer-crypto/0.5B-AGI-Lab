# -*- coding: utf-8 -*-
"""copro2.py — 推理协处理器验证 v2: LSTM(带门控) vs 普通RNN vs 无循环
   任务: adding problem(长程状态追踪) —— transformer 的经典弱项
"""
import numpy as np, time

def sig(x): return 1.0/(1.0+np.exp(-np.clip(x,-30,30)))

def gen(B,T):
    x=np.random.rand(B,T,2).astype(np.float32); x[:,:,1]=0
    i1=np.random.randint(0,T,B); i2=np.random.randint(0,T,B)
    s=(i1==i2); i2[s]=(i2[s]+1)%T
    r=np.arange(B); x[r,i1,1]=1; x[r,i2,1]=1
    y=x[r,i1,0]+x[r,i2,0]
    return x, y.astype(np.float32)

class LSTM:
    def __init__(self,H=64,seed=0):
        r=np.random.RandomState(seed); self.H=H
        k=1.0/np.sqrt(H)
        self.Wx=(r.randn(4*H,2)*0.5).astype(np.float32)
        self.Wh=(r.randn(4*H,H)*k).astype(np.float32)
        self.b=np.zeros(4*H,np.float32)
        self.Wo=(r.randn(1,H)*k).astype(np.float32); self.bo=np.zeros(1,np.float32)
        self.m={n:np.zeros_like(getattr(self,n)) for n in ("Wx","Wh","b","Wo","bo")}
        self.v={n:np.zeros_like(getattr(self,n)) for n in ("Wx","Wh","b","Wo","bo")}
        self.t=0
    def np_(self): return self.Wx.size+self.Wh.size+self.b.size+self.Wo.size+1
    def forward(self,x):
        B,T,_=x.shape; H=self.H
        h=np.zeros((B,H),np.float32); c=np.zeros((B,H),np.float32)
        hs=np.zeros((B,T,H),np.float32); cs=np.zeros((B,T,H),np.float32)
        hs_p=np.zeros((B,T,H),np.float32)
        gates=np.zeros((B,T,4,H),np.float32)
        for t in range(T):
            hp=h
            z=x[:,t,:]@self.Wx.T + h@self.Wh.T + self.b
            i=sig(z[:,0:H]); f=sig(z[:,H:2*H]); o=sig(z[:,2*H:3*H]); g=np.tanh(z[:,3*H:4*H])
            c=f*c+i*g; h=o*np.tanh(c)
            hs[:,t,:]=h; cs[:,t,:]=c; hs_p[:,t,:]=hp
            gates[:,t,0]=i; gates[:,t,1]=f; gates[:,t,2]=o; gates[:,t,3]=g
        out=hs[:,-1,:]@self.Wo.T+self.bo
        return out, (hs,cs,hs_p,gates)
    def step(self,x,y,lr=0.01,clip=5.0):
        B,T,_=x.shape; H=self.H
        out,(hs,cs,hs_p,gates)=self.forward(x)
        loss=float(np.mean((out[:,0]-y)**2))
        dout=(2*(out[:,0]-y)/B)[:,None]
        gWo=dout.T@hs[:,-1,:]; gbo=np.array([dout.sum()],np.float32)
        dh=dout@self.Wo; dc=np.zeros((B,H),np.float32)
        gWx=np.zeros_like(self.Wx); gWh=np.zeros_like(self.Wh); gb=np.zeros_like(self.b)
        for t in range(T-1,-1,-1):
            i=gates[:,t,0]; f=gates[:,t,1]; o=gates[:,t,2]; g=gates[:,t,3]
            c=cs[:,t,:]; cp=cs[:,t-1,:] if t>0 else np.zeros((B,H),np.float32)
            do=dh*np.tanh(c)
            dc=dh*o*(1-np.tanh(c)**2)+dc
            df=dc*cp; di=dc*g; dg=dc*i
            dc=dc*f
            dz=np.concatenate([di*i*(1-i), df*f*(1-f), do*o*(1-o), dg*(1-g*g)],axis=1)
            gWx+=dz.T@x[:,t,:]; gWh+=dz.T@hs_p[:,t,:]; gb+=dz.sum(0)
            dh=dz@self.Wh
        for P,G in ((self.Wx,gWx),(self.Wh,gWh),(self.b,gb),(self.Wo,gWo),(self.bo,gbo)):
            n={id(self.Wx):"Wx",id(self.Wh):"Wh",id(self.b):"b",id(self.Wo):"Wo",id(self.bo):"bo"}[id(P)]
            np.clip(G,-clip,clip,out=G)
            # Adam
            self.t+=1
            self.m[n]=0.9*self.m[n]+0.1*G; self.v[n]=0.999*self.v[n]+0.001*G*G
            mh=self.m[n]/(1-0.9**self.t); vh=self.v[n]/(1-0.999**self.t)
            P-=lr*mh/(np.sqrt(vh)+1e-8)
        return loss

def run(T, steps, B=32):
    print("\n"+"="*58)
    print("  任务: T=%d 长程求和(找两个标记位并相加)"%T)
    print("="*58)
    m=LSTM(H=64,seed=1)
    t0=time.time(); ls=[]
    for s in range(steps):
        x,y=gen(B,T); ls.append(m.step(x,y,lr=0.01))
        if s%max(1,steps//5)==0 and s>0: print("    step%4d loss=%.5f (%.0fs)"%(s,np.mean(ls[-20:]),time.time()-t0))
    xt,yt=gen(300,T); o,_=m.forward(xt); mse=float(np.mean((o[:,0]-yt)**2))
    print("  [LSTM %5d参数] 训练loss %.5f → 测试MSE %.5f (%.0fs)"%(m.np_(),np.mean(ls[-20:]),mse,time.time()-t0))
    print("      → %s"%("✅ 完美学会长程状态追踪" if mse<0.01 else ("⚠️ 部分" if mse<0.05 else "❌ 没学会")))
    return mse

if __name__=="__main__":
    print("推理协处理器验证: LSTM(64隐藏) 能否干掉 transformer 的经典弱项")
    for T,st in ((50,400),(200,600)):
        run(T,st)
