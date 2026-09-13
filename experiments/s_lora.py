# -*- coding: utf-8 -*-
"""测 CPU+LoRA 训练速度 (可行性验证)"""
import time, torch, sys
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model
t0=time.time()
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), flush=True)
print("加载模型...", flush=True)
tok=AutoTokenizer.from_pretrained("/root/distill_calc_v1")
tok.pad_token=tok.eos_token
md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1", dtype=torch.float32)
print(f"  加载 {time.time()-t0:.0f}s", flush=True)
cfg=LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj","v_proj"],
               lora_dropout=0.0, bias="none", task_type="CAUSAL_LM")
md=get_peft_model(md, cfg)
md.print_trainable_parameters()
print("测单步训练...", flush=True)
opt=torch.optim.AdamW([p for p in md.parameters() if p.requires_grad], lr=1e-4)
txt=["计算 3+5 等于多少","答案 = ⟨calc⟩3+5⟨/calc⟩"]
enc=tok(txt,return_tensors="pt",padding=True,truncation=True,max_length=64)
il=enc["input_ids"].shape[1]//2
full=enc["input_ids"]; lab=full.clone(); lab[:,:il]=-100
t1=time.time()
loss=md(full,attention_mask=enc["attention_mask"],labels=lab).loss
loss.backward(); opt.step(); opt.zero_grad()
dt=time.time()-t1
print(f"  单步(含反向): {dt:.2f}s", flush=True)
print(f"  -> 训练400样本x2epoch(200步) 预计: {dt*200/60:.1f} 分钟", flush=True)
print(f"总耗时 {time.time()-t0:.0f}s", flush=True)
print("LORA_TEST_DONE")
