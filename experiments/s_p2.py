import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
BASE="/root/autodl-tmp/qwen25_base_raw"
AH="/root/autodl-tmp/life1/antiheb_05b"
tok=AutoTokenizer.from_pretrained(BASE)
TEST="人工智能是计算机科学的一个分支，它研究如何让机器模拟人类的智能行为。水循环是指水在地球上的循环过程。"
PROMPTS=[("推理1步","12 + 34 = ?\n答："),("推理2步","12 + 34 + 56 = ?\n答："),
         ("推理3步","(12 + 34) * 2 = ?\n答："),("风格-老屋","爷爷去世后，山腰那栋老屋空了七年。我这次回来，"),
         ("常识","水的沸点是")]
ids=tok(TEST,return_tensors="pt").input_ids.cuda()
def load(d):
    return AutoModelForCausalLM.from_pretrained(d,torch_dtype=torch.float16).to("cuda").eval()
def ppl(m):
    with torch.no_grad(): return torch.exp(m(ids,labels=ids).loss).item()
def gen(m,p,n=28):
    i=tok(p,return_tensors="pt").input_ids.cuda()
    with torch.no_grad():
        o=m.generate(i,max_new_tokens=n,do_sample=False,pad_token_id=tok.eos_token_id)
    return tok.decode(o[0][i.shape[1]:],skip_special_tokens=True).replace("\n"," ")[:75]
print("="*74); print("[A] base 模型"); m=load(BASE); print(f"  困惑度={ppl(m):.3f}")
for nm,p in PROMPTS: print(f"  [{nm}] -> {gen(m,p)}")
del m; torch.cuda.empty_cache()
print(); print("="*74); print("[B] antiheb (写活版)")
try:
    a=load(AH); print(f"  困惑度={ppl(a):.3f}")
    for nm,p in PROMPTS: print(f"  [{nm}] -> {gen(a,p)}")
    del a; torch.cuda.empty_cache()
except Exception as e: print("  失败:",str(e)[:100])
print(); print("="*74); print("[C] 扰动曲线: base第12层加 eps*噪声")
m=load(BASE); W0=m.model.layers[12].mlp.down_proj.weight.data.clone()
sd=W0.float().std().item(); print(f"  权重std={sd:.6f}")
for eps in [0,1e-4,1e-3,1e-2,1e-1]:
    with torch.no_grad():
        m.model.layers[12].mlp.down_proj.weight.data.copy_(W0+torch.randn_like(W0)*sd*eps)
    print(f"  eps={eps:.0e}  困惑度={ppl(m):9.3f}  老屋续写='{gen(m,PROMPTS[3][1],20)}'")
print("ALL DONE")
