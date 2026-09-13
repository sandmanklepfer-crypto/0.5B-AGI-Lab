#!/usr/bin/env python3
"""
V102b 权重幂次滚动 — 稳定版
用 hook 替换滚动层 MLP.forward: 每 token 前向时, 该层 MLP 内部自动滚 R 次
(状态过 MLP -> 结果再过同一 MLP, R 次组织 = 权重幂次展开近似)
其余全部走 transformers 原生 generate, 不做任何手动解码
"""
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
ROLL_LAYER = 20
ROLLS = [1, 3, 6]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    mlp = model.model.layers[ROLL_LAYER].mlp
    print('[V102b] 权重幂次滚动(hook稳定版) | 层%d 滚次=%s' % (ROLL_LAYER, ROLLS), flush=True)

    orig_fwd = mlp.forward
    cur_rolls = 1

    def rolling_forward(x):
        h = orig_fwd(x)
        if cur_rolls <= 1:
            return h
        gw = mlp.gate_proj.weight
        uw = mlp.up_proj.weight
        dw = mlp.down_proj.weight
        acc = h
        for _ in range(cur_rolls - 1):
            m = F.silu(F.linear(h, gw)) * F.linear(h, uw)
            acc = acc + F.linear(m, dw)
            h = acc
        return acc
    mlp.forward = rolling_forward

    TASKS = [
        ("三色球跟踪",
         "盒子里开始有1个红球。第一次放入2个蓝球。第二次拿走1个红球放入3个绿球。第三次拿走2个蓝球放入1个红球。现在盒子里红球、蓝球、绿球各多少个？"),
        ("人物关系",
         "老王的儿子是小李，小李的妻子是小张，小张的弟弟是小赵。问：小张和老王是什么关系？"),
        ("排队位置",
         "甲乙丙丁戊五人排队。甲在乙左边，丙在甲左边，丁在戊右边，戊在乙右边。问：谁站在最中间？"),
    ]

    with torch.inference_mode():
        for title, q in TASKS:
            print('\n' + '='*60, flush=True)
            print('【%s】%s' % (title, q[:60]), flush=True)
            for r in ROLLS:
                cur_rolls = r
                try:
                    ids = tok(q, return_tensors='pt').input_ids.to('cuda')
                    o = model.generate(ids, max_new_tokens=80, do_sample=False,
                                       repetition_penalty=1.2, pad_token_id=tok.eos_token_id)
                    ans = tok.decode(o[0][len(ids[0]):], skip_special_tokens=True).strip()
                    print('  滚%d次: %s' % (r, ans[:250]), flush=True)
                except Exception as e:
                    import traceback
                    print('  滚%d次 出错: %s' % (r, str(e)[:200]), flush=True)
                    traceback.print_exc()
    mlp.forward = orig_fwd
    print('\n[V102b] 完成', flush=True)

if __name__ == '__main__':
    main()
