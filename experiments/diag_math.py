# -*- coding: utf-8 -*-
"""diag_math.py — 诊断"为什么答不出黎曼几何/广义相对论"
   方法: 同一模型, 对比
     ① 简单题(会做)           ← 对照组
     ② 黎曼几何题(不会)        ← 实验组
     ③ 广义相对论题(不会)
   看什么(可解释性指标):
     A. 隐状态范数/熵          → 是"没反应过来"还是"反应过度"
     B. 逐层激活漂移           → 在哪一层开始崩
     C. logits 分布            → 是"不知道"还是"知道但选错"
     D. 首token 熵             → 置信度
     E. 词表命中率             → 是"词不认识"还是"关系不懂"
"""
import numpy as np, time, math, json
from gguf import GGUFReader
from gguf.quants import dequantize

t0=time.time()
# 用 0.5B (小, 快, 便于分析; 问题在更大模型上同样存在)
r=GGUFReader("/root/autodl-tmp/qwen05b_q4km.gguf")
W={}
for t in r.tensors:
    W[t.name]=dequantize(t.data,t.tensor_type).astype(np.float32)
print("模型加载 %.0fs"% (time.time()-t0), flush=True)
D=896; L=24; V=151936

# ---------- 分词 ----------
tk=r.fields["tokenizer.ggml.tokens"].contents()
by_len={}
for i,s in enumerate(tk):
    s=str(s)
    if s: by_len.setdefault(len(s),{})[s]=i
lens=sorted(by_len.keys(), reverse=True)
def tokenize(text, maxlen=120):
    ids=[]; i=0; n=len(text)
    while i<n and len(ids)<maxlen:
        hit=None
        for Ln in lens:
            if Ln>n-i: continue
            s=text[i:i+Ln]
            if s in by_len[Ln]: hit=(by_len[Ln][s], Ln); break
        if hit: ids.append(hit[0]); i+=hit[1]
        else: ids.append(0); i+=1     # <unk>
    return ids
def untok(i): return str(tk[i]) if 0<=i<len(tk) else "?"

# ---------- 前向(记录每层) ----------
def rms(x,w): return (x/np.sqrt(np.mean(x*x)+1e-6))*w
def silu(x): return x/(1+np.exp(-np.clip(x,-50,50)))
def rope(x,pos,theta=1000000.0,dim=64):
    half=dim//2
    inv=1.0/(theta**(np.arange(0,half,dtype=np.float32)/half))
    ang=pos*inv; c=np.cos(ang).astype(np.float32); s=np.sin(ang).astype(np.float32)
    x1=x[...,:half]; x2=x[...,half:]
    return np.concatenate([x1*c-x2*s, x2*c+x1*s],axis=-1)

def forward_trace(ids):
    """返回: 每层隐状态记录 + 最终 logits"""
    kv={l:{"k":[],"v":[]} for l in range(L)}
    layer_stats=[]; hiddens=[]
    x=None
    for pos,tk_ in enumerate(ids):
        x=W["token_embd.weight"][tk_].copy()
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
            q=rope(q.reshape(14,64),pos); k=rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[l]["k"].append(k); kv[l]["v"].append(v)
            Ks=np.repeat(np.stack(kv[l]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[l]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(W[p+"attn_output.weight"]@att)
            h2=rms(x,W[p+"ffn_norm.weight"])
            gp=W[p+"ffn_gate.weight"]@h2; up=W[p+"ffn_up.weight"]@h2
            ffn=silu(gp)*up
            x=x+(W[p+"ffn_down.weight"]@ffn)
            if pos==len(ids)-1:
                layer_stats.append({"l":l,"norm":float(np.linalg.norm(x)),
                    "std":float(np.std(x)),"ffn_norm":float(np.linalg.norm(ffn)),
                    "attn_norm":float(np.linalg.norm(W[p+"attn_output.weight"]@att))})
        hiddens.append(x)
    xf=rms(x,W["output_norm.weight"])
    logits=W["output.weight"]@xf
    return logits, layer_stats, np.array(hiddens)

def entropy(p):
    p=np.clip(p,1e-12,None); return float(-np.sum(p*np.log(p)))
def topk(logits,k=8):
    e=np.exp(logits-logits.max()); p=e/e.sum()
    idx=np.argsort(-logits)[:k]
    return [(int(i), untok(i), float(p[i])) for i in idx], p

# ==================== 测试题 ====================
CASES = [
 ("【1】简单·算术",       "1+1等于几？答："),
 ("【2】简单·常识",       "中国的首都是哪里？答："),
 ("【3】中等·物理",       "苹果为什么会落地？答："),
 ("【4】难·微积分",       "求函数f(x)=x^3的导数，答："),
 ("【5】难·黎曼几何",     "黎曼度量张量的定义是什么？答："),
 ("【6】难·黎曼曲率",     "黎曼曲率张量如何表示空间弯曲？答："),
 ("【7】难·广义相对论",   "爱因斯坦场方程的意义是什么？答："),
 ("【8】难·张量分析",     "协变导数与普通偏导数有何区别？答："),
 ("【9】难·测地线",       "测地线方程如何描述自由落体？答："),
]

print("\n"+"="*78)
print("  诊断: 为什么答不出黎曼几何/广义相对论")
print("="*78)
rows=[]
for name, q in CASES:
    ids=tokenize(q)
    lg, ls, hiddens = forward_trace(ids)
    tops, p = topk(lg, 8)
    ent=entropy(p)
    mx=float(np.max(p))
    # 关键指标
    unk = sum(1 for i in ids if i==0)
    r = {"name":name, "q":q, "tokens":len(ids), "unk":unk,
         "entropy":ent, "maxp":mx,
         "top1":tops[0][1], "top1p":tops[0][2],
         "top5":[(t[1],round(t[2],3)) for t in tops[:5]],
         "final_norm":float(np.linalg.norm(hiddens[-1])),
         "mid_norm":float(np.linalg.norm(hiddens[len(hiddens)//2])),
         "layer_norms":[round(s["norm"],1) for s in ls[::4]],
         "ffn_act":round(float(np.mean([s["ffn_norm"] for s in ls])),1)}
    rows.append(r)
    print("\n%s"%name)
    print("  问题: %s" % q)
    print("  分词: %d个 (未知字 %d个)" % (len(ids), unk))
    print("  首token: %r(p=%.3f)  熵=%.2f  最高概率=%.3f" % (r["top1"], r["top1p"], ent, mx))
    print("  Top5: %s" % " | ".join("%s(%.2f)"%(t[1],t[2]) for t in tops[:5]))
    print("  隐状态范数: 中段%.0f → 末段%.0f   FFN激活均值%.0f" % (r["mid_norm"], r["final_norm"], r["ffn_act"]))

# ---------- 对比分析 ----------
print("\n"+"="*78)
print("  对比分析")
print("="*78)
easy=[r for r in rows if "简单" in r["name"] or "中等" in r["name"]]
hard=[r for r in rows if "难" in r["name"]]
print("\n%-16s %-8s %-10s %-10s %s"%("类别","熵","最高概率","隐范数","说明"))
print("-"*78)
for grp,gname in ((easy,"简单/中等"),(hard,"难题(黎曼/相对论)")):
    if not grp: continue
    e=np.mean([r["entropy"] for r in grp]); m=np.mean([r["maxp"] for r in grp])
    n=np.mean([r["final_norm"] for r in grp])
    print("%-16s %-8.2f %-10.3f %-10.0f %s"%(gname,e,m,n,
        "模型" + ("知道自己在说什么" if m>0.3 else "完全没把握")))

print("\n【逐题诊断】")
print("%-18s %-8s %-8s %s"%("题","熵","最高p","判定"))
print("-"*60)
for r in rows:
    if r["maxp"]>0.5: v="✅ 很有把握"
    elif r["maxp"]>0.2: v="⚠️ 有点方向"
    elif r["maxp"]>0.08: v="🔸 瞎猜范围内"
    else:       v="❌ 完全不知道"
    print("%-18s %-8.2f %-8.3f %s"%(r["name"],r["entropy"],r["maxp"],v))

print("\n【关键指标: 词表命中】")
for r in rows:
    print("  %-18s 未知字 %d/%d"%(r["name"],r["unk"],r["tokens"]))

json.dump(rows, open("/root/autodl-tmp/math_diag.json","w"), ensure_ascii=False, indent=1)
print("\n数据 → /root/autodl-tmp/math_diag.json")
print("总耗时 %.0fs"%(time.time()-t0))
