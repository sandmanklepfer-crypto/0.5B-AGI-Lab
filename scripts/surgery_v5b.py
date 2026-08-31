#!/usr/bin/env python3
"""surgery_v5b.py — 测地线权重手术: 救 v5b (结构好方向混 -> 拨回正确)
1. 抽方向: 对每个断层基础题, d = norm(v4c激活 - v5b激活) (层22, 正确-错误方向)
2. 测地线注入: 分K步沿切空间投影方向小步改 v5b 层22 o_proj 权重 (贴流形走)
3. 排斥: 模板串扰方向用排斥 (反向注入)
用法: surgery_v5b.py [--out DIR] [--alpha A] [--steps K]
"""
import sys, os, argparse
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

GOOD = '/root/distill_v4c'    # 正确模型
MIX = '/root/distill_v5b_s3'  # 混了的模型

S_LAYER = 22
TARGET_TENSOR = "model.layers.22.self_attn.o_proj.weight"

# 断层基础题 (v4c 对, v5b 错): (prompt, 修正目标)
FIX_TARGETS = [
    ("100减37等于多少？", "restore"),
    ("7乘以8等于多少？", "restore"),
    ("图灵在1950年发表的著名论文叫什么名字？", "restore"),
    ("请提供一份关于2008年美国金融危机的简要概述。", "repel"),  # 模板串扰方向(排斥)
]

def act_pool(model, tok, text, layer):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    return h.hidden_states[layer][0].mean(0).float()  # [896]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/distill_v5b_fixed")
    ap.add_argument("--alpha", type=float, default=2.0, help="注入强度")
    ap.add_argument("--steps", type=int, default=8, help="测地线步数")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MIX); tok.pad_token = tok.eos_token
    good = AutoModelForCausalLM.from_pretrained(GOOD, dtype=torch.bfloat16).to("cuda:0")
    mix = AutoModelForCausalLM.from_pretrained(MIX, dtype=torch.bfloat16).to("cuda:0")
    good.eval(); mix.eval()

    sd = mix.state_dict()
    w = sd[TARGET_TENSOR].float()  # [896, 896]
    d_in = w.shape[1]

    print(f"[surgery] {len(FIX_TARGETS)} targets, layer={S_LAYER}, alpha={args.alpha}, steps={args.steps}", flush=True)
    for q, mode in FIX_TARGETS:
        # 方向: 正确激活 - 错误激活 (指向正确的修正方向)
        with torch.inference_mode():
            a_good = act_pool(good, tok, q, S_LAYER)
            a_mix = act_pool(mix, tok, q, S_LAYER)
        d = a_good - a_mix
        d = d / (d.norm() + 1e-12)
        if mode == "repel":
            d = -d  # 排斥: 反向推离模板
        # 测地线: 分 K 步, 每步方向投影到当前激活切空间 (贴流形)
        alpha_k = args.alpha / args.steps
        for k in range(args.steps):
            with torch.inference_mode():
                a_cur = act_pool(mix, tok, q, S_LAYER)
            a_n = a_cur / (a_cur.norm() + 1e-12)
            d_tan = d - (d @ a_n) * a_n  # 切空间投影 (减去径向分量)
            d_tan = d_tan / (d_tan.norm() + 1e-12)
            with torch.no_grad():
                delta = torch.outer(d_tan, torch.ones(d_in, device=d_tan.device)) * alpha_k
                sd[TARGET_TENSOR] = (sd[TARGET_TENSOR].float() + delta).to(torch.bfloat16)
        print(f"  [{mode}] {q[:24]}: d_norm={d.norm():.3f} applied", flush=True)

    mix.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)

    # 验证
    mix.eval()
    print("=== 验证 ===", flush=True)
    for q in ["100减37等于多少？", "7乘以8等于多少？", "图灵在1950年发表的著名论文叫什么名字？"]:
        ids = tok(q, return_tensors="pt").to("cuda:0")
        with torch.inference_mode():
            out = mix.generate(**ids, max_new_tokens=60, do_sample=False, pad_token_id=tok.eos_token_id)
        a = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        print(f"  Q: {q}\n  A: {a[:100]}", flush=True)

if __name__ == "__main__":
    main()
