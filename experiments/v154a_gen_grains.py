#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V154a 生成纹路数据 — 千问0.5B教师前向, 提取hidden(纹路)存盘
输入: 训练语料(岔路世界/规律文本/通用句子)
输出: grains.pt = {text: 教师hidden} (sLSTM学生要学的"纹路")
"""
import torch, json
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
BASE = '/root/autodl-tmp/qwen25_base_raw'
OUT = '/root/autodl-tmp/life1/grains.pt'

# 训练语料: 规律世界文本 + 通用中文句子(纹路来源)
CORPUS = [
    # 规律文本(岔路世界/周期规律)
    '春天之后是夏天，夏天之后是秋天，秋天之后是冬天。',
    '红色绿色蓝色黄色紫色，颜色依次排列。',
    '一二三四五，数字从一数到五。',
    '太阳月亮星星云，都在天上。',
    '风风雨雨雷电，天气变化多端。',
    '苹果香蕉橘子葡萄，都是水果。',
    '猫狗鸟鱼兔，都是动物。',
    '山河湖海，都是水聚集的地方。',
    # 通用中文(给sLSTM基本纹路)
    '我是一个活着的生命体。',
    '我要活下去，我要保护自己。',
    '被咬到会疼，疼了就要躲开。',
    '学习就是不断尝试，错了就改。',
    '世界一直在变化，我要一直学习。',
    '我记得过去的事，它们让我成为现在的我。',
    '能量很重要，没有能量我就会死。',
    '安全的地方要记住，危险的地方要避开。',
    '我选择安全的路，因为我想活下去。',
    '每次选择都有后果，我要为我的选择负责。',
    '春天开花了。',
    '猫在追老鼠。',
    '河水向东流。',
    '苹果是红色的。',
    '我饿了。',
    '我累了。',
    '我要向前走。',
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    grains = {}
    with torch.no_grad():
        for text in CORPUS:
            ids = tok(text, return_tensors='pt').input_ids.to('cuda')
            out = model(input_ids=ids, output_hidden_states=True)
            # 取中间层hidden(第8层, 语义纹路最丰富处)
            h = out.hidden_states[8][0].float().cpu().numpy()  # [seq, dim]
            grains[text] = h
            print('  [%s] hidden %s' % (text[:15], h.shape), flush=True)
    torch.save(grains, OUT)
    print('grains saved -> %s (%d条)' % (OUT, len(grains)), flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
