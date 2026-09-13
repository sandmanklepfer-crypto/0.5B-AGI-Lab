#!/usr/bin/env python3
"""geodesic_py.py — 推理时测地线激活注入 (复刻 geodesic_inject.c 思想)
生成时每 K 步: 读层22激活 -> 修正方向投影到切空间 -> 小步注入激活
修正方向 d = norm(v4c激活 - v5b激活) (正确-错误)
用法: geodesic_py.py [--alpha A] [--K N] [--max-new N]
"""
import sys, argparse
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

GOOD = '/root/distill_v4c'
MIX = '/root/distill_v5b_s3'
S_LAYER = 22

FIX_DIRS = {
    "100减37等于多少？": "restore",
    "7乘以8等于多少？": "restore",
    "图灵在1950年发表的著名论文叫什么名字？": "restore",
    "请提供一份关于2008年美国金融危机的简要概述。": "repel",
}

def act_pool(model, tok, text, layer):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    return h.hidden_states[layer][0].mean(0).float()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alpha", type=float, default=3.0)
    ap.add_argument("--K", type=int, default=2, help="每 K 步注入一次")
    ap.add_argument("--max-new", type=int, default=80)
    ap.add_argument("--query", default="100减37等于多少？")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MIX); tok.pad_token = tok.eos_token
    good = AutoModelForCausalLM.from_pretrained(GOOD, dtype=torch.bfloat16).to("cuda:0")
    mix = AutoModelForCausalLM.from_pretrained(MIX, dtype=torch.bfloat16).to("cuda:0")
    good.eval(); mix.eval()

    # 预计算修正方向
    dirs = {}
    for q, mode in FIX_DIRS.items():
        with torch.inference_mode():
            d = act_pool(good, tok, q, S_LAYER) - act_pool(mix, tok, q, S_LAYER)
        d = d / (d.norm() + 1e-12)
        if mode == "repel":
            d = -d
        dirs[q] = d
    print(f"[dirs] {len(dirs)} directions", flush=True)

    # 注入 hook: 层 S_LAYER 输出激活
    injected = {"cnt": 0}
    def make_hook(d):
        def hook_fn(module, inp, out):
            if injected["cnt"] % args.K == 0:
                h = out[0]  # [B, L, H] 或 [B*L, H]
                if h.dim() == 2:
                    a_last = h[-1]  # 最后一行 = 最后位置
                else:
                    a_last = h[:, -1, :]
                a_n = a_last / (a_last.norm(dim=-1, keepdim=True) + 1e-12)
                a_n = a_n.float()
                d_tan = d - (d @ a_n[0] if a_n.dim() == 2 else d @ a_n) * (a_n[0] if a_n.dim() == 2 else a_n)
                d_tan = d_tan / (d_tan.norm() + 1e-12)
                out0 = h.clone()
                if out0.dim() == 2:
                    out0[-1] = out0[-1] + args.alpha * d_tan
                else:
                    out0[:, -1, :] = out0[:, -1, :] + args.alpha * d_tan
                return out0
            return out
        return hook_fn

    q = args.query
    d = dirs.get(q)
    if d is None:
        d = act_pool(good, tok, q, S_LAYER) - act_pool(mix, tok, q, S_LAYER)
        d = d / (d.norm() + 1e-12)
    h = mix.model.layers[S_LAYER].self_attn.o_proj.register_forward_hook(make_hook(d))

    print(f"=== {q} (alpha={args.alpha}, K={args.K}) ===", flush=True)
    ids = tok(q, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = mix.generate(**ids, max_new_tokens=args.max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    a = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    print(f"A: {a[:200]}", flush=True)
    h.remove()

if __name__ == "__main__":
    main()
