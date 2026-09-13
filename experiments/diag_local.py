# -*- coding: utf-8 -*-
"""diag_local.py — 本地诊断: 为什么答不出黎曼几何/广义相对论
   模型: ERNIE-4.5-0.3B (229MB)
   对比: 简单题(会) vs 高数/黎曼/相对论(不会)
"""
import numpy as np, time, json, sys, math
from gguf import GGUFReader
from gguf.quants import dequantize

t0=time.time()
r=GGUFReader("/workspace/ernie03b.gguf")
meta={}
for k,v in r.fields.items():
    if k.endswith(".block_count"): meta["L"]=int(v.contents())
    if k.endswith(".embedding_length"): meta["D"]=int(v.contents())
    if k.endswith(".attention.head_count") and "kv" not in k: meta["H"]=int(v.contents())
    if k.endswith(".attention.head_count_kv"): meta["KV"]=int(v.contents())
    if k.endswith(".rope.freq_base"): meta["rope"]=float(v.contents())
    if k.endswith(".attention.key_length"): meta["HD"]=int(v.contents())
L=meta.get("L",18); D=meta.get("D",1024); H=meta.get("H",16); KV=meta.get("KV",2)
rope_base=meta.get("rope",10000.0)
HD=meta.get("HD",D//H)
QD=H*HD; KVD=KV*HD
print("模型: ERNIE-4.5-0.3B | 层%d 隐维%d heads %d/%d head_dim %d (Q=%d KV=%d) rope_base %.0f"%(
    L,D,H,KV,HD,QD,KVD,rope_base))

W={}
for t in r.tensors: W[t.name]=dequantize(t.data,t.tensor_type).astype(np.float32)
print("加载 %.0fs"%(time.time()-t0), flush=True)

# ---------- 分词 ----------
tk=[str(x) for x in r.fields["tokenizer.ggml.tokens"].contents()]
by_len={}
for i,s in enumerate(tk):
    if s: by_len.setdefault(len(s),{})[s]=i
lens=sorted(by_len.keys(), reverse=True)
BOS=1
def tokenize(text, mx=100):
    """SentencePiece 风: 前置 ▁ + BOS"""
    text = "▁" + text.replace(" ", "▁")
    ids=[BOS]; i=0; n=len(text)
    while i<n and len(ids)<mx:
        hit=None
        for Ln in lens:
            if Ln>n-i: continue
            s=text[i:i+Ln]
            if s in by_len[Ln]: hit=(by_len[Ln][s],Ln); break
        if hit: ids.append(hit[0]); i+=hit[1]
        else: i+=1
    return ids
def untok(i): return tk[i] if 0<=i<len(tk) else "?"

# ---------- 前向 ----------
def rms(x,w): return (x/np.sqrt(np.mean(x*x)+1e-6))*w
def silu(x): return x/(1+np.exp(-np.clip(x,-50,50)))
_INV=None
def get_inv():
    global _INV
    if _INV is None:
        half=HD//2
        _INV=1.0/(rope_base**(np.arange(0,half,dtype=np.float32)/half))
    return _INV
def rope(x,pos):
    half=HD//2; inv=get_inv()
    ang=pos*inv; c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
    x1=x[...,:half]; x2=x[...,half:]
    return np.concatenate([x1*c-x2*s, x2*c+x1*s],axis=-1)

def forward_trace(ids):
    kv={l:{"k":[],"v":[]} for l in range(L)}
    layer_stats=[]
    x=None
    for pos,idt in enumerate(ids):
        x=W["token_embd.weight"][idt].copy()
        for l in range(L):
            p="blk.%d."%l
            h=rms(x,W[p+"attn_norm.weight"])
            q=W[p+"attn_q.weight"]@h; k=W[p+"attn_k.weight"]@h; v=W[p+"attn_v.weight"]@h
            for nm,arr in (("q",q),("k",k),("v",v)):
                b=p+"attn_"+nm+".bias"
                if b in W:
                    if nm=="q": q=arr+W[b]
                    elif nm=="k": k=arr+W[b]
                    else: v=arr+W[b]
            q=rope(q.reshape(H,HD),pos); k=rope(k.reshape(KV,HD),pos); v=v.reshape(KV,HD)
            kv[l]["k"].append(k); kv[l]["v"].append(v)
            rep=H//KV
            Ks=np.repeat(np.stack(kv[l]["k"]),rep,axis=1)
            Vs=np.repeat(np.stack(kv[l]["v"]),rep,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(HD)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            ao=W[p+"attn_output.weight"]@att
            x=x+ao
            h2=rms(x,W[p+"ffn_norm.weight"])
            gp=W[p+"ffn_gate.weight"]@h2; up=W[p+"ffn_up.weight"]@h2
            ffn=silu(gp)*up
            x=x+(W[p+"ffn_down.weight"]@ffn)
            if pos==len(ids)-1:
                layer_stats.append({"l":l,"norm":float(np.linalg.norm(x)),
                    "std":float(np.std(x)),"ffn":float(np.linalg.norm(ffn)),
                    "attn_out":float(np.linalg.norm(ao)),
                    "attn_ent":float(-np.sum(a*np.log(a+1e-12)))})
    xf=rms(x,W["output_norm.weight"])
    Ow=W.get("output.weight", W["token_embd.weight"])
    logits=Ow@xf
    return logits, layer_stats

def ent(p): p=np.clip(p,1e-12,None); return float(-np.sum(p*np.log(p)))
def topk(lg,k=6):
    e=np.exp(lg-lg.max()); p=e/e.sum()
    idx=np.argsort(-lg)[:k]
    return [(untok(int(i)), float(p[i])) for i in idx], p

# ---------- 题目 ----------
CASES=[
 ("1 简单·算术",   "1+1=",                          "简单"),
 ("2 简单·常识",   "中国的首都是",                   "简单"),
 ("3 简单·语言",   "今天天气真",                     "简单"),
 ("4 中等·物理",   "苹果落地是因为",                 "中等"),
 ("5 微积分",      "x平方的导数是",                  "数学"),
 ("6 线性代数",    "矩阵的特征值是",                 "数学"),
 ("7 黎曼几何",    "黎曼度量张量的定义是",           "黎曼"),
 ("8 黎曼曲率",    "黎曼曲率张量描述了",             "黎曼"),
 ("9 协变导数",    "协变导数和偏导数的区别是",       "黎曼"),
 ("10 爱因斯坦",   "爱因斯坦场方程是",               "相对论"),
 ("11 测地线",     "测地线方程描述的是",             "相对论"),
 ("12 时空弯曲",   "质量如何弯曲时空",               "相对论"),
]

print("\n"+"="*80)
print("  诊断结果")
print("="*80)
rows=[]
for name,q,cat in CASES:
    ids=tokenize(q)
    lg,ls=forward_trace(ids)
    tops,p=topk(lg,6)
    unk=sum(1 for i in ids if i==0)
    mx=float(np.max(p)); E=ent(p)
    rows.append({"name":name,"cat":cat,"q":q,"unk":unk,"ntok":len(ids),
        "ent":E,"maxp":mx,"top1":tops[0][0],"top5":tops,
        "layers":[round(s["norm"],0) for s in ls[::3]],
        "attn_ent":round(float(np.mean([s["attn_ent"] for s in ls])),2),
        "ffn":round(float(np.mean([s["ffn"] for s in ls])),0)})
    print("\n%s  [%s]"%(name,cat))
    print("  输入: %s → %d tokens (未知字%d)"%(q,len(ids),unk))
    print("  Top5: %s"%(" | ".join("%s(%.2f)"%(a,b) for a,b in tops[:5])))
    print("  置信度 %.3f  熵 %.2f  注意力熵 %.2f"%(mx,E,rows[-1]["attn_ent"]))

print("\n"+"="*80)
print("  分类对比")
print("="*80)
print("\n%-10s %-8s %-10s %-10s %s"%("类别","题数","平均熵","平均置信","判定"))
print("-"*70)
for cat in ["简单","中等","数学","黎曼","相对论"]:
    g=[r for r in rows if r["cat"]==cat]
    if not g: continue
    e=np.mean([x["ent"] for x in g]); m=np.mean([x["maxp"] for x in g])
    v = "✅ 有把握" if m>0.35 else ("⚠️ 勉强" if m>0.15 else "❌ 完全没把握")
    print("%-10s %-8d %-10.2f %-10.3f %s"%(cat,len(g),e,m,v))

print("\n【结论】")
for cat in ["简单","数学","黎曼","相对论"]:
    g=[r for r in rows if r["cat"]==cat]
    if not g: continue
    print("  %-8s 置信度 %.3f  最大值%.3f  首token: %s"%(
        cat, np.mean([x["maxp"] for x in g]), max(x["maxp"] for x in g), g[0]["top1"]))
json.dump(rows, open("/workspace/math_diag.json","w"), ensure_ascii=False, indent=1)
print("\n耗时 %.0fs"% (time.time()-t0))
