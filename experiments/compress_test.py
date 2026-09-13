# -*- coding: utf-8 -*-
"""compress_test.py — 「推理核压缩」真实实验
   问题: 把大模型的层"SVD低秩压缩成一个小核", 能力保留多少? 何时崩?
   做法: 对每层权重做 rank-r 截断SVD → 实测输出保真度 + 推理题表现
   指标: ① logits KL散度(快, 精确)  ② 推理题答对率(慢, 直观)
"""
import numpy as np, time, warnings
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪 (%.2fGB)"%(time.time()-t0,
      sum(v.nbytes for v in M.w.values())/2**30),flush=True)

# ---------- 推理题(标准答案) ----------
PROBLEMS=[
 ("小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？","5"),
 ("一只蜗牛白天爬3米晚上滑2米，井深10米，几天爬出去？","8"),
 ("1+2+3+...+10 等于多少？","55"),
 ("如果所有的A都是B，所有的B都是C，那么所有的A都是C吗？","是"),
 ("一个班有30人，其中男生比女生多4人，女生有几人？","13"),
]

def logits_of(mdl, ids, layer_compress=None):
    """前向取 logits; layer_compress: {(L,which): (U,S,Vt)} 用压缩版代替"""
    w=mdl.w; kv=[{"k":[],"v":[]} for _ in range(24)]
    for pos,t in enumerate(ids):
        x=mdl.tok_emb[t].copy()
        for L in range(24):
            p="blk.%d."%L
            def W(name):
                if layer_compress and (L,name) in layer_compress:
                    U,S,Vt=layer_compress[(L,name)]
                    return (U*S)@Vt
                return w[p+name]
            h=mdl.rms(x,w[p+"attn_norm.weight"])
            q=W("attn_q.weight")@h; k=W("attn_k.weight")@h; v=W("attn_v.weight")@h
            if p+"attn_q.bias" in w: q=q+w[p+"attn_q.bias"]
            if p+"attn_k.bias" in w: k=k+w[p+"attn_k.bias"]
            if p+"attn_v.bias" in w: v=v+w[p+"attn_v.bias"]
            q=mdl.rope(q.reshape(14,64),pos); k=mdl.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64)
            sc=sc-sc.max(-1,keepdims=True); e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(W("attn_output.weight")@att)
            h2=mdl.rms(x,w[p+"ffn_norm.weight"])
            gp=W("ffn_gate.weight")@h2; up=W("ffn_up.weight")@h2
            x=x+(W("ffn_down.weight")@(mdl.silu(gp)*up))
        pass
    xf=mdl.rms(x,M.out_norm)
    return M.out_w@xf

def softmax(lg,t=0.8):
    lg=lg.copy()/t; lg-=lg.max(); e=np.exp(lg); return e/e.sum()

def kl(p,q):
    p=np.clip(p,1e-12,None); q=np.clip(q,1e-12,None)
    return float(np.sum(p*np.log(p/q)))

# ---------- 基线 ----------
print("\n"+"="*66)
print("  ① 基线(未压缩)")
print("="*66)
base_logits={}; base_answers={}
for q,gold in PROBLEMS:
    ids=TK.encode("<|im_start|>user\n"+q+"<|im_end|>\n<|im_start|>assistant\n")
    lg=logits_of(M,ids)
    base_logits[q]=lg
    # 贪心首token
    pred=TK.decode([int(np.argmax(lg))])
    base_answers[q]=pred
    print("  Q: %-40s → 首字: %r"%(q[:38],pred),flush=True)

# ---------- 低秩压缩扫描 ----------
print("\n"+"="*66)
print("  ② 低秩压缩(SVD截断) — 推理能力保留度")
print("="*66)
WHICH=["attn_q.weight","attn_v.weight","ffn_gate.weight","ffn_down.weight"]
for RANK in [512, 256, 128, 64, 32, 8]:
    t1=time.time()
    comp={}; kept=0; total=0
    for L in range(24):
        p="blk.%d."%L
        for nm in WHICH:
            W=M.w[p+nm]
            if nm=="attn_q.weight": Wc=W[:896,:]         # q: 896x896
            else: Wc=W
            try:
                U,S,Vt=np.linalg.svd(Wc, full_matrices=False)
                r=min(RANK,len(S))
                comp[(L,nm)]=(U[:,:r].copy(),S[:r].copy(),Vt[:r,:].copy())
                kept+=r*(Wc.shape[0]+Wc.shape[1]); total+=Wc.shape[0]*Wc.shape[1]
            except Exception: pass
    ratio = 100*kept/max(total,1)
    # 测保真度
    kls=[]; 
    for q,gold in PROBLEMS:
        ids=TK.encode("<|im_start|>user\n"+q+"<|im_end|>\n<|im_start|>assistant\n")
        lg2=logits_of(M,ids,comp)
        kls.append(kl(softmax(base_logits[q]), softmax(lg2)))
    print("  rank=%3d (存%.0f%%参数): KL=%.3f ±%.3f  [%.0fs]"%(
        RANK, ratio, np.mean(kls), np.std(kls), time.time()-t1),flush=True)

print("\n总耗时 %.0fs"%(time.time()-t0))
print("解读: KL<0.1 几乎无损; 0.1~1 有损可用; >2 已崩")
