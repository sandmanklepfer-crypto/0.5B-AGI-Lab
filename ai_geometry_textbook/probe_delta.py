#!/usr/bin/env python3
"""probe_delta.py — Δ(注入重定向)的空间成分: 偏公共基底(99%)还是差异通道(1%)
决定: 重定向是"只动差异"(可随意加技能)还是"动全局"(技能多几何崩)
"""
import torch, torch.nn.functional as F
import numpy as np, struct, glob
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_mix_v4b"
Q_SYL = "所有的A都是B，所有的B都是C，那么A是什么？"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "苹果", "香蕉", "数学", "物理",
            "太阳", "月亮", "星星", "医生", "老师", "汽车", "火车", "电脑", "手机", "音乐"]

def load_base_layer(file_idx, layer=22, n_embd=896):
    files = sorted(glob.glob("/tmp/base_act_L*.bin"))
    data = open(files[file_idx], "rb").read()
    nl, ne = struct.unpack_from("<ii", data, 0)
    arr = np.frombuffer(data, dtype=np.float32, count=nl*ne, offset=8).reshape(nl, ne)
    return arr[layer]

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    n_layers = m.config.num_hidden_layers
    print("=== Δ(重定向)的空间成分: 偏公共基底(99%)还是差异通道(1%)? ===")
    print("层 | 深度% | cos(Δ,公共) | cos(Δ,差异) | 判定")
    for li in [4, 8, 12, 16, 20, 22, 23]:
        # v4b 激活
        a_v = act_layer(m, tok, Q_SYL, li)
        # 基座激活 (dump_layers 层顺序: 0=embed? 1..24 对应模型层)
        base = torch.tensor(load_base_layer(0, layer=li+1 if li < 23 else 23)).float()
        base = base / (base.norm() + 1e-12)
        d = a_v - base  # Δ(重定向)
        d = d / (d.norm() + 1e-12)
        # 公共基底方向 (v4b 概念激活均值)
        acts = torch.stack([act_layer(m, tok, c, li) for c in CONCEPTS])
        pub = acts.mean(0); pub = pub / (pub.norm() + 1e-12)
        # 差异方向 (中心化后的一个代表方向)
        ctr = acts.mean(0)
        diff = acts[0] - ctr; diff = diff / (diff.norm() + 1e-12)
        c_pub = F.cosine_similarity(d.unsqueeze(0), pub.unsqueeze(0)).item()
        c_dif = F.cosine_similarity(d.unsqueeze(0), diff.unsqueeze(0)).item()
        judge = "★偏差异(可加技能)" if c_dif > 0.5 else ("偏公共(动基础)" if c_pub > 0.5 else "混合")
        depth = li / n_layers * 100
        print(f"{li:>3} | {depth:>4.0f}% | {c_pub:.3f} | {c_dif:.3f} | {judge}")
