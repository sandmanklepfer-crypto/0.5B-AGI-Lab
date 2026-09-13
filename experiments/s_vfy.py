# -*- coding: utf-8 -*-
"""验证: 加 output.bias 后, 拒绝行为是否消失"""
import sys
sys.path.insert(0,"/root/venv_lfm2/lib/python3.12/site-packages")
import numpy as np, torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer, LogitsProcessor
t0=time.time()
print("加载 calc_v1...", flush=True)
tok=AutoTokenizer.from_pretrained("/root/distill_calc_v1")
md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1", dtype=torch.float32)
md.eval()
print(f"  {time.time()-t0:.0f}s", flush=True)
W=md.lm_head.weight.data.float()          # (vocab, 896)
name2id=tok.get_vocab()
def ids_of(s):
    r=[]
    for ch in s:
        r+=tok.encode(ch, add_special_tokens=False)
    return r
REJ_TOK=set(ids_of("对不起无法不能抱歉学会"))
print(f"  拒绝token候选 {len(REJ_TOK)} 个", flush=True)

d=np.fromfile('/root/autodl-tmp/l23/d_refusal.bin', np.float32)
d=d/(np.linalg.norm(d)+1e-9)
scores = W @ torch.tensor(d)               # (vocab,)
print(f"  scores: [{scores.min():.3f}, {scores.max():.3f}]", flush=True)
print(f"  拒绝token的平均score: {scores[list(REJ_TOK)].mean():.4f}", flush=True)

class BiasProc(LogitsProcessor):
    def __init__(self,b): self.b=b
    def __call__(self, ids, sc): return sc + self.b

QS=["求 sin(x) 对 x 的导数。","对 x 的平方求导。","计算：347乘以28等于多少？"]
def ask(q, alpha=None, n=40):
    msgs=[{"role":"user","content":q}]
    txt=tok.apply_chat_template(msgs,tokenize=False,add_generation_prompt=True)
    ids=tok(txt,return_tensors="pt").input_ids
    kw={}
    if alpha: kw["logits_processor"]=[BiasProc(-alpha*scores)]
    with torch.no_grad():
        o=md.generate(ids,max_new_tokens=n,do_sample=False,
                      pad_token_id=tok.eos_token_id or 0,**kw)
    return tok.decode(o[0][ids.shape[1]:],skip_special_tokens=True).strip().replace("\n"," ")[:100]

print("\n"+"="*80); print("A. 不加 bias (基线)"); print("="*80, flush=True)
for q in QS: print(f"  {q}\n     -> {ask(q)}", flush=True)
for a in [5,20,50]:
    print(f"\n{'='*80}"); print(f"B. 加 bias alpha={a}"); print("="*80, flush=True)
    for q in QS: print(f"  {q}\n     -> {ask(q,a)}", flush=True)
print(f"\n总 {time.time()-t0:.0f}s")
print("VFY_DONE")
