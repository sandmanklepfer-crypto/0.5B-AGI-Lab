# -*- coding: utf-8 -*-
"""快速版: 只压 1 层(第12层), 看 KL 随 rank 变化"""
import numpy as np, time, warnings
warnings.filterwarnings("ignore")
import np_qwen
from np_tok import Tok
t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False); M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 就绪"%(time.time()-t0),flush=True)

Q="小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？"
ids=TK.encode("<|im_start|>user\n"+Q+"<|im_end|>\n<|im_start|>assistant\n")

def fwd(comp=None):
    w=M.w; kv=[{"k":[],"v":[]} for _ in range(24)]
    for pos,t in enumerate(ids):
        x=M.tok_emb[t].copy()
        for L in range(24):
            p="blk.%d."%L
            def W(n):
                if comp and (L,n) in comp:
                    U,S,Vt=comp[(L,n)]; return (U*S)@Vt
                return w[p+n]
            h=M.rms(x,w[p+"attn_norm.weight"])
            q=W("attn_q.weight")@h; k=W("attn_k.weight")@h; v=W("attn_v.weight")@h
            if p+"attn_q.bias" in w: q=q+w[p+"attn_q.bias"]
            if p+"attn_k.bias" in w: k=k+w[p+"attn_k.bias"]
            if p+"attn_v.bias" in w: v=v+w[p+"attn_v.bias"]
            q=M.rope(q.reshape(14,64),pos); k=M.rope(k.reshape(2,64),pos); v=v.reshape(2,64)
            kv[L]["k"].append(k); kv[L]["v"].append(v)
            Ks=np.repeat(np.stack(kv[L]["k"]),7,axis=1); Vs=np.repeat(np.stack(kv[L]["v"]),7,axis=1)
            sc=np.einsum("hd,shd->hs",q,Ks)/np.sqrt(64); sc=sc-sc.max(-1,keepdims=True)
            e=np.exp(sc); a=e/e.sum(-1,keepdims=True)
            att=np.einsum("hs,shd->hd",a,Vs).reshape(-1)
            x=x+(W("attn_output.weight")@att)
            h2=M.rms(x,w[p+"ffn_norm.weight"])
            x=x+(W("ffn_down.weight")@(M.silu(W("ffn_gate.weight")@h2)*W("ffn_up.weight")@h2))
    xf=M.rms(x,M.out_norm); return M.out_w@xf

def sm(lg,t=0.8):
    lg=lg.copy()/t; lg-=lg.max(); e=np.exp(lg); return e/e.sum()
def kl(p,q):
    p=np.clip(p,1e-12,None); q=np.clip(q,1e-12,None); return float(np.sum(p*np.log(p/q)))

t1=time.time(); base=fwd(); print("[%.0fs] 基线完成"%(time.time()-t0),flush=True)
print("基线首字:",TK.decode([int(np.argmax(base))]),flush=True)
print("\n第12层 ffn_down SVD压缩:",flush=True)
Wd=M.w["blk.12.ffn_down.weight"]      # (896, 4864)
print("  原始形状",Wd.shape,flush=True)
U,S,Vt=np.linalg.svd(Wd, full_matrices=False)
print("  奇异值top10:", " ".join("%.1f"%x for x in S[:10]),flush=True)
print("  秩大小:",len(S)," 最大/第100大=%.0f"%(S[0]/max(S[99],1e-9)),flush=True)
for R in [256,128,64,32,16,8,4]:
    comp={(12,"ffn_down.weight"):(U[:,:R].copy(),S[:R].copy(),Vt[:R,:].copy())}
    lg=fwd(comp); d=kl(sm(base),sm(lg))
    print("  rank=%3d (%.1f%%参数) KL=%.4f  首字=%r"%(R,100*R*(896+4864)/(896*4864),d,
        TK.decode([int(np.argmax(lg))])),flush=True)
print("\n总 %.0fs"%(time.time()-t0))
