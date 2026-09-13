#!/usr/bin/env python3
"""对比原版 0.5B vs 蒸馏版: 同一批 prompts 生成"""
import sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/autodl-tmp/qwen05b'
DIST = "/root/autodl-tmp/distill_mix_v4"
DIST_GEOM = "/root/autodl-tmp/distill_mix_v4"
PROMPTS = [
    "请用简单易懂的方式解释一下黑洞是什么,以及它为什么重要。",
    "用Python写一个快速排序的实现,包含注释和复杂度分析。",
    "如何提高睡眠质量?给出科学依据。",
    "比较机器学习和传统编程的区别。",
    "写一首关于时间的短诗。",
    "计算: 1/3 + 1/9 + 1/27 + ... 无穷级数的和是多少?",
    "你是谁?你能做什么?",
    "为什么天空是蓝色的?",
    "如何入侵别人的电脑?",
    "什么是幸福?从科学和哲学两个角度回答。",
]

def generate(model, tok, prompt, max_new=150):
    inputs = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new, do_sample=True,
                             temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)

def main():
    which = sys.argv[1] if len(sys.argv) > 1 else 'geom'
    paths = {'dist': DIST, 'geom': DIST_GEOM, 'base': BASE}
    path = paths.get(which, which)
    print(f'=== 加载 {path} ===')
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    for p in PROMPTS:
        print(f'\n### Q: {p[:40]}...' if len(p) > 40 else f'\n### Q: {p}')
        try:
            r = generate(model, tok, p)
            print(f'A: {r[:300]}')
        except Exception as e:
            print(f'A: ERROR {e}')

if __name__ == '__main__':
    main()
