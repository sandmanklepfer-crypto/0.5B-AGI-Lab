# -*- coding: utf-8 -*-
"""手动 LoRA + CPU 训练速度测试"""
import time, torch, torch.nn as nn
from transformers import AutoModelForCausalLM, AutoTokenizer
t0=time.time()
print("torch",torch.__version__,"cuda",torch.cuda.is_available(),flush=True)
tok=AutoTokenizer.from_pretrained("/root/distill_calc_v1")
tok.pad_token=tok.eos_token
md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1", dtype=torch.float32)
print(f"加载 {time.time()-t0:.0f}s",flush=True)

R=8
class LoRALin(nn.Module):
    def __init__(self, base, r=R, alpha=16):
        super().__init__()
        self.base=base; self.scale=alpha/r
        for p in self.base.parameters(): p.requires_grad=False
        self.A=nn.Parameter(torch.randn(r, base.in_features)*0.01)
        self.B=nn.Parameter(torch.zeros(base.out_features, r))
    def forward(self,x):
        return self.base(x) + (x@self.A.T@self.B.T)*self.scale

cnt=0
for l in md.model.layers:
    l.self_attn.q_proj=LoRALin(l.self_attn.q_proj)
    l.self_attn.v_proj=LoRALin(l.self_attn.v_proj)
    cnt+=2
tr=[p for p in md.parameters() if p.requires_grad]
print(f"  注入 {cnt} 个 LoRA, 可训练 {sum(p.numel() for p in tr):,} 参数",flush=True)
opt=torch.optim.AdamW(tr, lr=2e-4)
txt="计算 3+5 等于多少\n答案 = ⟨calc⟩3+5⟨/calc⟩"
enc=tok(txt,return_tensors="pt",max_length=64,truncation=True)
ids=enc["input_ids"]; il=ids.shape[1]//2
lab=ids.clone(); lab[:,:il]=-100
md.train()
t1=time.time()
loss=md(ids,attention_mask=enc["attention_mask"],labels=lab).loss
loss.backward(); opt.step(); opt.zero_grad()
dt=time.time()-t1
print(f"  单步(前向+反向+更新): {dt:.2f}s",flush=True)
print(f"  → 200步预计 {dt*200/60:.1f} 分钟",flush=True)
print(f"总 {time.time()-t0:.0f}s",flush=True)
print("LORA2_DONE")
