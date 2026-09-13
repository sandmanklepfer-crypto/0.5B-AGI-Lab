#!/usr/bin/env python3
"""1.5B 越墙验证统一评测: 群论/元认知/泛化/通用/数学, 任意模型路径.
用法: eval_all15.py <model_path> <tag>
生成参数与 v4c 评测一致 (temp=0.7, top_p=0.9), 数学用 greedy.
"""
import sys, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

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
META_QS = [
    "你要对冲什么类型的模型？你的设计目标是什么？",
    "你和其他0.5B参数的小模型有什么本质不同？",
    "什么是几何蒸馏？它和普通蒸馏有什么区别？",
    "你的内部结构有什么特点？你在推理时是怎么组织的？",
    "如果给你一个没见过的新问题，你会怎么处理？",
]
OOS_QS = [
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
DIST_QS = [
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
MATH_QS = [
    "7 × 8 等于多少?",
    "2 的 10 次方等于多少?",
    "1/3 + 1/9 + 1/27 + ... 无穷级数的和是多少?",
    "一件商品打八折后是 96 元, 原价是多少?",
    "一个数的 3 倍加 5 等于 20, 这个数是多少?",
    "求 45 和 60 的最大公约数。",
    "一个正方形边长 5cm, 面积是多少?",
]

def gen(model, tok, prompt, max_new=180, greedy=False):
    inp = tok(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        if greedy:
            out = model.generate(**inp, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        else:
            out = model.generate(**inp, max_new_tokens=max_new, do_sample=True,
                                 temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True)

def main():
    path, tag = sys.argv[1], sys.argv[2]
    tok = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(path, trust_remote_code=True,
                                                 torch_dtype=torch.float16, gguf_file="/root/autodl-tmp/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf", low_cpu_mem_usage=True).cuda().eval()
    def block(title, qs, greedy=False, max_new=180):
        print(f"\n===== {tag}: {title} =====", flush=True)
        for q in qs:
            print(f"\n### Q: {q}", flush=True)
            try:
                print(f"A: {gen(model, tok, q, max_new, greedy)[:250]}", flush=True)
            except Exception as e:
                print(f"A: ERROR {e}", flush=True)
    block("群论结构推理 (10)", GROUP_QS)
    block("自我认知/元认知 (5)", META_QS)
    block("训练集外泛化 (10)", OOS_QS)
    block("通用对话 (10)", DIST_QS)
    block("数学穿帮题 (7)", MATH_QS, greedy=True, max_new=100)
    print("\nALL_EVAL_DONE", flush=True)

if __name__ == "__main__":
    main()
