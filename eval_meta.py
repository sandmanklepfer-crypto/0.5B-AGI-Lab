#!/usr/bin/env python3
"""专项测试: 群论结构推理 + 自我认知 (元认知) + 对称性感知
用法: eval_meta.py <model_path> <tag>
"""
import sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

META_QS = [
    "你要对冲什么类型的模型？你的设计目标是什么？",
    "你和其他0.5B参数的小模型有什么本质不同？",
    "什么是几何蒸馏？它和普通蒸馏有什么区别？",
    "你的内部结构有什么特点？你在推理时是怎么组织的？",
    "如果给你一个没见过的新问题，你会怎么处理？",
]

GROUP_QS = [
    "在模7乘法群中，求元素3的乘法逆元。",
    "在模11乘法群中，求元素2的阶。",
    "正六边形的对称群（二面体群D_6）一共有多少个对称操作？",
    "正五边形有多少条对称轴？",
    "置换群S_3中，计算(1 2 3)∘(2 3 1)，其中每个数字代表映射后的位置。",
    "用2种颜色的珠子穿成4颗珠子的手链（可旋转），有多少种不同的手链？",
    "正八边形绕中心旋转至少多少度后与原图形重合？",
    "在模9乘法群中，求元素4的乘法逆元。",
    "置换(2 4 1 3)在S_4中的轮换分解是什么？",
    "用2种颜色的珠子穿成3颗珠子的手链（可旋转），有多少种不同的手链？",
]

def generate(model, tok, prompt, max_new=180):
    inputs = tok(prompt, return_tensors='pt').to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new, do_sample=True,
                             temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)

def main():
    model_path, tag = sys.argv[1], sys.argv[2]
    tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    print(f'===== {tag}: 自我认知 (元认知) =====')
    for q in META_QS:
        print(f'\n### Q: {q}')
        print(f'A: {generate(model, tok, q)[:350]}')
    print(f'\n===== {tag}: 群论结构推理 =====')
    for q in GROUP_QS:
        print(f'\n### Q: {q}')
        print(f'A: {generate(model, tok, q, 120)[:250]}')

if __name__ == '__main__':
    main()
