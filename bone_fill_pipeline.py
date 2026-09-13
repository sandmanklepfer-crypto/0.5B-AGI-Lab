#!/usr/bin/env python3
"""扩散骨架 + 自回归填充 管线 + 几何分析
骨架生成器: 0.5B bridge (distill_05b_bridge, 粗->精行为)
填充器: 3B 精化版 (distill_3b_refine)
几何: 骨架激活 vs 填充增量方向 (0.5B时代 Δ 分析同款)
输出: /root/bone_fill_results.txt + 激活 dump /root/acts_bonefill/
"""
import json, sys, torch, os, struct
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

SKELETON = '/root/autodl-tmp/distill_05b_bridge'   # 0.5B bridge (骨架)
FILLER = '/root/autodl-tmp/distill_3b_refine'      # 3B 精化 (填充)
OUT = '/root/bone_fill_results.txt'

PROMPTS = [
    "7 × 8 等于多少？",
    "2 的 10 次方等于多少？",
    "一个数的 3 倍加 5 等于 20，这个数是多少？",
    "为什么天空是蓝色的？",
    "什么是黑洞？",
    "什么是递归？",
    "机器学习和传统编程的区别？",
    "为什么铁会生锈？",
    "解释一下什么是复利。",
    "地球为什么有四季？",
    "什么是过拟合？",
    "如何提高睡眠质量？",
    "什么是质数？",
    "解释一下什么是生态位。",
    "为什么海水是咸的？",
]

def gen(tok, model, text, max_new, sample=False):
    ids = tok(text, return_tensors='pt').to(model.device)
    with torch.inference_mode():
        if sample:
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=True,
                                 temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
        else:
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()

def extract_skeleton(text):
    """从 bridge 输出中提取 <|draft|> 骨架段 (粗->精格式)"""
    if '<|draft|>' in text:
        seg = text.split('<|draft|>')[-1]
        if '<|refine|>' in seg:
            return seg.split('<|refine|>')[0].strip()
    return None

@torch.inference_mode()
def get_act(model, tok, text, layer):
    ids = tok(text, return_tensors='pt').to(model.device)
    h = model(**ids, output_hidden_states=True).hidden_states[layer]
    return h[0].mean(0)  # (d)

def main():
    tok_f = AutoTokenizer.from_pretrained(FILLER, trust_remote_code=True)
    fl = AutoModelForCausalLM.from_pretrained(FILLER, trust_remote_code=True,
                                              torch_dtype=torch.bfloat16).cuda().eval()
    n_layers = fl.config.num_hidden_layers
    layer_geom = n_layers - 2  # 深层

    skel_map = {}
    for line in open('/root/skeletons.jsonl', encoding='utf-8'):
        r = json.loads(line)
        skel_map[r['prompt']] = r['skeleton']

    results = []
    cos_list = []
    for p in PROMPTS:
        skeleton = skel_map.get(p, '')
        # 1. 直接生成 (3B 精化) vs 2. 骨架+填充
        direct = gen(tok_f, fl, p, 250, sample=True)
        filled = gen(tok_f, fl, f"{p}\n以下是回答骨架：{skeleton}\n请把骨架扩写成完整回答：", 250, sample=True)
        # 3. 几何: 骨架激活 vs 直接/填充激活 (3B 深层)
        try:
            a_skel = get_act(fl, tok_f, skeleton, layer_geom)
            a_dir = get_act(fl, tok_f, direct, layer_geom)
            a_fill = get_act(fl, tok_f, filled, layer_geom)
            delta = a_fill - a_skel
            cos_skel_fill = F.cosine_similarity(a_skel, a_fill, dim=-1).item()
            cos_skel_delta = F.cosine_similarity(a_skel, delta, dim=-1).item()
            cos_dir_fill = F.cosine_similarity(a_dir, a_fill, dim=-1).item()
            cos_list.append((cos_skel_fill, cos_skel_delta, cos_dir_fill))
            geom = f"cos(骨架,填充)={cos_skel_fill:.3f} cos(骨架,Δ)={cos_skel_delta:+.3f} cos(直接,填充)={cos_dir_fill:.3f}"
        except Exception as e:
            geom = f"geom ERR {e}"
        results.append({'prompt': p, 'skeleton': skeleton[:120], 'direct': direct[:150],
                        'filled': filled[:150], 'geom': geom})
        print(f'=== {p[:22]} ===\n  骨架: {skeleton[:80]}\n  直接: {direct[:80]}\n  填充: {filled[:80]}\n  {geom}', flush=True)
    # 汇总
    if cos_list:
        import numpy as np
        c = np.array(cos_list)
        print(f'\n[几何汇总] cos(骨架,填充)均值={c[:,0].mean():.3f}  cos(骨架,Δ)均值={c[:,1].mean():+.3f}  cos(直接,填充)均值={c[:,2].mean():.3f}', flush=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print('BONE_FILL_DONE', flush=True)

if __name__ == '__main__':
    main()
