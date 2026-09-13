#!/usr/bin/env python3
"""V82 干净写活泛化测试 — 归一化单方向修改后, 各种任务是否都稳
写活: 沿1个干净方向 归一化幅度s 改 layer12.down_proj
任务集: 写作/问答/推理/翻译/续写 多类型
对比: 改前 vs 改后(幅度0.06/0.12) 每任务质量
"""
import os, re, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TASKS = [
    ("写作", "写一段关于大海的短文。"),
    ("问答", "一年有几个季节？答："),
    ("推理", "所有鸟都有翅膀，企鹅是鸟。企鹅会怎样？答："),
    ("因果", "因为下雨地湿了，地湿所以路滑。问：为什么路滑？答："),
    ("描述", "描述一下你最喜欢的季节。"),
    ("常识", "太阳从哪边升起？答："),
    ("续写", "他推开门，发现屋里"),
]

def gen(model, tok, prompt, n=30):
    ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode():
        out = model.generate(input_ids=ids, max_new_tokens=n, do_sample=True,
                             temperature=0.8, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

def quality(a):
    if len(a) < 6: return 0.0
    cn = sum(1 for c in a if '\u4e00' <= c <= '\u9fff')
    ratio = cn / max(len(a), 1)
    if re.search(r'(.)\1{5,}', a): ratio *= 0.2
    return ratio

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    WN = 'model.layers.12.mlp.down_proj.weight'

    def load_with_patch(scale):
        m = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
        if scale > 0:
            with torch.no_grad():
                W = m.state_dict()[WN].float()
                torch.manual_seed(7)
                d = torch.randn(W.shape[0], device='cuda')
                d = d / d.norm()
                patch = torch.outer(d, torch.randn(W.shape[1], device='cuda'))
                patch = patch / patch.norm() * W.norm() * scale
                m.state_dict()[WN].copy_((W + patch).to(torch.bfloat16))
        return m

    print("=== V82 干净写活泛化测试 ===", flush=True)
    for scale in [0.0, 0.06, 0.12]:
        m = load_with_patch(scale)
        print(f"\n--- 写活幅度={scale} ---", flush=True)
        scores = []
        for name, q in TASKS:
            a = gen(m, tok, q)
            ql = quality(a)
            scores.append(ql)
            flag = "✅" if ql > 0.5 else "❌"
            print(f"  [{name}] 质量{ql:.2f} {flag} | {a[:32]!r}", flush=True)
        print(f"  平均质量: {np.mean(scores):.2f} (基线{'参考' if scale==0 else '对比'})", flush=True)
        del m; torch.cuda.empty_cache()
    print("\n=== V82 DONE ===", flush=True)

if __name__ == '__main__':
    main()
