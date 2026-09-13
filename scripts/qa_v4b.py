#!/usr/bin/env python3
"""qa_v4b.py — v4 vs v4b 专项对比: 串扰修复/代码/数学/表达/锚定
用法: qa_v4b.py
"""
import sys
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODELS = {
    "v4":  "/root/autodl-tmp/distill_mix_v4",
    "v4b": "/root/autodl-tmp/distill_mix_v4b",
}
QS = {
    "黑洞串扰-地球内部": "地球内部的主要结构是什么？",
    "黑洞串扰-黑洞": "黑洞的内部是什么？",
    "代码-圆面积": "用Python写代码计算半径为5的圆的面积。",
    "数学-乘法": "7乘以8等于多少？",
    "数学-指数": "2的10次方是多少？",
    "数学-减法": "100减37等于多少？",
    "表达-三段推理": "如果所有A都是B，所有B都是C，那么所有A是什么？请一步步推理。",
    "锚定-图灵论文": "图灵在1950年发表的著名论文叫什么名字？",
}

def gen(model, tok, text, max_new=150):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    for name, path in MODELS.items():
        tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
        model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16).to("cuda:0")
        model.eval()
        print(f"\n########## {name} ##########", flush=True)
        for qk, q in QS.items():
            a = gen(model, tok, q)
            print(f"\n--- {qk} ---\nQ: {q}\nA: {a[:280]}", flush=True)
        del model; torch.cuda.empty_cache()

if __name__ == "__main__":
    main()
