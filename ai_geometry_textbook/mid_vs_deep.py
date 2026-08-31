#!/usr/bin/env python3
"""mid_vs_deep.py — 中间层 vs 深层测量 (v4c, 层8/12/16/20/22)
每层测: ①概念差异占比(中心化R/公共基底) ②生成活性(相邻步λ̄)
问题: 中间层(8/12/16)和深层(20/22)的差异/活性是否不同?
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "老虎", "苹果", "香蕉", "数学", "物理", "化学",
            "太阳", "月亮", "星星", "医生", "老师", "学生", "汽车", "火车", "飞机", "米饭", "面条",
            "电脑", "手机", "音乐", "电影", "足球", "游泳", "跑步", "北京", "上海", "广州", "战争",
            "和平", "经济", "历史", "科技", "艺术", "睡眠", "吃饭", "旅行", "学习", "工作", "爱情",
            "友谊", "春天", "冬天", "量子", "基因"]
LAYERS = [8, 12, 16, 20, 22]
Q = "你好"

def layer_stats(model, tok, layer):
    # 概念差异: 中心化 R + 公共基底占比
    U = []
    for c in CONCEPTS:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        U.append(u / (u.norm() + 1e-12))
    U = torch.stack(U)
    N = U.shape[0]
    R_raw = (U.sum(0).norm() / N).item()
    mean_u = U.mean(0)
    common = mean_u.norm().item()
    Uc = U - mean_u
    Uc = Uc / (Uc.norm(dim=1, keepdim=True) + 1e-12)
    R_cen = (Uc.sum(0).norm() / N).item()
    # 生成活性: 生成10步, 相邻步激活变化率
    ids = tok(Q, return_tensors="pt")
    gen = ids["input_ids"]
    prev = None
    lam = []
    for _ in range(10):
        with torch.inference_mode():
            lg = model(gen).logits[:, -1]
        nxt = torch.argmax(lg, dim=-1).unsqueeze(0)
        gen = torch.cat([gen, nxt], dim=1)
        with torch.inference_mode():
            h = model(gen, output_hidden_states=True)
        a = h.hidden_states[layer][0, -1].float()
        a = a / (a.norm() + 1e-12)
        if prev is not None:
            lam.append(1 - F.cosine_similarity(prev.unsqueeze(0), a.unsqueeze(0)).item())
        prev = a
    return R_raw, R_cen, common, sum(lam)/len(lam)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    print("=== 中间层 vs 深层 (v4c) ===")
    print("层 | 深度% | R_raw(公共) | R_center(差异) | 公共基底 | 活性λ̄")
    for layer in LAYERS:
        R_raw, R_cen, common, lam = layer_stats(m, tok, layer)
        depth = layer / m.config.num_hidden_layers * 100
        print(f"{layer:>3} | {depth:>5.0f}% | {R_raw:.4f} | {R_cen:.4f} | {common:.4f} | {lam:.4f}")
