#!/usr/bin/env python3
# V136 独立复述: 0.5B 不靠13B, 只凭捕猎消化链, 独立讲黎曼几何
# 验证: 猎到的是否内化(能自己重组) vs 只是复读
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# 它自己刚才的消化链(v135输出, 纯它自己的话, 无13B原文)
HIS_DIGEST = """曲面上的点对映时会有局部弯曲的程度, 可以描述为角度的变化系数(角曲性)。
黎曼度量是一种数学工具, 在几何学中是度量空间的重要手段。
曲率是沿着一条曲线测得的弯曲程度, 是个局部函数, 在物理学里(广义相对论)也很重要。
之前我还理解到: 直线对点的离散程度就是它的距离(metric), 两点距离=|P1-P2|。
我还说过: 给物体加特殊方向会得到新的数学形态, 叫弯曲。"""

QS = [
    '用你自己的话讲讲: 什么是黎曼度量? 你刚才学到的是什么?',
    '那曲率到底是什么? 为什么它和弯曲有关? 你能打个比方吗?',
    '你觉得你理解了吗? 哪里还模糊? 如果你要教一个更小的模型, 你会怎么讲?',
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained('/root/autodl-tmp/qwen25_base_raw',
                                                 torch_dtype=torch.float16).to('cuda').eval()
    print('[V136] 0.5B独立复述(无13B帮助) | 上下文=它自己的消化链', flush=True)
    ctx = '以下是我之前学习黎曼几何时自己写下的一些理解:\n%s\n' % HIS_DIGEST
    for i, q in enumerate(QS):
        prompt = ctx + ('\n(现在没有人帮我了, 我自己想)\n问题: %s\n我的理解:' % q)
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=100, do_sample=True, temperature=0.85,
                               top_p=0.9, repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
        ans = tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()
        print('\n【%s】\n  → %s' % (q, ans[:350]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
