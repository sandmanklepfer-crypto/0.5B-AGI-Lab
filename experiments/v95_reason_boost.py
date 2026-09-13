#!/usr/bin/env python3
"""
V95 推理通路放大实验 (承接v94对话效果)
变体 (层20分块):
  A 原模型      W = Wk+Wr+Wrest
  B 纯推理      W = Wr+Wrest          (知识块清零, 同v94)
  D 推理增强    W = Wr*1.3 + Wk*0.7 + Wrest   (放大推理通路/压缩知识通路)
  E 推理超增    W = Wr*1.6 + Wk*0.4 + Wrest
判据: greedy生成(去采样噪声) → 4道可判对错难题 (蜗牛/年龄/说谎/盒子)
       看推理通路强弱对解题的影响 + 语句是否保持推理骨架
"""
import copy
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
BLOCKS = '/root/autodl-tmp/life1/v92_blocks.pt'
QS = [
    "一只蜗牛爬井，白天爬3米，晚上滑下2米，井深10米，蜗牛几天能爬出井口？",
    "小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？",
    "一个两位数，个位数字是十位数字的2倍，如果把十位和个位对调，得到的数比原数大36，原来的两位数是多少？",
    "有100个和尚吃100个馒头，大和尚每人吃3个，小和尚每3人吃1个，问大小和尚各几人？",
]

def main():
    torch.manual_seed(0); np.random.seed(0)
    b = torch.load(BLOCKS, map_location='cpu', weights_only=False)
    Lb = b['layer']
    Wk = b['Wk'].float().numpy(); Wr = b['Wr'].float().numpy(); Wrest = b['Wrest'].float().numpy()
    W0 = Wk + Wr + Wrest
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.%d.mlp.down_proj.weight' % Lb
    variants = {
        'A原模型': W0,
        'B纯推理(知识块清零)': (Wr + Wrest),
        'D推理增强(×1.3,知识×0.7)': (Wr*1.3 + Wk*0.7 + Wrest),
        'E推理超增(×1.6,知识×0.4)': (Wr*1.6 + Wk*0.4 + Wrest),
    }
    with torch.inference_mode():
        for vname, Wv in variants.items():
            sd2 = copy.deepcopy(sd); sd2[WN] = torch.tensor(Wv).to(sd[WN].dtype)
            model.load_state_dict(sd2, strict=True)
            print('\n' + '=' * 64, flush=True)
            print('变体: %s' % vname, flush=True)
            print('=' * 64, flush=True)
            for q in QS:
                ids = tok(q, return_tensors='pt').input_ids.to('cuda')
                out = model.generate(ids, max_new_tokens=120, do_sample=False,
                                     repetition_penalty=1.1)
                text = tok.decode(out[0][len(ids[0]):], skip_special_tokens=True).strip()
                # 截到第一个明显跑题标志
                cut = text.split('\n\n')
                print('\n【问】%s\n【答】%s' % (q, cut[0][:300]), flush=True)
    model.load_state_dict(sd, strict=True)

if __name__ == '__main__':
    main()
