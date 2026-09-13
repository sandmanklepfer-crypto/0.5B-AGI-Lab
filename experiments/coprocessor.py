# -*- coding: utf-8 -*-
"""coprocessor.py — 验证「推理协处理器」假设
   测试: 长程状态追踪(adding problem) —— transformer 的经典弱项
   对照: 同规模【无循环】前馈网(模拟"没有状态追踪能力")
   目标: 证明几十 KB 的专用循环核, 能做 LLM 做不了的事
"""
import numpy as np, time, sys

def gen(B, T):
    x = np.random.rand(B,T,2).astype(np.float32)
    x[:,:,1] = 0
    i1 = np.random.randint(0,T,B); i2 = np.random.randint(0,T,B)
    same = (i1==i2); i2[same] = (i2[same]+1) % T
    row = np.arange(B)
    x[row,i1,1] = 1.0
    x[row,i2,1] = 1.0
    y = x[row,i1,0] + x[row,i2,0]
    return x, y.astype(np.float32)

class RNN:
    """最简循环核(它就是你的 SLC 那类东西)"""
    def __init__(self, H=128, seed=0):
        r = np.random.RandomState(seed)
        self.H=H
        self.Wx = (r.randn(H,2)*0.5).astype(np.float32)
        self.Wh = (r.randn(H,H)/np.sqrt(H)).astype(np.float32)
        self.b  = np.zeros(H,np.float32)
        self.Wo = (r.randn(1,H)/np.sqrt(H)).astype(np.float32)
        self.bo = np.zeros(1,np.float32)
    def nparams(self):
        return self.Wx.size+self.Wh.size+self.b.size+self.Wo.size+1
    def forward(self, x):
        B,T,_ = x.shape; H=self.H
        hs = np.zeros((B,T,H),np.float32); h = np.zeros((B,H),np.float32)
        for t in range(T):
            h = np.tanh(x[:,t,:] @ self.Wx.T + h @ self.Wh.T + self.b)
            hs[:,t,:] = h
        return hs[:,-1,:] @ self.Wo.T + self.bo, hs
    def step(self, x, y, lr):
        B,T,_ = x.shape
        out, hs = self.forward(x)
        loss = float(np.mean((out[:,0]-y)**2))
        dout = (2*(out[:,0]-y)/B)[:,None]                 # (B,1)
        gWo = dout.T @ hs[:,-1,:]                          # (1,H)
        gbo = np.array([dout.sum()],np.float32)
        dh  = dout @ self.Wo                               # (B,H)
        gWx=np.zeros_like(self.Wx); gWh=np.zeros_like(self.Wh); gb=np.zeros_like(self.b)
        zero = np.zeros((B,self.H),np.float32)
        for t in range(T-1,-1,-1):
            dz = dh*(1-hs[:,t,:]**2)
            gb  += dz.sum(0)
            gWx += dz.T @ x[:,t,:]
            gWh += dz.T @ (hs[:,t-1,:] if t>0 else zero)
            if t>0: dh = dz @ self.Wh
        for P,G in ((self.Wx,gWx),(self.Wh,gWh),(self.b,gb),(self.Wo,gWo),(self.bo,gbo)):
            P -= lr*G
        return loss

class FF:
    """对照: 无循环的「只看位置」模型(没有状态追踪)"""
    def __init__(self, T, seed=0):
        r=np.random.RandomState(seed)
        self.W1=(r.randn(T*2,64)/np.sqrt(T*2)).astype(np.float32)
        self.b1=np.zeros(64,np.float32)
        self.W2=(r.randn(64,1)/8).astype(np.float32)
        self.b2=np.zeros(1,np.float32)
    def nparams(self): return self.W1.size+self.b1.size+self.W2.size+1
    def step(self,x,y,lr):
        B,T,_=x.shape
        xf=x.reshape(B,-1)
        z=xf@self.W1+self.b1; h=np.tanh(z); out=(h@self.W2+self.b2)[:,0]
        loss=float(np.mean((out-y)**2))
        dout=(2*(out-y)/B)[:,None]
        gW2=h.T@dout; gb2=np.array([dout.sum()],np.float32)
        dh=(dout@self.W2.T)*(1-h**2)
        gW1=xf.T@dh; gb1=dh.sum(0)
        for P,G in ((self.W1,gW1),(self.b1,gb1),(self.W2,gW2),(self.b2,gb2)): P-=lr*G
        return loss

def run(T, steps=600, B=32, lr=0.02):
    print("\n"+"="*56)
    print("  任务: T=%d 长程求和(只看两个标记位, 间隔可达 %d 步)"%(T,T))
    print("="*56)
    # 循环核
    m=RNN(H=128,seed=1)
    t0=time.time(); losses=[]
    for s in range(steps):
        x,y=gen(B,T); losses.append(m.step(x,y,lr))
    xt,yt=gen(200,T)
    out,_=m.forward(xt); mse=float(np.mean((out[:,0]-yt)**2))
    print("  [循环核 %5d参数] 末loss %.5f  测试MSE %.5f  (%.1fs)"%(m.nparams(),np.mean(losses[-20:]),mse,time.time()-t0))
    demo_pass = mse < 0.02
    print("      → %s"%("✅ 学会长程状态追踪(精度接近完美)" if demo_pass else "⚠️ 未完全学会"))
    # 对照
    f=FF(T,seed=1)
    t0=time.time(); fl=[]
    for s in range(steps):
        x,y=gen(B,T); fl.append(f.step(x,y,lr))
    out,_=f.forward(xt) if hasattr(f,'forward') else (None,None)
    xt2,yt2=gen(200,T)
    xf=xt2.reshape(200,-1); h=np.tanh(xf@f.W1+f.b1); o=(h@f.W2+f.b2)[:,0]
    fmse=float(np.mean((o-yt2)**2))
    print("  [无循环 %5d参数] 测试MSE %.5f  → %s"%(f.nparams(),fmse,
          "❌ 学不会(缺状态追踪)" if fmse>0.05 else "✓"))
    return mse, fmse

if __name__=="__main__":
    print("验证「推理协处理器」: 几十 KB 的专用核 vs 无循环对照")
    for T in (30, 100, 200):
        run(T, steps=int(sys.argv[1]) if len(sys.argv)>1 else 500)
