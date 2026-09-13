#!/usr/bin/env python3
"""数学穿帮题组: 0.5B 基座/v4c 的穿帮点, 1.5B 能否过关"""
import sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MATH = [
    "7 × 8 等于多少?",
    "2 的 10 次方等于多少?",
    "1/3 + 1/9 + 1/27 + ... 无穷级数的和是多少?",
    "一件商品打八折后是 96 元, 原价是多少?",
    "一个数的 3 倍加 5 等于 20, 这个数是多少?",
    "求 45 和 60 的最大公约数。",
    "一个正方形边长 5cm, 面积是多少?",
]

def generate(model, tok, prompt, max_new=100):
    inputs = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

def main():
    path = sys.argv[1]
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    print(f"===== {path}: 数学穿帮题 =====")
    for q in MATH:
        print(f"\n### Q: {q}")
        print(f"A: {generate(model, tok, q)[:200]}")

if __name__ == "__main__":
    main()
