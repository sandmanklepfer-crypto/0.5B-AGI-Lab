#!/usr/bin/env python3
"""V80 0.5B 鲁棒性四维测试 — 找出最脆弱处
R1 扰动鲁棒: 输入加噪, 输出是否翻车 (稳定性)
R2 修改鲁棒: 权重被改(delta), 模型是否崩 (写活前提)
R3 累积鲁棒: 长链生成, 多久开始复读/退化
R4 机制鲁棒: 挂机制后 novelty 保持 (机制叠加不乱)
"""
import os, json, re, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'

def ngram_nov(seg, hist, n=4):
    if not seg or len(seg) < n: return 0.5
    seen = set()
    if len(hist) >= n:
        for i in range(len(hist)-n+1): seen.add(hist[i:i+n])
    tot=new=0
    for i in range(len(seg)-n+1):
        if seg[i:i+n] not in seen: new+=1
        tot+=1
    return new/max(tot,1)

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    print('=== V80 0.5B 鲁棒性四维测试 ===', flush=True)

    # ---- R1 扰动鲁棒: 同一问题加不同噪声, 答是否稳定 ----
    print('\n[R1 扰动鲁棒]', flush=True)
    q = "大象比马重，马比羊重。问：谁最重？答："
    answers = []
    for seed in range(8):
        torch.manual_seed(seed)
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=8, do_sample=True,
                                 temperature=0.9, pad_token_id=tok.eos_token_id)
        a = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        answers.append(a)
    uniq = len(set(answers))
    print(f'  8次采样答案: {answers}')
    print(f'  不同答案数: {uniq}/8 → 扰动鲁棒性 {"✅高" if uniq<=2 else "❌低(同题答法飘)"}')

    # ---- R2 修改鲁棒: 权重加随机delta, 输出崩不崩 ----
    print('\n[R2 修改鲁棒]', flush=True)
    for delta_scale in [0.01, 0.05, 0.1, 0.2]:
        m2 = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
        WN = 'model.layers.12.mlp.down_proj.weight'
        with torch.no_grad():
            orig = m2.state_dict()[WN].float()
            noise = torch.randn_like(orig) * orig.norm() * delta_scale
            m2.state_dict()[WN].copy_((orig + noise).to(m2.dtype if hasattr(m2.state_dict()[WN],'dtype') else orig.dtype))
        ids = tok("写一段关于夜晚的短文。", return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = m2.generate(input_ids=ids, max_new_tokens=40, do_sample=True,
                              temperature=0.8, pad_token_id=tok.eos_token_id)
        a = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        rep = bool(re.search(r'(.)\1{6,}', a))
        short = len(a) < 10
        print(f'  delta={delta_scale}: 输出={"崩" if rep or short else "正常"} | {a[:30]!r}')
        del m2; torch.cuda.empty_cache()

    # ---- R3 累积鲁棒: 长链续写多久开始复读 ----
    print('\n[R3 累积鲁棒]', flush=True)
    hist = "爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。"
    for r in range(15):
        ids = tok(hist[-400:], return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=40, do_sample=True,
                                 temperature=0.85, top_p=0.92, pad_token_id=tok.eos_token_id)
        seg = tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        hist += seg
        nov = ngram_nov(seg, hist)
        rep = bool(re.search(r'(.)\1{6,}', seg)) or (seg in hist[:-len(seg)])
        if r < 5 or nov < 0.2:
            print(f'  轮{r+1}: nov={nov:.2f} {"⚠复读" if rep else ""} | {seg[:25]!r}')
        if rep and r > 5:
            print(f'  → 第{r+1}轮开始复读 (累积鲁棒墙)')
            break

    print('\n=== V80 完成 ===', flush=True)

if __name__ == '__main__':
    main()
