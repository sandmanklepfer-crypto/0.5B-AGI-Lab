# -*- coding: utf-8 -*-
"""steer_test.py — 控制核增强实验：强化"控制核"能否提升输出?
   对比: 正常生成 vs 控制核激活放大K倍
   问题: 用推理题, 看答案质量是否变化
"""
import numpy as np, time, warnings
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪"%(time.time()-t0),flush=True)

# 找控制核(用几个不同任务)
CALIB=['中国的首都是哪里？','1+1等于几？','鲸鱼属于什么动物？','请写一段关于秋天的文字']
def gate_sig(ids, layers=(12,)):
    w=M.w; got={L:None for L in layers}
    kv=[{"k":[],"v":[]} for _ in range(24)]
    for pos,t in enumerate(ids):
        x=M.tok_emb[t].copy()
        for L in range(24):
            p="blk.%d."%L
            h=M.rms(x,w[p+"attn_norm.weight"])
            q=w[p+"attn_q.weight"]@h; k=w[p+"attn_k.weight"]@h; v=w[p+"attn_v.weight"]@h
            for nm,arr in (("q",q),("k",k),("v",v)):
                b=p+"attn_"+nm+".bias"
                if b in w:
                    if nm=="q": q=arr+w[b]
                    elif nm=="k": k=arr+w[b]
                    else: v=arr+w[b]
            q=M.rope(q.reshape(14,64),pos); k=M.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(w[p+"attn_output.weight"]@att)
            h2=M.rms(x,w[p+"ffn_norm.weight"])
            gp=w[p+"ffn_gate.weight"]@h2
            if L in layers: got[L]=gp.copy()
            u=w[p+"ffn_up.weight"]@h2
            x=x+(w[p+"ffn_down.weight"]@(M.silu(gp)*u))
    return got

sigs={L:[] for L in (12,)}
for q in CALIB:
    g=gate_sig(TK.encode(q)); sigs[12].append(g[12])
A=np.stack(sigs[12]); mean=A.mean(0); std=A.std(0)
CTRL = (np.abs(mean)>np.percentile(np.abs(mean),90)) & (std<np.percentile(std,50))
print("控制核: %d 个 (第12层)"%CTRL.sum(),flush=True)

# ---- 带增强的生成 ----
def gen_steer(ids, boost=1.0, maxn=45, temp=0.7, seed=7, layer=12):
    """boost: 控制核激活放大倍数"""
    w=M.w; rng=np.random.RandomState(seed)
    kv=[{"k":[],"v":[]} for _ in range(24)]
    logits=None
    def step(tk,pos):
        nonlocal logits
        x=M.tok_emb[tk].copy()
        for L in range(24):
            p="blk.%d."%L
            h=M.rms(x,w[p+"attn_norm.weight"])
            q=w[p+"attn_q.weight"]@h; k=w[p+"attn_k.weight"]@h; v=w[p+"attn_v.weight"]@h
            if p+"attn_q.bias" in w: q=q+w[p+"attn_q.bias"]
            if p+"attn_k.bias" in w: k=k+w[p+"attn_k.bias"]
            if p+"attn_v.bias" in w: v=v+w[p+"attn_v.bias"]
            q=M.rope(q.reshape(14,64),pos); k=M.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(w[p+"attn_output.weight"]@att)
            h2=M.rms(x,w[p+"ffn_norm.weight"])
            gp=w[p+"ffn_gate.weight"]@h2
            if L==layer and boost!=1.0:
                gp=gp.copy(); gp[CTRL]*=boost          # ← 增强控制核
            u=w[p+"ffn_up.weight"]@h2
            x=x+(w[p+"ffn_down.weight"]@(M.silu(gp)*u))
        xf=M.rms(x,M.out_norm); logits=w["output.weight"]@xf
    for pos,t in enumerate(ids): step(t,pos)
    out=[]
    for i in range(maxn):
        lg=logits/max(temp,1e-4)
        idx=np.argpartition(-lg,40)[:40]; m=np.full_like(lg,-1e30); m[idx]=lg[idx]; lg=m
        e=np.exp(lg-lg.max()); p=e/e.sum()
        nid=int(rng.choice(len(p),p=p)); out.append(nid)
        step(nid,len(ids)+i)
    return out

QS=['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
    '一只蜗牛白天爬3米晚上滑下2米，井深10米几天爬出？']

for q in QS:
    prompt="<|im_start|>user\n"+q+"<|im_end|>\n<|im_start|>assistant\n"
    ids=TK.encode(prompt)
    print("\n"+"="*66)
    print("【问】%s"%q)
    print("="*66)
    for boost,label in [(1.0,"基线    "),(1.5,"控制核×1.5"),(2.5,"控制核×2.5")]:
        t1=time.time()
        out=gen_steer(ids,boost=boost,maxn=45)
        txt=TK.decode(out).replace("\n"," ")
        print("  [%s] %.0fs  %s"%(label,time.time()-t1,txt[:150]))
print("\n总耗时 %.0fs"%(time.time()-t0))
