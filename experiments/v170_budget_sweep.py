# -*- coding: utf-8 -*-
"""桥流强度扫描: 找"语义不崩"的最大强度"""
import numpy as np
for _n,_t in [('long',np.int64),('ulong',np.uint64),('uintc',np.uint32),
              ('longlong',np.int64),('ulonglong',np.uint64),('int',int),
              ('float',float),('bool',bool),('object',object),('str',str)]:
    if not hasattr(np,_n):
        try: setattr(np,_n,_t)
        except Exception: pass
import torch, math, copy, json
torch.set_num_threads(8)
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
from transformers.models.qwen2.tokenization_qwen2_fast import Qwen2TokenizerFast
SRC='/root/autodl-tmp/life1/antiheb_05b'
tok=Qwen2TokenizerFast.from_pretrained(SRC)
TXT=["人工智能正在改变世界，它可以帮助人们处理很多复杂的问题。",
     "春天来了，树木开始发芽，小鸟在枝头歌唱。",
     "数学是研究数量关系和空间形式的科学。",
     "深度学习模型通过反向传播算法不断调整参数，从而逐渐逼近目标函数。",
     "长江是中国最长的河流，它从青藏高原流向东海，全长六千多公里。"]
def collect(m):
    out=[]
    for n,mod in m.named_modules():
        if hasattr(mod,'weight') and mod.weight is not None and mod.weight.dim()==2 \
           and any(p in n for p in ('q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')):
            out.append((n,mod))
    return out
def ppl(m):
    tl,tn=0.0,0
    for t in TXT:
        ids=tok(t,return_tensors='pt').input_ids
        with torch.no_grad(): o=m(ids,labels=ids)
        tl+=float(o.loss)*(ids.shape[1]-1); tn+=ids.shape[1]-1
    return math.exp(tl/tn)
def gen(m,q,n=20):
    ids=tok(q,return_tensors='pt').input_ids
    with torch.no_grad(): o=m.generate(ids,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True)
print('加载原始模型...',flush=True)
m=Qwen2ForCausalLM.from_pretrained(SRC,dtype=torch.float32); m.eval()
mods=collect(m)
ORIG={n:mod.weight.data.clone() for n,mod in mods}
print(f'可改权重 {len(mods)} 个',flush=True)
base=ppl(m); print(f'原始困惑度 = {base:.4f}',flush=True)
res={'base':base,'sweep':[]}
R_RATIO=0.28
for ALPHA in [0.35,0.10,0.03,0.01,0.003]:
    for n,mod in mods: mod.weight.data.copy_(ORIG[n])
    rels=[]
    for n,mod in mods:
        W=mod.weight.data.float()
        U,S,Vh=torch.linalg.svd(W,full_matrices=False)
        k=S.numel(); R=max(4,int(k*R_RATIO))
        if R>=k: continue
        head=S[:R].sum(); tail=S[R:].sum()
        S2=S.clone(); S2[:R]=S2[:R]*(1.0+ALPHA*tail/(head+1e-8))
        S2=S2*(S.norm()/(S2.norm()+1e-8))
        W2=(U*S2)@Vh
        rels.append(float((W2-W).norm()/(W.norm()+1e-8)))
        mod.weight.data.copy_(W2.to(mod.weight.dtype))
    p=ppl(m); rmax=max(rels)
    ok = p/base < 1.25
    print(f'ALPHA={ALPHA:<6} 单矩阵最大偏离={rmax:.4f}  困惑度={p:9.4f} ({p/base:6.2f}x)  {"✅语义保" if ok else "❌崩"}',flush=True)
    if ok: print(f'    样例: {gen(m,"你好，请介绍一下你自己。")[:70]}',flush=True)
    res['sweep'].append({'alpha':ALPHA,'rel':rmax,'ppl':p,'ratio':p/base})
json.dump(res,open('/root/autodl-tmp/life1/sweep.json','w'),ensure_ascii=False,indent=1)
print('DONE',flush=True)
