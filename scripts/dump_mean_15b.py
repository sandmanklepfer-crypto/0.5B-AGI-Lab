#!/usr/bin/env python3
"""1.5B mean口径 dump: 879段每段mean激活, 存成 dump_layers 同格式 (与32B严格同口径)
用法: dump_mean_15b.py <model> <text_file> <out_dir>
"""
import sys, struct
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

path, text_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True,
                                             torch_dtype=torch.bfloat16).cuda().eval()
n_layer = model.config.num_hidden_layers
d = model.config.hidden_size
lines = [l for l in open(text_path, encoding='utf-8', errors='replace').read().split('\n') if l.strip()]
print(f"[dump15] {n_layer}层 x {d}维, {len(lines)} 段", flush=True)
import os
os.makedirs(out_dir, exist_ok=True)
for idx, line in enumerate(lines):
    ids = tok(line, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True).hidden_states
    fn = os.path.join(out_dir, f"a_L{idx+1:02d}.bin")
    with open(fn, 'wb') as f:
        f.write(struct.pack('<2i', n_layer, d))
        for x in h:
            v = x[0].mean(0).float().cpu().numpy()
            f.write(v.astype(np.float32).tobytes())
    if (idx + 1) % 100 == 0:
        print(f"  {idx+1}/{len(lines)}", flush=True)
print(f"done {len(lines)} texts", flush=True)
