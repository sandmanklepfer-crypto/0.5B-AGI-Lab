#!/usr/bin/env python3
"""V83 干净持续写活 — 每轮归一化单方向+受控幅度, 长跑不崩?
V81/82 发现: 干净单方向写活鲁棒(泛化不掉)
V83: 持续多轮写活, 每轮沿"新方向"(anti-Hebbian) 归一化小步写
测: 30轮长跑, 每轮novelty/质量/是否绕圈/权重累积
"""
import os, json, re, time, argparse
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
SEED = "爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。"

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
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=30)
    ap.add_argument('--max_new', type=int, default=50)
    ap.add_argument('--scale', type=float, default=0.05, help='每轮写活幅度(受控)')
    ap.add_argument('--anti', type=int, default=1, help='anti-Hebbian: 只沿垂直旧方向写')
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.12.mlp.down_proj.weight'
    W0 = sd[WN].float().clone()
    print(f'[V83] 干净持续写活 30轮 scale={args.scale} anti={args.anti}', flush=True)

    # 已写方向 (anti-Hebbian: 新轮避开旧方向)
    written_dirs = []
    act_buf = {}
    def hook_in(mod, inp, out):
        act_buf['a'] = inp[0][0, -1].float().detach().cpu()
        return out
    h_in = model.model.layers[12].mlp.down_proj.register_forward_hook(hook_in)

    def clean_write(avec):
        """归一化单方向写活: 沿 avec 方向, 幅度精确 scale*|W|"""
        with torch.no_grad():
            W = sd[WN].float()
            d = torch.randn(W.shape[0], device='cuda')
            if args.anti and written_dirs:
                # anti-Hebbian: 去掉已写方向的分量 (全在cuda)
                for wd in written_dirs[-5:]:
                    wd = wd.to('cuda')
                    d = d - (d @ wd) * wd
            d = d / (d.norm() + 1e-9)
            # 归一化 patch (rank-1): d和avec都单位化 → patch.norm()≈1
            patch = torch.outer(d, avec.to('cuda'))
            patch = patch / (patch.norm() + 1e-9) * (W.norm() * args.scale)
            sd[WN].copy_((W + patch).to(torch.bfloat16))
            written_dirs.append(d.cpu())

    hist = SEED
    log = []
    t0 = time.time()
    crash_at = None
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
            rep = bool(re.search(r'(.)\1{6,}', seg)) or (len(seg) > 10 and seg in hist[:-len(seg)])
            # 干净写活 (每轮沿当前输出的激活方向)
            if 'a' in act_buf:
                avec = act_buf['a'].to('cuda')
                avec = avec / (avec.norm() + 1e-9)
                clean_write(avec)
            drift = (sd[WN].float() - W0).norm().item()
            log.append({'r': r+1, 'nov': round(nov,2), 'drift': round(drift,3)})
            if r < 8 or r % 5 == 4 or nov < 0.15:
                flag = "⚠绕圈" if rep else ""
                print(f'  [r{r+1:02d}] nov={nov:.2f} 漂移={drift:.3f} {flag} | {seg[:32]}', flush=True)
            if rep and r > 3:
                crash_at = r+1
                print(f'  → 第{r+1}轮绕圈', flush=True)
                break
    finally:
        h_in.remove()
        json.dump({'rounds': len(log), 'crash_at': crash_at, 'log': log,
                   'final_drift': drift}, open(f'{SAVE}/v83_log.json', 'w'), ensure_ascii=False, indent=1)
        torch.save({'w_delta': (sd[WN].float()-W0).half()}, f'{SAVE}/v83_clean_body.pt')
        print(f'\n[V83 DONE] {len(log)}轮 崩/绕圈于{crash_at} 最终漂移={drift:.3f} | {time.time()-t0:.0f}s', flush=True)

if __name__ == '__main__':
    main()
