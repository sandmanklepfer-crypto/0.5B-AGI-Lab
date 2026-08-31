#!/usr/bin/env python3
"""C方案生成: 掩码扩散迭代去掩码 (模拟去噪)
用法: generate_mask_diff.py <model_dir> <lora_dir> <prompt> [steps=32] [unmask_per_step=6]
"""
import sys, math, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

model_dir, lora_dir, prompt = sys.argv[1], sys.argv[2], sys.argv[3]
steps = int(sys.argv[4]) if len(sys.argv) > 4 else 32
unmask = int(sys.argv[5]) if len(sys.argv) > 5 else 6

tok = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
mask_id = tok.pad_token_id if tok.pad_token_id is not None else 151643
base = AutoModelForCausalLM.from_pretrained(model_dir, trust_remote_code=True,
                                            torch_dtype=torch.bfloat16).cuda().eval()
model = PeftModel.from_pretrained(base, lora_dir).eval()

ids = tok(prompt, add_special_tokens=False)['input_ids']
T = len(ids) + 96  # 生成长度 = prompt + 96
cur = [mask_id] * T
cur[:len(ids)] = ids
cur = torch.tensor([cur]).cuda()

known = [True] * len(ids) + [False] * 96
known = torch.tensor([known]).cuda()

for step in range(steps):
    with torch.inference_mode():
        logits = model(input_ids=cur).logits[0]  # (T, V)
    # 未知位置按 logits 置信度排序
    cand = (~known[0]).nonzero(as_tuple=True)[0]
    if len(cand) == 0:
        break
    probs = logits[cand].softmax(-1).max(-1).values
    n_unmask = min(unmask, len(cand))
    topk = cand[probs.argsort(descending=True)[:n_unmask]]
    for j in topk:
        cur[0, j] = logits[j].argmax(-1)
        known[0, j] = True

out = cur[0, len(ids):].tolist()
# 去掉 pad/mask 尾巴
text = tok.decode([t for t in out if t != mask_id and t != tok.eos_token_id], skip_special_tokens=True)
print(text)
print(f'\n[MASKDIFF] steps={steps} unmask/step={unmask} 生成长度={len(text)}字')
