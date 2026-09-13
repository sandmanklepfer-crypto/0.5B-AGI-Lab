#!/usr/bin/env python3
"""sphere_centered.py — 中心化球面分布 (去公共基底后的概念真形状)
R_raw: 含公共基底 | R_centered: 去均值后(概念差异方向的分布)
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "老虎", "苹果", "香蕉", "数学", "物理", "化学",
            "太阳", "月亮", "星星", "医生", "老师", "学生", "汽车", "火车", "飞机", "米饭", "面条",
            "电脑", "手机", "音乐", "电影", "足球", "游泳", "跑步", "北京", "上海", "广州", "战争",
            "和平", "经济", "历史", "科技", "艺术", "睡眠", "吃饭", "旅行", "学习", "工作", "爱情",
            "友谊", "春天", "冬天", "量子", "基因"]
L = 22

def collect(model, tok, concepts, layer=L):
    U = []
    for c in concepts:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        U.append(u / (u.norm() + 1e-12))
    return torch.stack(U)  # [N, 896] 归一化

def sphere_both(U):
    """R_raw(含公共基底) vs R_centered(去均值) + 公共基底占比"""
    N = U.shape[0]
    R_raw = (U.sum(0).norm() / N).item()
    mean_u = U.mean(0)                      # 公共基底
    common_ratio = (mean_u.norm()).item()   # 公共基底长度
    Uc = U - mean_u                          # 中心化
    Uc = Uc / (Uc.norm(dim=1, keepdim=True) + 1e-12)
    R_centered = (Uc.sum(0).norm() / N).item()
    C = (Uc @ Uc.T).abs()
    mask = ~torch.eye(N, dtype=torch.bool)
    mc = C[mask].numpy().mean()
    return R_raw, R_centered, common_ratio, mc

MODELS = [("v4b", "/workspace/backups_a800/distill_mix_v4b"),
          ("v4c", "/workspace/backups_a800/distill_v4c"),
          ("calc_v1", "/workspace/backups_a800/distill_calc_v1")]

if __name__ == "__main__":
    print("=== 中心化球面分布 (50概念, 层22) ===")
    for name, path in MODELS:
        try:
            tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
            m = AutoModelForCausalLM.from_pretrained(path)
            m.eval()
            U = collect(m, tok, CONCEPTS)
            R_raw, R_cen, com, mc = sphere_both(U)
            print(f"  {name}: R_raw={R_raw:.4f} → R_center={R_cen:.4f} | 公共基底={com:.4f} | 中心化两两cos={mc:.4f}")
            del m
        except Exception as e:
            print(f"  {name}: ERR {str(e)[:60]}")
