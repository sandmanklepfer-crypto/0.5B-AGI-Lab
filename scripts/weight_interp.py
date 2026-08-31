#!/usr/bin/env python3
"""weight_interp.py — 权重插值救 v5b: w_fixed = (1-β)·v4c + β·v5b
β 扫描 0.3/0.5/0.7, 测基础题恢复 (100-37/7×8/图灵/模板)
用法: weight_interp.py
"""
import sys, os, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

GOOD = '/root/distill_v4c'
MIX = '/root/distill_v5b_s3'

QS = ["100减37等于多少？", "7乘以8等于多少？", "图灵在1950年发表的著名论文叫什么名字？"]
GOOD_ANS = {"100减37等于多少？": "63", "7乘以8等于多少？": "56"}

def gen(model, tok, q, max_new=40):
    ids = tok(q, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    tok = AutoTokenizer.from_pretrained(GOOD); tok.pad_token = tok.eos_token
    good = AutoModelForCausalLM.from_pretrained(GOOD, dtype=torch.bfloat16).to("cuda:0")
    mix = AutoModelForCausalLM.from_pretrained(MIX, dtype=torch.bfloat16).to("cuda:0")
    good.eval(); mix.eval()
    g_sd, m_sd = good.state_dict(), mix.state_dict()

    for beta in [0.3, 0.5, 0.7]:
        out_dir = f'/root/distill_v5b_i{int(beta*10)}'
        fixed = {}
        for k in g_sd:
            if k in m_sd:
                fixed[k] = ((1 - beta) * g_sd[k].float() + beta * m_sd[k].float()).to(torch.bfloat16)
        mix.load_state_dict(fixed)
        os.makedirs(out_dir, exist_ok=True)
        mix.save_pretrained(out_dir); tok.save_pretrained(out_dir)
        print(f"=== β={beta} ===", flush=True)
        for q in QS:
            a = gen(mix, tok, q)
            ok = ""
            if q in GOOD_ANS:
                ok = " ✅" if GOOD_ANS[q] in a[:20] else " ❌"
            print(f"  {q[:18]}: {a[:60]}{ok}", flush=True)
    print("[done]", flush=True)

if __name__ == "__main__":
    main()
