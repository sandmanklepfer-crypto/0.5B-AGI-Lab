#!/usr/bin/env python3
# V125 极简探测: 0.5B 会不会 few-shot 转述? (几秒出结果, 决定要不要上 LoRA)
# context 给 3 个"卡原文→我的转述"示范, 再给 1 张新卡无箭头, 采样4次看会不会转述
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
DEMO = [
    ('卡A: 黎曼猜想说所有非平凡零点的实部都等于二分之一。',
     '我的转述: 黎曼猜的那个函数的特殊零点的位置全在一条中线上。'),
    ('卡B: 这个猜想从1859年到现在没人能证明。',
     '我的转述: 一百六十多年过去了，这道题还是悬着的。'),
    ('卡C: 欧拉把ζ函数写成了所有素数的乘积形式。',
     '我的转述: 欧拉发现这个函数跟每个质数都有关系，能拆成一串质数的乘法。'),
]
TEST_CARD = '卡D: ζ函数在s等于2的时候，它的值等于圆周率的平方除以6。'
PROMPT = ('下面每张卡是一句数学事实。我要用自己的话把卡的意思讲给别人听，不照抄原句。\n'
          + '\n'.join(a + b for a, b in DEMO) + '\n' + TEST_CARD)

def main():
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    ids = tok(PROMPT, return_tensors='pt').input_ids.to('cuda')
    for n in range(4):
        with torch.no_grad():
            out = model.generate(ids, max_new_tokens=60, do_sample=True, temperature=0.8,
                                 top_p=0.9, pad_token_id=tok.eos_token_id)
        text = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).replace('\n', ' ')
        print('[采样%d] %s' % (n+1, text), flush=True)

if __name__ == '__main__':
    main()
