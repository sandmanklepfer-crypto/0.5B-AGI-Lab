#!/usr/bin/env python3
"""extract_bad.py — 从崩坏模型提取"坏模式" (反面教材)
1. 用 v5c 生成崩坏输出 (乱码/重复/模板串扰) -> neg_samples.txt
2. 坏方向: v5c 崩坏生成激活 - v4c 正常生成激活 -> bad_dirs.npz (层22)
用法: extract_bad.py [--n N]
"""
import sys, os, json, argparse
import numpy as np
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

GOOD = '/root/distill_v4c'
BAD = '/root/distill_v5c'
S_LAYER = 22

PROBES = [
    "100减37等于多少？",
    "7乘以8等于多少？",
    "图灵在1950年发表的著名论文叫什么名字？",
    "所有的A都是B，所有的B都是C，那么A是什么？",
    "请用一段话介绍你自己。",
]

def gen_text(model, tok, q, max_new=60):
    ids = tok(q, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def act_pool(model, tok, text, layer):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    return h.hidden_states[layer][0].mean(0).float()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(GOOD); tok.pad_token = tok.eos_token
    good = AutoModelForCausalLM.from_pretrained(GOOD, dtype=torch.bfloat16).to("cuda:0")
    bad = AutoModelForCausalLM.from_pretrained(BAD, dtype=torch.bfloat16).to("cuda:0")
    good.eval(); bad.eval()

    # 1. 崩坏输出样本
    neg = []
    for q in PROBES:
        for _ in range(args.n // len(PROBES) + 1):
            b = gen_text(bad, tok, q)
            if len(b) > 10 and ('ilma' in b or '废话' in b or len(set(b)) < len(b) * 0.5
                                or '请提供' in b or '请阅读' in b):
                neg.append({"q": q, "bad": b[:200]})
                if len(neg) >= args.n: break
        if len(neg) >= args.n: break
    json.dump(neg, open('/root/neg_samples.json', 'w'), ensure_ascii=False, indent=1)
    print(f"[neg] {len(neg)} bad samples -> /root/neg_samples.json", flush=True)

    # 2. 坏方向: 对每个 probe, d_bad = norm(v5c激活 - v4c激活) (坏-好)
    dirs = []
    for q in PROBES:
        with torch.inference_mode():
            a_good = act_pool(good, tok, q, S_LAYER)
            a_bad = act_pool(bad, tok, q, S_LAYER)
        d = a_bad - a_good
        d = d / (d.norm() + 1e-12)
        dirs.append(d.cpu().numpy())
    D = np.stack(dirs)
    np.savez('/root/bad_dirs.npz', dirs=D)
    print(f"[dirs] {D.shape} -> /root/bad_dirs.npz (层{S_LAYER} 坏方向)", flush=True)

if __name__ == "__main__":
    main()
