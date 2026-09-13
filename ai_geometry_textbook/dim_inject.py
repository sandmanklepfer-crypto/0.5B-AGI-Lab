#!/usr/bin/env python3
"""dim_inject.py — 维度子集级注入: 只打差异维度(概念方差大的维度)
对比整向量注入(8+22有效): 维度级是否更纯(触发推理不带知乎?)
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
LAYERS = [8, 22]
Q = "所有的A都是B，所有的B都是C，那么A是什么？"
NON_Q = "你好"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "苹果", "香蕉", "数学", "物理",
            "太阳", "月亮", "星星", "医生", "老师", "汽车", "火车", "电脑", "手机", "音乐"]

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def diff_mask(model, tok, layer=22, topk=200):
    """差异维度掩码: 概念激活去均值后, 方差最大的 topk 维度"""
    U = []
    for c in CONCEPTS:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        U.append(u / (u.norm() + 1e-12))
    U = torch.stack(U)
    var = U.var(0)  # 每维度方差
    mask = torch.zeros_like(var)
    top = torch.topk(var, topk).indices
    mask[top] = 1.0
    return mask

def gen_dim(model, tok, q, layers, direction, mask, strength, max_new=20):
    state = {"done": False}
    hooks = []
    for layer in layers:
        def hook_out(module, inp, out, layer=layer):
            h = out[0]
            if not state["done"]:
                inj = direction * mask * strength  # 只打差异维度
                if h.dim() == 3:
                    h[:, -1, :] = (h[:, -1, :].float() + inj).to(h.dtype)
                else:
                    h[-1] = (h[-1].float() + inj).to(h.dtype)
            return out
        hooks.append(model.model.layers[layer].self_attn.o_proj.register_forward_hook(hook_out))
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    for h in hooks: h.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    r_dir = act_layer(m, tok, Q, 22) - act_layer(m, tok, NON_Q, 22)
    r_dir = r_dir / (r_dir.norm() + 1e-12)
    print(f"推理方向norm: {r_dir.norm():.4f}")

    print("=== 维度级注入 (层8+22, 只打差异维度) vs 整向量 ===")
    for topk in [50, 200, 500, 896]:
        mask = diff_mask(m, tok, 22, topk)
        print(f"--- top{topk} 维度 ---")
        for s in [2.5, 5.0]:
            a = gen_dim(m, tok, Q, LAYERS, r_dir, mask, s)
            has_reason = ("子集" in a or "所以A也是C" in a or "A是C" in a)
            has_tpl = ("知乎" in a or "请提供" in a or "2008" in a)
            tag = "REASON!" if has_reason else ("TPL" if has_tpl else "   ")
            print(f"  s={s}: {tag} {a[:55]!r}")
