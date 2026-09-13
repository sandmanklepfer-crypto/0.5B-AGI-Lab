# -*- coding: utf-8 -*-
"""手动LoRA + 绕过坏torchvision + CPU训练速度测试"""
import sys, types, time
# ---- 绕过 torchvision ----
import importlib.machinery as _m
def _mk(name,is_pkg=False):
    mm=types.ModuleType(name); mm.__version__="0.0.0"
    mm.__spec__=_m.ModuleSpec(name,None,is_package=is_pkg)
    if is_pkg: mm.__path__=[]
    return mm
fake=_mk("torchvision",True); tr=_mk("torchvision.transforms")
class IM: pass
tr.InterpolationMode=IM
for a in ["Compose","ToTensor","Normalize","Resize","CenterCrop","RandomHorizontalFlip"]:
    setattr(tr,a,object)
fake.transforms=tr
sys.modules["torchvision"]=fake
sys.modules["torchvision.transforms"]=tr
import torch, torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
t0=time.time()
print("torch",torch.__version__,flush=True)
tok=AutoTokenizer.from_pretrained("/root/distill_calc_v1")
tok.pad_token=tok.eos_token
md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1",dtype=torch.float32)
print(f"加载OK {time.time()-t0:.0f}s 层数={len(md.model.layers)}",flush=True)
R=8
class LoRALin(nn.Module):
    def __init__(s,base,r=R,alpha=16):
        super().__init__(); s.base=base; s.scale=alpha/r
        for p in base.parameters(): p.requires_grad=False
        s.A=nn.Parameter(torch.randn(r,base.in_features)*0.01)
        s.B=nn.Parameter(torch.zeros(base.out_features,r))
    def forward(s,x): return s.base(x)+(x@s.A.T@s.B.T)*s.scale
for l in md.model.layers:
    l.self_attn.q_proj=LoRALin(l.self_attn.q_proj)
    l.self_attn.v_proj=LoRALin(l.self_attn.v_proj)
tr_=[p for p in md.parameters() if p.requires_grad]
print(f"可训练参数 {sum(p.numel() for p in tr_):,}",flush=True)
opt=torch.optim.AdamW(tr_,lr=2e-4)
enc=tok("计算 3+5 等于多少\n答案 = ⟨calc⟩3+5⟨/calc⟩",return_tensors="pt",max_length=64,truncation=True)
ids=enc["input_ids"]; il=ids.shape[1]//2
lab=ids.clone(); lab[:,:il]=-100
md.train(); t1=time.time()
loss=md(ids,attention_mask=enc["attention_mask"],labels=lab).loss
loss.backward(); opt.step(); opt.zero_grad()
dt=time.time()-t1
print(f"单步 {dt:.2f}s  -> 200步 {dt*200/60:.1f}分钟",flush=True)
print(f"总 {time.time()-t0:.0f}s",flush=True)
print("LORA3_DONE")
