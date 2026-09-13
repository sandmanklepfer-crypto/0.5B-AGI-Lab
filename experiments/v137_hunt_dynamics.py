#!/usr/bin/env python3
# V137 捕猎失败底层诊断: 0.5B消化13B知识时, 状态到底发生了什么
# 测3个候选机制:
#  A. 容量挤压: 13B知识(长/密集)注入 → 0.5B上下文超载 → 激活饱和/平均化 → 只能抓1个词
#  B. 无内化锚: 消化时慢S没参与(纯文本续写) → 新知识与"我"无关 → 过耳即忘
#  C. 重建缺原料: 0.5B词表里没有曲率概念簇 → 不是记不住, 是没东西可重建
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
KNOW = ('黎曼度量是流形上每点内积的平滑选择，它定义了点之间的无穷小距离。'
        '曲率(里奇曲率/截面曲率)描述空间如何弯曲，是度量二阶导数的组合，'
        '在广义相对论中，物质告诉时空如何弯曲(爱因斯坦场方程 G=8πT)。')
# 控制: 同样长度的日常文本
DAILY = ('今天早上我起床后先喝了一杯温水，然后去阳台看了看花，'
         '花盆里的月季开了两朵红的，我浇了水又回屋做了早饭，'
         '煎了两个蛋，吃完就出门上班了，路上买了杯豆浆。')

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    def probe(text, label):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model(input_ids=ids, output_hidden_states=True)
        hs = out.hidden_states
        print('--- %s ---' % label, flush=True)
        # 逐层激活范数/饱和度
        for L in [0, 6, 12, 18, 23]:
            h = hs[L+1][0]  # (seq, 896)
            norms = h.norm(dim=-1)
            # 末token前的平均激活(看有没有被知识撑爆/饱和)
            act = torch.tanh(h).abs().mean().item()
            print('  层%2d: 激活均值=%.3f 末token范数=%.2f' % (L, act, norms[-1].item()), flush=True)
        # 末token 熵(看"下一步"确定度: 知识后应该低=有明确指向)
        with torch.no_grad():
            lg = model(input_ids=ids).logits[0, -1]
        p = torch.softmax(lg, -1)
        ent = -(p * torch.log(p + 1e-9)).sum().item()
        print('  末token词表熵=%.1f (低=确定/高=迷茫)' % ent, flush=True)
        # 层间残差流: 知识 vs 日常 的差异幅度
        return hs

    hk = probe(KNOW, '黎曼知识(猎来的)')
    hd = probe(DAILY, '日常文本(对照)')
    # 对比: 两层文本在深层是否同样被"平滑吸收"(残差方向差异)
    print('\n=== 深层激活差异(知识vs日常) ===', flush=True)
    for L in [12, 20, 23]:
        diff = (hk[L+1][0, -1] - hd[L+1][0, -1]).norm().item()
        print('  层%d 末token激活差=%.2f (大=知识确实产生不同状态)' % (L, diff), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
