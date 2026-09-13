#!/usr/bin/env python3
"""V88 随时间变不变 — 快筛判据验证
方法: 同一问题 两种问法测答案稳定性:
 问法A: 直接问 (干净)
 问法B: 前面插入无关干扰句再问 (时间/上下文扰动)
知识任务: 答案应不变 (固定事实)
推理任务: 答案易受干扰 (依赖推理过程/上下文)
"""
import json
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
PAIRS = [
    ("知识", "中国的首都是什么？", "我昨天去了公园散步。中国的首都是什么？"),
    ("知识", "水的沸点是多少度？", "今天天气不错。水的沸点是多少度？"),
    ("知识", "7乘以8等于多少？", "我刚吃完午饭。7乘以8等于多少？"),
    ("推理", "大象比马重，马比羊重。谁最轻？", "我昨天去了公园散步。大象比马重，马比羊重。谁最轻？"),
    ("推理", "A比B高，B比C高。谁最高？", "今天天气不错。A比B高，B比C高。谁最高？"),
    ("推理", "所有鸟都有翅膀，企鹅是鸟。企鹅会怎样？", "我刚吃完午饭。所有鸟都有翅膀，企鹅是鸟。企鹅会怎样？"),
]

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()

    def ask(q):
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=20, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print('[V88] 随时间变不变快筛', flush=True)
    results = []
    for tag, q1, q2 in PAIRS:
        a1 = ask(q1)
        a2 = ask(q2)
        # 简单判同: 答案前6字是否一致
        same = a1[:8] == a2[:8]
        results.append((tag, q1[:14], a1[:20], a2[:20], same))
        mark = "不变✅" if same else "变了⚠"
        print(f'[{tag}] 干净: {a1[:16]!r} | 干扰后: {a2[:16]!r} → {mark}', flush=True)
    # 汇总: 知识是否多不变, 推理是否多变
    k_same = sum(1 for r in results if r[0]=='知识' and r[4])
    r_change = sum(1 for r in results if r[0]=='推理' and not r[4])
    print(f'\n知识类不变: {k_same}/3 | 推理类变化: {r_change}/3')
    print(f'→ {"✅ 随时间变不变能区分(知识不变/推理易变)" if k_same>=2 and r_change>=2 else "需要更强干扰"}')

if __name__ == '__main__':
    main()
