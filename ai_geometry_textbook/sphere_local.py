#!/usr/bin/env python3
"""sphere_local.py — 激活球面分布测量 (本地 CPU, 4个0.5B模型)
R统计量: 方向集中度 (0=均匀球面, 1=全部同向)
用法: python3 sphere_local.py
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

def sphere_stats(model, tok, concepts, layer=L):
    U = []
    for c in concepts:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        u = u / (u.norm() + 1e-12)
        U.append(u)
    U = torch.stack(U)
    N = len(U)
    R = (U.sum(0).norm() / N).item()
    C = (U @ U.T).abs()
    mask = ~torch.eye(N, dtype=torch.bool)
    C_nodiag = C[mask].numpy()
    mean_c, std_c = C_nodiag.mean(), C_nodiag.std()
    U2, S, V = torch.pca_lowrank(U, q=5)
    s1 = (S[0]**2 / (S**2).sum()).item()
    return R, mean_c, std_c, s1

MODELS = [("v3(旧蒸馏)", "/workspace/backups_a800/distill_mix_v3"),
          ("v4b(平衡)", "/workspace/backups_a800/distill_mix_v4b"),
          ("v4c(修复)", "/workspace/backups_a800/distill_v4c"),
          ("calc_v1(数学)", "/workspace/backups_a800/distill_calc_v1")]

if __name__ == "__main__":
    print("=== 激活球面分布 (50概念, 层22, 本地CPU) ===")
    for name, path in MODELS:
        try:
            tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
            m = AutoModelForCausalLM.from_pretrained(path)
            m.eval()
            R, mc, sc, s1 = sphere_stats(m, tok, CONCEPTS)
            print(f"  {name}: R={R:.4f} 两两cos均值={mc:.4f} 标准差={sc:.4f} 主方向占比={s1:.3f}")
            del m
        except Exception as e:
            print(f"  {name}: ERR {str(e)[:60]}")
