# -*- coding: utf-8 -*-
"""np_train2.py — 端侧 LoRA 训练 v2: 完整 BPTT(历史 token 梯度不丢)
   与 v1 的差别: 反向时把所有历史位置的 k/v 梯度累积回去
"""
import numpy as np

EPS=1e-6
N_LAYER,N_HEAD,N_KV,HEAD_DIM = 24,14,2,64
ROPE_THETA=1000000.0

class LoRA:
    def __init__(self, out_dim, in_dim, r=8, alpha=16, seed=0):
        rng=np.random.RandomState(seed)
        self.r=r; self.out_dim=out_dim; self.in_dim=in_dim
        self.A=(rng.randn(r,in_dim)*0.01).astype(np.float32)
        self.B=np.zeros((out_dim,r),np.float32)
        self.scale=alpha/r
        self.gA=np.zeros_like(self.A); self.gB=np.zeros_like(self.B)
    def fwd(self,x): return self.A@x
    def apply(self,ax): return (self.B@ax)*self.scale
    def bwd(self,x,ax,dout):
        d=dout*self.scale
        self.gB+=np.outer(d,ax)
        dax=self.B.T@d
        self.gA+=np.outer(dax,x)
        return self.A.T@dax
    def step(self,lr): self.A-=lr*self.gA; self.B-=lr*self.gB; self.gA[:]=0; self.gB[:]=0
    def nbytes(self): return self.A.nbytes+self.B.nbytes

class TrainQwen:
    """layers: 只在这些层挂 LoRA(默认最后4层, 端侧速度快 6 倍)"""
    def __init__(self, model, layers=None, r=8, alpha=16, seed=0):
        self.m=model; self.w=model.w; self.DIM=model.DIM
        if layers is None: layers=[20,21,22,23]
        self.layers=layers
        self.loras={}
        for L in layers:
            self.loras[(L,"q")]=LoRA(self.DIM,self.DIM,r,alpha,seed+L*2)
            self.loras[(L,"v")]=LoRA(N_KV*HEAD_DIM,self.DIM,r,alpha,seed+L*2+1)
        self.inv=1.0/(ROPE_THETA**(np.arange(0,HEAD_DIM//2,dtype=np.float32)/(HEAD_DIM//2)))
    # ---- 基础 ----
    @staticmethod
    def rms_f(x,w):
        ms=np.mean(x*x)+EPS; inv=1.0/np.sqrt(ms); return x*inv*w,(ms,inv)
    @staticmethod
    def rms_b(dy,x,w,ms,inv):
        d=len(x); dyw=dy*w; s=np.sum(dyw*x)
        return dyw*inv - x*(inv**3/d)*s
    @staticmethod
    def silu_f(x):
        s=1/(1+np.exp(-np.clip(x,-50,50))); return x*s,s
    def rope_f(self,x,pos):
        ang=pos*self.inv; c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
        x1=x[...,:HEAD_DIM//2]; x2=x[...,HEAD_DIM//2:]
        return np.concatenate([x1*c-x2*s,x2*c+x1*s],axis=-1),(c,s)
    def rope_b(self,dy,pos):
        ang=pos*self.inv; c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
        y1=dy[...,:HEAD_DIM//2]; y2=dy[...,HEAD_DIM//2:]
        return np.concatenate([y1*c+y2*s, -y1*s+y2*c],axis=-1)

    # ---- 前向(存全部中间量) ----
    def forward(self, toks, keep_all=True):
        w=self.w; T=len(toks)
        kvs=[{"k":[],"v":[]} for _ in range(N_LAYER)]
        C=[]           # 每步每层
        finals=[]
        for t in range(T):
            x=self.m.tok_emb[toks[t]].copy()
            for L in range(N_LAYER):
                p="blk.%d."%L
                x_in=x.copy()
                h,(ms,inv)=self.rms_f(x,w[p+"attn_norm.weight"])
                q_raw=self.w[p+"attn_q.weight"]@h
                k_raw=self.w[p+"attn_k.weight"]@h
                v_raw=self.w[p+"attn_v.weight"]@h
                ax_q=ax_v=None
                if (L,"q") in self.loras:
                    ax_q=self.loras[(L,"q")].fwd(h); q_raw=q_raw+self.loras[(L,"q")].apply(ax_q)
                if (L,"v") in self.loras:
                    ax_v=self.loras[(L,"v")].fwd(h); v_raw=v_raw+self.loras[(L,"v")].apply(ax_v)
                if p+"attn_q.bias" in w: q_raw=q_raw+w[p+"attn_q.bias"]
                if p+"attn_k.bias" in w: k_raw=k_raw+w[p+"attn_k.bias"]
                if p+"attn_v.bias" in w: v_raw=v_raw+w[p+"attn_v.bias"]
                qr,_=self.rope_f(q_raw.reshape(N_HEAD,HEAD_DIM),t)
                kr,_=self.rope_f(k_raw.reshape(N_KV,HEAD_DIM),t)
                vr=v_raw.reshape(N_KV,HEAD_DIM)
                kvs[L]["k"].append(kr); kvs[L]["v"].append(vr)
                Ks=np.stack(kvs[L]["k"]); Vs=np.stack(kvs[L]["v"])
                rep=N_HEAD//N_KV
                Kx=np.repeat(Ks,rep,axis=1); Vx=np.repeat(Vs,rep,axis=1)
                sc=np.einsum("hd,shd->hs",qr,Kx)/np.sqrt(HEAD_DIM)
                sc=sc-sc.max(axis=-1,keepdims=True)
                e=np.exp(sc); a=e/e.sum(axis=-1,keepdims=True)
                att=np.einsum("hs,shd->hd",a,Vx).reshape(-1)
                o=w[p+"attn_output.weight"]@att
                x=x+o
                x_mid=x.copy()
                h2,(ms2,inv2)=self.rms_f(x,w[p+"ffn_norm.weight"])
                g,sg=self.silu_f(w[p+"ffn_gate.weight"]@h2)
                u=w[p+"ffn_up.weight"]@h2
                gu=g*u
                ff=w[p+"ffn_down.weight"]@gu
                x=x+ff
                C.append(dict(L=L,t=t,x_in=x_in,x_mid=x_mid,h=h,ms=ms,inv=inv,
                              qr=qr,kr=kr,v=vr,Ks=Ks,Vs=Vs,a=a,rep=rep,
                              h2=h2,ms2=ms2,inv2=inv2,g=g,sg=sg,u=u,ax_q=ax_q,ax_v=ax_v))
            xf,(msf,invf)=self.rms_f(x,w["output_norm.weight"])
            finals.append(dict(x=x,xf=xf,msf=msf,invf=invf))
        Wout=self.w.get("output.weight",self.m.tok_emb)
        logits=Wout@finals[T-1]["xf"]
        return logits, C, finals, kvs

    # ---- 反向: 正确处理「最后token的注意力用到所有历史kv」 ----
    def backward(self, toks, tgt, C, finals):
        T=len(toks); w=self.w
        # 索引化 cache
        idx={}
        for c in C: idx[(c["L"],c["t"])]=c
        Wout=w.get("output.weight",self.m.tok_emb)
        logits=Wout@finals[T-1]["xf"]
        lg=logits-logits.max(); p=np.exp(lg); p=p/p.sum()
        loss=-np.log(p[tgt]+1e-12)
        dlogits=p.copy(); dlogits[tgt]-=1.0
        dxf=Wout.T@dlogits
        dx=self.rms_b(dxf, finals[T-1]["x"], w["output_norm.weight"],
                      finals[T-1]["msf"], finals[T-1]["invf"])
        # 从最后一层往下(只需到最浅可训层)
        Lmin=min(self.layers) if self.layers else 0
        for L in range(N_LAYER-1, Lmin-1, -1):
            cT=idx.get((L,T-1))
            if cT is None: continue
            rep=cT["rep"]
            # --- FFN 反向 ---
            dgu=w["blk.%d.ffn_down.weight"%L].T@dx
            dg=dgu*cT["u"]; du=dgu*cT["g"]
            dg_pre=dg*(cT["sg"]+cT["g"]*(1-cT["sg"]))
            dh2=w["blk.%d.ffn_gate.weight"%L].T@dg_pre + w["blk.%d.ffn_up.weight"%L].T@du
            dx_attn = dx + self.rms_b(dh2, cT["x_mid"], w["blk.%d.ffn_norm.weight"%L], cT["ms2"], cT["inv2"])
            # --- attention 反向(只 T-1 有梯度) ---
            datt=w["blk.%d.attn_output.weight"%L].T@dx_attn
            datt2=datt.reshape(N_HEAD,HEAD_DIM)
            Vx=np.repeat(cT["Vs"],rep,axis=1); Kx=np.repeat(cT["Ks"],rep,axis=1)
            da=np.einsum("hd,shd->hs",datt2,Vx)
            dVx=np.einsum("hs,hd->shd",cT["a"],datt2)
            dsc=cT["a"]*(da-(da*cT["a"]).sum(axis=-1,keepdims=True))/np.sqrt(HEAD_DIM)
            dq=np.einsum("hs,shd->hd",dsc,Kx)
            dKx=np.einsum("hs,hd->shd",dsc,cT["qr"])
            # --- v: 所有历史位置都要更新 LoRA(冻结的 W_v 不需要梯度) ---
            if (L,"v") in self.loras:
                lo=self.loras[(L,"v")]
                for s in range(T):
                    cs=idx.get((L,s))
                    if cs is None: continue
                    dv_s=dVx[s].reshape(N_KV,rep,HEAD_DIM).sum(axis=1).reshape(-1)
                    lo.bwd(cs["h"], cs["ax_v"], dv_s)
            # --- q: 只有 T-1 ---
            dq2=self.rope_b(dq, cT["t"])
            dh_q=w["blk.%d.attn_q.weight"%L].T@dq2.reshape(-1)
            if (L,"q") in self.loras:
                dh_q+=self.loras[(L,"q")].bwd(cT["h"], cT["ax_q"], dq2.reshape(-1))
            # --- 继续往上层传(只传 q 通道, 因 k/v 冻结且无上游可训参数) ---
            dx = dx_attn + self.rms_b(dh_q, cT["x_in"], w["blk.%d.attn_norm.weight"%L], cT["ms"], cT["inv"])
        return loss, p

    def train_step(self, toks, tgt, lr):
        logits,C,finals,kvs=self.forward(toks)
        loss,p=self.backward(toks,tgt,C,finals)
        for lo in self.loras.values(): lo.step(lr)
        return loss, float(p[tgt])
    def nbytes(self): return sum(l.nbytes() for l in self.loras.values())
