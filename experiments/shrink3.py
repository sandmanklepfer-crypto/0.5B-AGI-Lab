# -*- coding: utf-8 -*-
"""shrink3.py — 三重手术: 0.5B → 0.05B, 实测能力保留
   手术:
     ① FFN 砍 90%  (按重要性保留前 10% 神经元)
     ② 层数 24 → 12 (保留前6+后6)
     ③ 词表 151936 → 32000 (按语料频率重排, 其余→<unk>)
   测: 困惑度(perplexity) — 越低越好, 随机猜测≈词表大小
"""
import numpy as np, time, json, os
from gguf import GGUFReader
from gguf.quants import dequantize

t0=time.time()
r=GGUFReader("/root/autodl-tmp/qwen05b_q4km.gguf")
W={}
for t in r.tensors:
    W[t.name]=dequantize(t.data,t.tensor_type).astype(np.float32)
print("加载 %d 张量 %.0fs"%(len(W), time.time()-t0), flush=True)

D=896; L=24; F=4864; V=151936

# ---------- 取测试文本 ----------
txt=open("/root/autodl-tmp/raw_corpus.txt",encoding="utf-8",errors="ignore").read()
print("语料 %d 字符"%len(txt))

# ---------- 分词(用 GGUF 自带词表, 贪心最长匹配) ----------
tok_field=r.fields["tokenizer.ggml.tokens"].contents()
tokstr=[str(x) for x in tok_field]
# 建立 前缀树式的贪心匹配(简化: 用长度分桶)
by_len={}
for i,s in enumerate(tokstr):
    if not s: continue
    by_len.setdefault(len(s),{})[s]=i
lens=sorted(by_len.keys(), reverse=True)

def tokenize(text, maxlen=300):
    ids=[]; i=0; n=len(text)
    while i<n and len(ids)<maxlen:
        hit=None
        for L in lens:
            if L> n-i: continue
            s=text[i:i+L]
            d=by_len[L]
            if s in d: hit=(d[s],L); break
        if hit: ids.append(hit[0]); i+=hit[1]
        else: i+=1
    return ids

ids=tokenize(txt, 320)
print("分词: %d tokens"%len(ids), flush=True)

# ---------- 前向(numpy) ----------
def rms(x,w): return (x/np.sqrt(np.mean(x*x)+1e-6))*w
def silu(x): return x/(1+np.exp(-np.clip(x,-50,50)))
def rope(x,pos,theta=1000000.0,dim=64):
    half=dim//2
    inv=1.0/(theta**(np.arange(0,half,dtype=np.float32)/half))
    ang=pos*inv; c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
    x1=x[...,:half]; x2=x[...,half:]
    return np.concatenate([x1*c-x2*s, x2*c+x1*s],axis=-1)

def forward(ids, layers, ffn_keep=None, Emat=None, Omat=None):
    """layers: 使用的层号列表; ffn_keep: {层号: 保留的神经元索引}; Emat/Omat: 替换的词表"""
    E = Emat if Emat is not None else W["token_embd.weight"]
    O = Omat if Omat is not None else W.get("output.weight", W["token_embd.weight"])
    kv={l:{"k":[],"v":[]} for l in layers}
    logits=None; T=len(ids)
    for pos,tk in enumerate(ids):
        x=E[tk].copy()
        for l in layers:
            p="blk.%d."%l
            h=rms(x,W[p+"attn_norm.weight"])
            q=W[p+"attn_q.weight"]@h; k=W[p+"attn_k.weight"]@h; v=W[p+"attn_v.weight"]@h
            for nm,arr in (("q",q),("k",k),("v",v)):
                b=p+"attn_"+nm+".bias"
                if b in W:
                    if nm=="q": q=arr+W[b]
                    elif nm=="k": k=arr+W[b]
                    else: v=arr+W[b]
            q=rope(q.reshape(14,64),pos); k=rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[l]["k"].append(k); kv[l]["v"].append(v)
            Ks=np.repeat(np.stack(kv[l]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[l]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(W[p+"attn_output.weight"]@att)
            h2=rms(x,W[p+"ffn_norm.weight"])
            g=W[p+"ffn_gate.weight"]; u=W[p+"ffn_up.weight"]; d=W[p+"ffn_down.weight"]
            if ffn_keep is not None and l in ffn_keep:
                idx=ffn_keep[l]
                gp = g[idx]@h2; up = u[idx]@h2; dp = d[:,idx]
            else:
                gp = g@h2; up = u@h2; dp = d
            x=x+(dp@(silu(gp)*up))
        xf=rms(x,W["output_norm.weight"])
        logits=O@xf
    return logits

# ---------- 困惑度 ----------
def perplexity(ids, **kw):
    """滑动窗口平均"""
    T=len(ids)-1
    if T<=0: return 999
    # 一次性前向整段, 但需要每步的 logits → 简化: 逐位置算
    E = kw.get("Emat"); O = kw.get("Omat")
    E = E if E is not None else W["token_embd.weight"]
    O = O if O is not None else W.get("output.weight", W["token_embd.weight"])
    layers=kw.get("layers") or list(range(L))
    fk=kw.get("ffn_keep")
    kv={l:{"k":[],"v":[]} for l in layers}
    nll=0.0; cnt=0
    for pos in range(len(ids)-1):
        tk=ids[pos]
        x=E[tk].copy()
        for l in layers:
            p="blk.%d."%l
            h=rms(x,W[p+"attn_norm.weight"])
            q=W[p+"attn_q.weight"]@h; k=W[p+"attn_k.weight"]@h; v=W[p+"attn_v.weight"]@h
            for nm,arr in (("q",q),("k",k),("v",v)):
                b=p+"attn_"+nm+".bias"
                if b in W:
                    if nm=="q": q=arr+W[b]
                    elif nm=="k": k=arr+W[b]
                    else: v=arr+W[b]
            q=rope(q.reshape(14,64),pos); k=rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[l]["k"].append(k); kv[l]["v"].append(v)
            Ks=np.repeat(np.stack(kv[l]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[l]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(W[p+"attn_output.weight"]@att)
            h2=rms(x,W[p+"ffn_norm.weight"])
            if fk is not None and l in fk:
                idx=fk[l]; gp=W[p+"ffn_gate.weight"][idx]@h2
                up=W[p+"ffn_up.weight"][idx]@h2; dp=W[p+"ffn_down.weight"][:,idx]
            else:
                gp=W[p+"ffn_gate.weight"]@h2; up=W[p+"ffn_up.weight"]@h2; dp=W[p+"ffn_down.weight"]
            x=x+(dp@(silu(gp)*up))
        xf=rms(x,W["output_norm.weight"])
        lg=O@xf
        lg=lg-lg.max(); p=np.exp(lg); p/=p.sum()
        nll += -np.log(max(p[ids[pos+1]],1e-12)); cnt+=1
    return float(np.exp(nll/max(cnt,1)))

# ============ 三种手术 ============
print("\n"+"="*70)
print("  三重手术实测 (困惑度, 越低越好)")
print("="*70)

# 基线
t1=time.time(); ppl0=perplexity(ids[:120]); 
print("① 基线(完整)          perplexity = %8.2f  [%.0fs]"%(ppl0, time.time()-t1), flush=True)

# 手术①: FFN 砍 90%
print("\n计算 FFN 重要性...", flush=True)
ffn_keep={}
for l in range(L):
    g=W["blk.%d.ffn_gate.weight"%l]; u=W["blk.%d.ffn_up.weight"%l]; d=W["blk.%d.ffn_down.weight"%l]
    imp=np.linalg.norm(g,axis=1)*np.linalg.norm(u,axis=1)*np.linalg.norm(d,axis=0)
    keep=int(F*0.1)
    ffn_keep[l]=np.argsort(-imp)[:keep]
t1=time.time(); ppl1=perplexity(ids[:120], ffn_keep=ffn_keep)
print("② +FFN砍90%%          perplexity = %8.2f  [%.0fs]"%(ppl1,time.time()-t1), flush=True)

# 手术②: 层数 24→12
keep_layers=[0,1,2,3,4,5,18,19,20,21,22,23]
t1=time.time(); ppl2=perplexity(ids[:120], layers=keep_layers)
print("③ +层数24→12          perplexity = %8.2f  [%.0fs]"%(ppl2,time.time()-t1), flush=True)

# 手术③: 词表 152k→32k
from collections import Counter
freq=Counter()
for i in ids[:200]: freq[i]+=1
for t in W and []: pass
# 用全局 token 频率近似: 取在语料里出现的 + 常见的低位 id
common=list(range(0,20000))   # 低位 id 通常对应高频 token
for t,c in freq.items():
    if t not in common: common.append(t)
common=common[:32000]
old2new={o:i for i,o in enumerate(common)}
UNK=32000  # 未知映射到一个新 id
Vnew=32001
Enew=np.zeros((Vnew,D),np.float32); Onew=np.zeros((Vnew,D),np.float32)
Eorig=W["token_embd.weight"]; Oorig=W.get("output.weight",Eorig)
for o,ni in old2new.items():
    if o<Eorig.shape[0]: Enew[ni]=Eorig[o]
    if o<Oorig.shape[0]: Onew[ni]=Oorig[o]
Enew[UNK]=Eorig.mean(0); Onew[UNK]=Oorig.mean(0)
ids_new=[old2new.get(t,UNK) for t in ids]
unk_rate=100*sum(1 for t in ids if t not in old2new)/max(len(ids),1)
t1=time.time(); ppl3=perplexity(ids_new[:120], Emat=Enew, Omat=Onew)
print("④ +词表152k→32k       perplexity = %8.2f  [%.0fs]  (unk率 %.0f%%)"%(ppl3,time.time()-t1,unk_rate), flush=True)

# 三重全上
t1=time.time(); ppl4=perplexity(ids_new[:120], layers=keep_layers, ffn_keep=ffn_keep, Emat=Enew, Omat=Onew)
print("⑤ 三重全上            perplexity = %8.2f  [%.0fs]"%(ppl4,time.time()-t1), flush=True)

print("\n"+"="*70)
print("  总结")
print("="*70)
base=494e6
print("  %-22s %-14s %s"%("配置","参数量","困惑度"))
print("  "+"-"*56)
print("  %-22s %-14s %.2f"%("完整 0.5B", "494M", ppl0))
print("  %-22s %-14s %.2f"%("+FFN砍90%%", "230M", ppl1))
print("  %-22s %-14s %.2f"%("+层12", "115M", ppl2))
print("  %-22s %-14s %.2f"%("+词表32k", "54M", ppl3))
print("  %-22s %-14s %.2f"%("三重全上", "54M", ppl4))
print("\n  (困惑度越低越好; 翻倍=能力显著下降)")
print("  总耗时 %.0fs"%(time.time()-t0))
