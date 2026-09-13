#!/usr/bin/env python3
"""
V94 分离后"仅推理通路"对话效果测试
基于 v92 分块 (层20: W = W_k(知识特有) + W_r(推理特有) + Wrest(公共))
三个变体:
  A 原模型        = W (对照)
  B 纯推理        = W_r + Wrest  (知识块清零 → 深层知识输出通路关闭)
  C 纯知识        = W_k + Wrest  (推理块清零 → 对照: 应答不了推理难题)
对每个发散/难题: 真实生成对话, 看"仅推理"效果
"""
import copy
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'

QUESTIONS = [
    # 推理难题 (知识少)
    "三个盒子分别贴着苹果、橙子、苹果和橙子混合的标签，但标签全都贴错了，你只能从其中一个盒子里摸出一个水果，怎样判断三个盒子里各装了什么？",
    "一只蜗牛爬井，白天爬3米，晚上滑下2米，井深10米，蜗牛几天能爬出井口？",
    "甲说乙在说谎，乙说甲在说谎，到底谁说真话？",
    "小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？",
    # 发散问题 (无标准答案, 需自己组织)
    "如果有一天全世界所有的钟表都突然倒着走，会发生什么？",
    "假如人类突然集体失去记忆，但还记得怎么说话走路，世界会怎样？",
]

def main():
    torch.manual_seed(42)
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Lb = b['layer']
    Wk = b['Wk'].float().numpy()
    Wr = b['Wr'].float().numpy()
    Wrest = b['Wrest'].float().numpy()
    W0 = Wk + Wr + Wrest
    print('[V94] 分离后对话测试 | 层%d分块: 知识块清零=纯推理' % Lb, flush=True)

    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.%d.mlp.down_proj.weight' % Lb

    variants = {
        'A原模型': W0,
        'B纯推理(知识块清零)': (Wr + Wrest),
        'C纯知识(推理块清零)': (Wk + Wrest),
    }

    gen_kw = dict(max_new_tokens=160, do_sample=True, temperature=0.85,
                  top_p=0.9, repetition_penalty=1.15)

    with torch.inference_mode():
        for vname, Wv in variants.items():
            sd2 = copy.deepcopy(sd)
            sd2[WN] = torch.tensor(Wv).to(sd[WN].dtype)
            model.load_state_dict(sd2, strict=True)
            print('\n' + '=' * 70, flush=True)
            print('变体: %s' % vname, flush=True)
            print('=' * 70, flush=True)
            for q in QUESTIONS:
                ids = tok(q, return_tensors='pt').input_ids.to('cuda')
                out = model.generate(ids, **gen_kw)
                text = tok.decode(out[0][len(ids[0]):], skip_special_tokens=True)
                print('\n【问】%s' % q, flush=True)
                print('【答】%s' % text.strip(), flush=True)
    model.load_state_dict(sd, strict=True)

if __name__ == '__main__':
    main()
