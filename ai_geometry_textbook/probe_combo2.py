#!/usr/bin/env python3
"""probe_combo2.py — 定位三段论组合点: 三段论(推理+数学) vs 纯推理 vs 纯数学
组合点 = 推理成分和数学成分【同时活跃】的层(两子技能融合处)
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_SYL = "所有的A都是B，所有的B都是C，那么A是什么？"   # 推理+数学
Q_REA = "如果下雨路会湿，路没湿，今天下雨了吗？"       # 纯推理
Q_MAT = "1+1等于几？"                                # 纯数学
Q_NON = "你好"                                       # 基线

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
    a_syl = all_layer_acts(m, tok, Q_SYL)
    a_rea = all_layer_acts(m, tok, Q_REA)
    a_mat = all_layer_acts(m, tok, Q_MAT)
    a_non = all_layer_acts(m, tok, Q_NON)
    n_layers = m.config.num_hidden_layers
    print("定位三段论组合点 (推理成分/数学成分 同时活跃的层)")
    print("层 | 深度% | 推理成分 | 数学成分 | 组合?")
    for li in range(len(a_syl)):
        rea_c = F.cosine_similarity((a_syl[li]-a_non[li]).unsqueeze(0), (a_rea[li]-a_non[li]).unsqueeze(0)).item()
        mat_c = F.cosine_similarity((a_syl[li]-a_non[li]).unsqueeze(0), (a_mat[li]-a_non[li]).unsqueeze(0)).item()
        depth = li / n_layers * 100
        combo = "★组合点" if (rea_c > 0.5 and mat_c > 0.5) else ("推理为主" if rea_c > 0.5 else ("数学为主" if mat_c > 0.5 else ""))
        print(f"{li:>3} | {depth:>4.0f}% | {rea_c:.3f} | {mat_c:.3f} | {combo}")
