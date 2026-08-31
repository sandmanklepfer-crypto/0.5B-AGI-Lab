#!/usr/bin/env python3
"""训练集外 (out-of-sample) 泛化测试: 原版 vs 几何蒸馏版
所有 prompt 均不在 distill_prompts.txt 中
"""
import sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/autodl-tmp/qwen05b'
DIST_GEOM = "/root/autodl-tmp/distill_mix_v4"

PROMPTS = [
    "解释一下引力波是什么。",
    "3的5次方等于多少?",
    "如果把一杯水放在零下10度的房间里一小时,会发生什么?",
    "用Python写一个计算圆面积的函数。",
    "光合作用的光反应和暗反应有什么区别?",
    "为什么海水是咸的?",
    "解释一下什么是自注意力机制。",
    "一架飞机从北京飞往纽约,向西飞和向东飞哪个更快?为什么?",
    "写一首关于秋天的四行诗。",
    "什么是图灵测试?",
]

def generate(model, tok, prompt, max_new=180):
    inputs = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new, do_sample=True,
                             temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'geom'
    path = DIST_GEOM if which == 'geom' else BASE
    tag = '几何蒸馏版' if which == 'geom' else '原版'
    print(f'=== {tag}: {path} ===')
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    for p in PROMPTS:
        print(f'\n### Q: {p}')
        try:
            r = generate(model, tok, p)
            print(f'A: {r[:400]}')
        except Exception as e:
            print(f'A: ERROR {e}')

if __name__ == '__main__':
    main()
