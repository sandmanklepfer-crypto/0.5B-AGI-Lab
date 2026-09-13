#!/usr/bin/env python3
"""V81 权重修改鲁棒性精细扫描 — 改多少崩? 哪种改法不崩?
测: 对 layer12.down_proj 加不同幅度/不同形式的修改
  1 全量加噪 (V80测过, 微改就乱码)
  2 低秩修改 (rank-k: 更"结构化"的改)
  3 只改单行/单方向 (更温和)
  4 anti-Hebbian 式修改 (垂直主方向)
找: 哪种改法在较大幅度下仍不崩 → 写活的正确姿势
"""
import os, re, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'

def gen_text(model, tok, prompt="写一段关于夜晚的短文。", n=35):
    ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
    with torch.inference_mode():
        out = model.generate(input_ids=ids, max_new_tokens=n, do_sample=True,
                             temperature=0.8, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

def quality(a):
    """输出质量: 乱码/重复检测"""
    if len(a) < 8: return 0.0
    cn = sum(1 for c in a if '\u4e00' <= c <= '\u9fff')
    ratio = cn / max(len(a), 1)
    rep = bool(re.search(r'(.)\1{5,}', a))
    if rep: ratio *= 0.3
    return ratio

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    print("=== V81 权重修改鲁棒性扫描 ===", flush=True)
    # 基线
    m0 = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
    base_q = quality(gen_text(m0, tok))
    print(f"基线质量: {base_q:.2f}", flush=True)
    del m0; torch.cuda.empty_cache()

    WN = 'model.layers.12.mlp.down_proj.weight'
    methods = {
        '全量加噪': lambda W, s: W + torch.randn_like(W)*W.norm()*s,
        '低秩r8':   lambda W, s: W + (torch.randn(W.shape[0],8,device=W.device)@torch.randn(8,W.shape[1],device=W.device))*W.norm()*s*0.3,
        '垂直补丁': lambda W, s: W + torch.outer(torch.randn(W.shape[0],device=W.device), torch.randn(W.shape[1],device=W.device))*W.norm()*s*0.3,
    }
    scales = [0.01, 0.03, 0.05, 0.1, 0.2]
    for name, fn in methods.items():
        print(f"\n--- {name} ---", flush=True)
        for s in scales:
            m = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
            with torch.no_grad():
                W = m.state_dict()[WN].float()
                m.state_dict()[WN].copy_((fn(W, s)).to(torch.bfloat16))
            q = quality(gen_text(m, tok))
            ok = "✅" if q > base_q*0.6 else "❌"
            print(f"  幅度{s:.2f}: 质量{q:.2f} {ok}", flush=True)
            del m; torch.cuda.empty_cache()

    # 最优法再精细扫 (找写活安全幅度)
    print("\n--- 写活安全幅度: 用垂直补丁法(最温和) 扫更细 ---", flush=True)
    for s in [0.02, 0.04, 0.06, 0.08, 0.12]:
        m = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
        with torch.no_grad():
            W = m.state_dict()[WN].float()
            patch = torch.outer(torch.randn(W.shape[0],device='cuda'), torch.randn(W.shape[1],device='cuda'))
            patch = patch / patch.norm() * W.norm() * s
            m.state_dict()[WN].copy_((W + patch).to(torch.bfloat16))
        q = quality(gen_text(m, tok))
        ok = "✅" if q > base_q*0.6 else "❌"
        print(f"  幅度{s:.3f}: 质量{q:.2f} {ok}", flush=True)
        del m; torch.cuda.empty_cache()
    print("\n=== V81 DONE ===", flush=True)

if __name__ == '__main__':
    main()
