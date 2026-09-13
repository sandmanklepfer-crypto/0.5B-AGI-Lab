#!/usr/bin/env python3
"""probe_depth.py — 加技能是否增加B深度: v4b vs v4c 三指标
①λ̄活性(大模型0.36>0.5B 0.24, 深度代理) ②有效维 ③生成多样性
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

V4B = "/workspace/backups_a800/distill_mix_v4b"
V4C = "/workspace/backups_a800/distill_v4c"
Q = "你好"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "苹果", "香蕉", "数学", "物理",
            "太阳", "月亮", "星星", "医生", "老师", "汽车", "火车", "电脑", "手机", "音乐"]

def activity(model, tok, q, layer=22, steps=15):
    ids = tok(q, return_tensors="pt")
    gen = ids["input_ids"]
    prev = None
    lam = []
    for _ in range(steps):
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
    return sum(lam)/len(lam), tok.decode(gen[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

def eff_dim(model, tok, layer=22):
    U = []
    for c in CONCEPTS:
        ids = tok(c, return_tensors="pt")
        with torch.inference_mode():
            h = model(**ids, output_hidden_states=True)
        u = h.hidden_states[layer][0].mean(0).float()
        U.append(u / (u.norm() + 1e-12))
    A = torch.stack(U).cpu().numpy()
    U2, S, Vt = np.linalg.svd(A, full_matrices=False)
    p = S[:20] / S[:20].sum()
    H = -(p * np.log(p + 1e-12)).sum()
    return np.exp(H)

if __name__ == "__main__":
    print("=== 加技能是否增加B深度 (v4b vs v4c, 后者+模板修复技能) ===")
    for name, path in [("v4b", V4B), ("v4c", V4C)]:
        tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
        m = AutoModelForCausalLM.from_pretrained(path)
        m.eval()
        lam, out = activity(m, tok, Q)
        ed = eff_dim(m, tok)
        diversity = len(set(out)) / max(len(out), 1)
        print(f"{name}: λ̄活性={lam:.4f} | 有效维={ed:.1f} | 生成多样性={diversity:.3f}")
        print(f"  生成: {out[:40]!r}")
        del m
