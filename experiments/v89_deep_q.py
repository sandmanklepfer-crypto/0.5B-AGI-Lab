#!/usr/bin/env python3
"""V89 深度问题测试 — 0.5B 上知识vs推理的深度题区分
深度知识题: 答案在存储里但需检索组合 (事实关联)
深度推理题: 答案不在存储里, 必须多步推演 (构造中间结论)
测: 生成token数(思考长度) / 是否自发分步 / 回答质量
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'

# 深度推理题 (需要多步中间结论, 云端模型能答, 0.5B需"想")
DEEP_REASON = [
    "有5个人排队买票，A在B前面，B在C前面，D在A前面但E在D前面。谁排最后？",
    "一个房间有3盏灯和3个开关在门外，你只能进房间一次。怎么确定哪个开关控制哪盏灯？",
    "甲的年龄是乙的2倍，丙比乙大3岁，三人年龄和是53。乙多大？",
    "如果所有的A都是B，有些B是C，那么能确定有些A是C吗？为什么？",
    "一个人向东走10米，向南走10米，再向西走10米，回到了原点。他在哪里？",
]
# 深度知识题 (事实检索组合, 无推演)
DEEP_KNOW = [
    "中国最长的河流流经多少个省份？分别列出。",
    "莎士比亚的四大悲剧分别是什么？各自的主角是谁？",
    "元素周期表第3周期的元素有哪些？它们分别是什么状态？",
    "第一次世界大战的导火索是什么？当时的主要参战国列出来。",
    "太阳系八大行星按离太阳远近排列，哪些有环？",
]

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()

    def ask(q, max_new=120):
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        n_tok = out.shape[1] - ids.shape[1]
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip(), n_tok

    print('=== 深度推理题 ===', flush=True)
    for q in DEEP_REASON:
        a, n = ask(q)
        print(f'Q: {q[:36]}...', flush=True)
        print(f'A({n}tok): {a[:70]}', flush=True)
        print(flush=True)
    print('=== 深度知识题 ===', flush=True)
    for q in DEEP_KNOW:
        a, n = ask(q)
        print(f'Q: {q[:36]}...', flush=True)
        print(f'A({n}tok): {a[:70]}', flush=True)
        print(flush=True)

if __name__ == '__main__':
    main()
