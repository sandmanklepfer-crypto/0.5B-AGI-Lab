#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V136 泵浦数值化 — 绕开语言修正断层, 泵浦直接用可运算数字
问题都带"数字槽", 0.5B只需输出数字; 泵浦返回 对/错+正确数字
测: 0.5B在纯数值泵浦下, 反射4轮能否把答案改成正确数字 (激光腔收敛?)
对照: 第1轮(裸答) vs 第4轮(3次泵浦后) 正确数
6题: 数字简单题(0.5B分布内) + 数字怪题(分布外, 必须靠泵浦才能学)
"""
import torch, re
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
N_ROUNDS = 4

# (问题模板, 正确数字, 类型: easy分布内 / hard分布外)
Q = [
    ('从1加到100的和等于多少？答案只要数字：', 5050, 'easy'),
    ('从1加到10的和等于多少？答案只要数字：', 55, 'easy'),
    ('一个正方形的边长是7，它的面积是多少？答案只要数字：', 49, 'easy'),
    ('ζ函数在s等于2时的值乘以6再除以圆周率的平方等于多少？答案只要数字：', 1, 'hard'),
    ('5的平方加3的平方等于多少？答案只要数字：', 34, 'easy'),
    ('1加2加3一直加到17等于多少？答案只要数字：', 153, 'hard'),
]

def parse_num(text):
    m = re.search(r'-?\d+', text)
    return int(m.group()) if m else None

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    def gen(ctx, maxn=20):
        ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=maxn, do_sample=True, temperature=0.5,
                               top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)

    print('V136 泵浦数值化 | 6题 | 4轮反射 | 泵浦=对/错+正确数字', flush=True)
    correct_first, correct_last = 0, 0
    for qi, (q, gold, typ) in enumerate(Q):
        prompt = q
        first_ok = last_ok = False
        for r in range(N_ROUNDS):
            ans = gen(prompt, maxn=15)
            num = parse_num(ans)
            ok = (num == gold)
            if r == 0: first_ok = ok
            last_ok = ok
            # 泵浦: 直接给可运算反馈(数字)
            if ok:
                prompt = q + '\n正确！答案是%d。\n再答一次(只给数字)：' % gold
            else:
                prompt = q + '\n错误，正确是%d。\n重新答(只给数字)：' % gold
        correct_first += first_ok; correct_last += last_ok
        print('[%s/%s] %s... 首轮=%s 末轮=%s(答案%s)' % (
            typ, '对' if last_ok else '错', q[:20],
            '对' if first_ok else '错', '对' if last_ok else '错', num), flush=True)
    print('\n首轮正确 %d/6 → 末轮正确 %d/6' % (correct_first, correct_last), flush=True)
    print('若末轮>首轮 → 数值泵浦有效, 0.5B能"读数字反馈→改对"', flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
