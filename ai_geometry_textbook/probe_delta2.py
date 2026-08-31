#!/usr/bin/env python3
"""probe_delta2.py — 换角度测Δ: 同精度(v4c-v4b) + 公共=残差流(层输入)
修正: ①GGUF量化污染Δ ②公共基底用残差流不是概念均值
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

V4B = "/workspace/backups_a800/distill_mix_v4b"
V4C = "/workspace/backups_a800/distill_v4c"
Q_SYL = "所有的A都是B，所有的B都是C，那么A是什么？"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "苹果", "香蕉", "数学", "物理",
            "太阳", "月亮", "星星", "医生", "老师", "汽车", "火车", "电脑", "手机", "音乐"]

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def resid_direction(model, tok, text, layer):
    """残差流方向: 层输入的mean(模型内部h_in)"""
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    # 层输入 = 上一层的输出 (hidden_states[layer]是第layer层的输出)
    a = h.hidden_states[max(0, layer-1)][0].mean(0).float()
    return a / (a.norm() + 1e-12)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(V4B); tok.pad_token = tok.eos_token
    mb = AutoModelForCausalLM.from_pretrained(V4B)
    mc = AutoModelForCausalLM.from_pretrained(V4C)
    mb.eval(); mc.eval()
    n_layers = mc.config.num_hidden_layers
    print("=== 换角度: Δ2(v4c-v4b, 同精度) vs 残差流/差异 ===")
    print("层 | 深度% | cos(Δ2,残差流) | cos(Δ2,差异) | 判定")
    for li in [4, 8, 12, 16, 20, 22, 23]:
        a_b = act_layer(mb, tok, Q_SYL, li)
        a_c = act_layer(mc, tok, Q_SYL, li)
        d = a_c - a_b; d = d / (d.norm() + 1e-12)
        # 残差流方向 (v4c 层输入)
        r = resid_direction(mc, tok, Q_SYL, li)
        # 差异方向 (v4c 概念中心化)
        acts = torch.stack([act_layer(mc, tok, c, li) for c in CONCEPTS])
        ctr = acts.mean(0)
        diff = acts[0] - ctr; diff = diff / (diff.norm() + 1e-12)
        c_r = F.cosine_similarity(d.unsqueeze(0), r.unsqueeze(0)).item()
        c_d = F.cosine_similarity(d.unsqueeze(0), diff.unsqueeze(0)).item()
        judge = "偏差异" if c_d > 0.3 else ("偏残差流" if c_r > 0.3 else "混合/正交")
        depth = li / n_layers * 100
        print(f"{li:>3} | {depth:>4.0f}% | {c_r:.3f} | {c_d:.3f} | {judge}")
