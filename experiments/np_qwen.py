# -*- coding: utf-8 -*-
"""np_qwen.py — 纯 numpy 的 Qwen2 前向 + 手写反向(端侧自我训练底座)
   OpenBLAS 215 GFLOPS; 权重从 GGUF(Q4_K_M) dequant
"""
import numpy as np, time
from gguf import GGUFReader
from gguf.quants import dequantize

N_LAYER = 24
N_HEAD = 14
N_KV = 2
HEAD_DIM = 64
ROPE_THETA = 1000000.0
EPS = 1e-6

class Qwen2:
    def __init__(self, gguf_path, verbose=True):
        self.w = {}
        t0 = time.time()
        r = GGUFReader(gguf_path)
        for t in r.tensors:
            self.w[t.name] = dequantize(t.data, t.tensor_type).astype(np.float32)
        self.tok_emb = self.w["token_embd.weight"]
        self.out_norm = self.w["output_norm.weight"]
        self.out_w = self.w.get("output.weight", self.tok_emb)
        self.DIM = self.tok_emb.shape[1]
        self.VOCAB = self.tok_emb.shape[0]
        if verbose:
            print("加载 %d 张量 %.1fs 内存%.2fGB" % (len(self.w), time.time()-t0,
                  sum(v.nbytes for v in self.w.values())/2**30))
        half = HEAD_DIM//2
        self.inv_freq = 1.0/(ROPE_THETA ** (np.arange(0,half,dtype=np.float32)/half))

    # ---------- 基础算子 ----------
    @staticmethod
    def rms(x, w, eps=EPS):
        return (x/np.sqrt(np.mean(x*x)+eps))*w
    @staticmethod
    def silu(x):
        return x/(1.0+np.exp(-np.clip(x,-50,50)))
    def rope(self, x, pos):
        ang = pos*self.inv_freq
        c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
        x1=x[...,:HEAD_DIM//2]; x2=x[...,HEAD_DIM//2:]
        return np.concatenate([x1*c-x2*s, x2*c+x1*s], axis=-1)

    # ---------- 前向(带按层 KV cache) ----------
    def new_kv(self):
        return [{"k":[], "v":[]} for _ in range(N_LAYER)]

    def forward_one(self, tok, pos, kv=None, want_hidden=False):
        w=self.w
        if kv is None: kv=self.new_kv()
        x=self.tok_emb[tok].copy()
        for L in range(N_LAYER):
            p="blk.%d."%L
            h=self.rms(x, w[p+"attn_norm.weight"])
            q=w[p+"attn_q.weight"]@h; k=w[p+"attn_k.weight"]@h; v=w[p+"attn_v.weight"]@h
            for nm,arr in (("attn_q",q),("attn_k",k),("attn_v",v)):
                b=p+nm+".bias"
                if b in w: arr=arr+w[b]
                if nm=="attn_q": q=arr
                elif nm=="attn_k": k=arr
                else: v=arr
            q=self.rope(q.reshape(N_HEAD,HEAD_DIM), pos)
            k=self.rope(k.reshape(N_KV,HEAD_DIM), pos)
            v=v.reshape(N_KV,HEAD_DIM)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.stack(kv[L]["k"]); Vs=np.stack(kv[L]["v"])   # [seq,N_KV,HD]
            rep=N_HEAD//N_KV
            Kx=np.repeat(Ks,rep,axis=1); Vx=np.repeat(Vs,rep,axis=1)
            sc=np.einsum("hd,shd->hs",q,Kx)/np.sqrt(HEAD_DIM)
            sc=sc-sc.max(axis=-1,keepdims=True)
            e=np.exp(sc); a=e/e.sum(axis=-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vx).reshape(-1)
            x=x+(w[p+"attn_output.weight"]@att)
            h2=self.rms(x, w[p+"ffn_norm.weight"])
            g=self.silu(w[p+"ffn_gate.weight"]@h2)
            u=w[p+"ffn_up.weight"]@h2
            x=x+(w[p+"ffn_down.weight"]@(g*u))
        xf=self.rms(x, self.out_norm)
        logits=self.out_w@xf
        if want_hidden: return logits, kv, xf
        return logits, kv

    def gen(self, toks, max_new=24, temp=0.7, top_k=40, seed=0):
        rng=np.random.RandomState(seed); kv=None; logits=None
        t0=time.time()
        for pos,t in enumerate(toks):
            logits,kv=self.forward_one(t,pos,kv)
        pre=time.time()-t0
        out=[]
        for i in range(max_new):
            lg=logits/max(temp,1e-4)
            if top_k:
                idx=np.argpartition(-lg,top_k)[:top_k]
                m=np.full_like(lg,-1e30); m[idx]=lg[idx]; lg=m
            e=np.exp(lg-lg.max()); p=e/e.sum()
            nid=int(rng.choice(len(p),p=p))
            out.append(nid)
            logits,kv=self.forward_one(nid,len(toks)+i,kv)
        return out, {"prefill_s":pre, "prompt_len":len(toks)}
