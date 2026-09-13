#!/usr/bin/env python3
"""V75 写活循环网络 — 循环架构 × 权重写活 (GPT-6循环方向 × 我们的写活)
架构: h_t = f(W_t, h_{t-1}, x_t)  循环传递状态
      W_{t+1} = W_t + ε·antiHebbian(h_t历史)  权重随循环演化(二阶慢变)
载体: 0.5B (qwen25_base_raw), 用 antiheb 写活delta 起步
测: 循环多轮生成, 看 状态推进 + 权重演化 是否持续不崩
"""
import os, json, re, time, argparse
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
SEED = '爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'

def ngram_nov(seg, hist, n=4):
    if not seg or len(seg) < n:
        return 0.5
    seen = set()
    if len(hist) >= n:
        for i in range(len(hist) - n + 1):
            seen.add(hist[i:i+n])
    tot = new = 0
    for i in range(len(seg) - n + 1):
        if seg[i:i+n] not in seen:
            new += 1
        tot += 1
    return new / max(tot, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=10)
    ap.add_argument('--max_new', type=int, default=56)
    ap.add_argument('--eta_w', type=float, default=0.04)
    ap.add_argument('--beta', type=float, default=0.3)
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.12.mlp.down_proj.weight'
    W0 = sd[WN].float().clone()
    print(f'[V75] 写活循环 起始|W|={W0.norm().item():.1f}', flush=True)

    # 循环状态: h_state (跨轮的时间状态)
    h_state = None
    act_buf = {}

    # 捕获 down_proj 输入 (用于写活)
    def hook_in(mod, inp, out):
        act_buf['a'] = inp[0][0, -1].float().detach().cpu()
        return out
    h_in = model.model.layers[12].mlp.down_proj.register_forward_hook(hook_in)

    # 循环注入: 把上轮状态作为方向加回输入 (时间状态传递)
    def make_loop():
        def hook(mod, inp, out):
            h = out[0]
            if h_state is not None:
                hs = h_state.to(h.dtype)
                h = h + 0.4 * hs.unsqueeze(0)
            return (h,) if isinstance(out, tuple) else h
        return hook
    h_loop = model.model.layers[6].register_forward_hook(make_loop())

    def clean_v(hist):
        with torch.inference_mode():
            enc = tok(hist[-300:], return_tensors='pt').to('cuda')
            h = model(**enc, output_hidden_states=True).hidden_states[13][0, -1].float()
        return h / (h.norm() + 1e-12)

    hist = SEED
    total_w = 0.0
    t0 = time.time()
    try:
        for r in range(args.rounds):
            enc = tok(hist[-400:], return_tensors='pt').to('cuda')
            with torch.inference_mode():
                out = model.generate(input_ids=enc.input_ids, attention_mask=enc.attention_mask,
                                     max_new_tokens=args.max_new, do_sample=True, temperature=0.85,
                                     top_p=0.92, pad_token_id=tok.eos_token_id)
            seg = tok.decode(out[0][enc.input_ids.shape[1]:], skip_special_tokens=True).strip()
            hist = hist + seg
            nov = ngram_nov(seg, hist)
            # 循环状态: 从本轮输出取末状态 (时间状态跨轮)
            v = clean_v(hist).to('cuda')
            h_state = v if h_state is None else (1 - args.beta) * h_state + args.beta * v
            # 权重写活 (anti-Hebbian): 只写垂直h_state的新方向
            if 'a' in act_buf:
                svec = h_state / (h_state.norm() + 1e-12)
                d = v - (v @ svec) * svec
                if d.norm() > 0.05:
                    avec = act_buf['a'].to('cuda'); avec = avec / (avec.norm() + 1e-12)
                    with torch.no_grad():
                        sd[WN].add_((args.eta_w * torch.outer((d / d.norm()).float(), avec.float())).to(sd[WN].dtype))
            cur_w = (sd[WN].float() - W0).norm().item()
            total_w += cur_w
            crash = bool(re.search(r'(.)\1{7,}', seg[-15:]))
            print(f'  [r{r+1:02d}] |ΔW|={cur_w:.3f} nov={nov:.2f} | {seg[:40]}', flush=True)
            if crash:
                print(f'  ⚠ 崩于{r+1}', flush=True)
                break
    finally:
        h_in.remove(); h_loop.remove()
        torch.save({'w_delta': (sd[WN].float() - W0).half(), 'rounds': r + 1,
                    'total_w': total_w}, f'{SAVE}/v75_recurrent_body.pt')
        open(f'{SAVE}/v75_flow.txt', 'w', encoding='utf-8').write(hist)
        print(f'\n[V75] {r+1}轮完成 累计写活={total_w:.3f} 存 v75_recurrent_body.pt | {time.time()-t0:.0f}s', flush=True)

if __name__ == '__main__':
    main()
