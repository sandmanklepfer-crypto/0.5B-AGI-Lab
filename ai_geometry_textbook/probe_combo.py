#!/usr/bin/env python3
"""probe_combo.py — 探测组合活跃区: 扫描全部层, 找推理/代码双高投影层
两个方向投影都高的层 = 两技能同时活跃 = 组合潜在区
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_REASON = "所有的A都是B，所有的B都是C，那么A是什么？"
Q_CODE = "写一个Python函数计算两个数的和"
NON_Q = "你好"

def all_layer_acts(model, tok, text):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    acts = []
    for li in range(len(h.hidden_states)):
        a = h.hidden_states[li][0].mean(0).float()
        acts.append(a / (a.norm() + 1e-12))
    return acts

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    print("扫描全部层: 推理方向/代码方向投影 (双高=组合潜在区)")
    print("层 | 深度% | 推理投影 | 代码投影 | 双高?")
    a_r = all_layer_acts(m, tok, Q_REASON)
    a_c = all_layer_acts(m, tok, Q_CODE)
    a_n = all_layer_acts(m, tok, NON_Q)
    n_layers = m.config.num_hidden_layers
    for li in range(len(a_r)):
        r_proj = (a_r[li] - a_n[li]).abs().sum().item()
        c_proj = (a_c[li] - a_n[li]).abs().sum().item()
        depth = li / n_layers * 100
        dual = "★双高" if (r_proj > 0.15 and c_proj > 0.15) else ""
        print(f"{li:>3} | {depth:>4.0f}% | {r_proj:.4f} | {c_proj:.4f} | {dual}")
