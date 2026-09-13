#!/usr/bin/env python3
"""spec_diag.py — 底层几何诊断: 权重谱对比 (稳定 vs 崩坏)
假设: 崩坏 = 权重谱坍缩 (奇异值集中/有效秩下降)
对比: qwen05b(原始) / v4c(稳定) / chain_v1(崩坏, 干净基座训) 的层22权重谱
用法: spec_diag.py
"""
import sys, glob
import numpy as np
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODELS = {
    "qwen05b(原始)": "/root/autodl-tmp/qwen05b",
    "v4c(稳定)": "/root/distill_v4c",
    "chain_v1(崩坏)": "/root/distill_chain_v1",
}
TENSORS = ["model.layers.22.self_attn.o_proj.weight", "model.layers.22.mlp.down_proj.weight",
           "model.embed_tokens.weight"]

def spec_metrics(w):
    """谱指标: 奇异值分布 -> 有效秩/集中度"""
    s = torch.linalg.svdvals(w.float())
    s = s[s > 1e-6]
    if len(s) == 0:
        return {"rank": 0, "conc": 1.0}
    p = s / s.sum()
    ent = -(p * torch.log(p + 1e-12)).sum().item()
    eff_rank = np.exp(ent)          # 有效秩 (谱熵指数)
    conc = (s[0] / s.sum()).item()  # 最大奇异值占比 (集中度)
    return {"rank": int(len(s)), "eff_rank": round(eff_rank, 1),
            "s1_ratio": round(conc, 4), "s1_s2": round((s[0]/(s[1]+1e-12)).item(), 3)}

def main():
    for name, path in MODELS.items():
        try:
            model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16)
        except Exception as e:
            print(f"{name}: LOAD FAIL {e}", flush=True); continue
        print(f"===== {name} =====", flush=True)
        for t in TENSORS:
            sd = model.state_dict()
            if t not in sd:
                # 找最近 tensor
                cand = [k for k in sd if t.split('.')[-1] in k][:2]
                for c in cand:
                    print(f"  {c}: {spec_metrics(sd[c])}", flush=True)
                continue
            print(f"  {t.split('layers.')[-1]}: {spec_metrics(sd[t])}", flush=True)
        del model; torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
