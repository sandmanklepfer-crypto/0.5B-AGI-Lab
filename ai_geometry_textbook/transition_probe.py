#!/usr/bin/env python3
"""transition_probe.py — 过渡过程显微镜: v4c 长生成逐点 λ̄ + 断裂处放大
观察: 正常→失败(模板/重复)的过渡微观结构
- 逐点 λ̄ 曲线
- 断裂点(λ̄<0.1)及周围放大(前兆/台阶/振荡)
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
L = 22
QS = ["图灵在1950年发表的著名论文叫什么名字？", "计算 7×8 等于多少", "你好"]

def gen_trace(model, tok, q, steps=45):
    ids = tok(q, return_tensors="pt")
    gen = ids["input_ids"]
    prev = None
    lambdas = []
    texts = []
    for i in range(steps):
        with torch.inference_mode():
            lg = model(gen).logits[:, -1]
        nxt = torch.argmax(lg, dim=-1).unsqueeze(0)
        gen = torch.cat([gen, nxt], dim=1)
        with torch.inference_mode():
            h = model(gen, output_hidden_states=True)
        a = h.hidden_states[L][0, -1].float()
        a = a / (a.norm() + 1e-12)
        if prev is not None:
            lambdas.append(1 - F.cosine_similarity(prev.unsqueeze(0), a.unsqueeze(0)).item())
        prev = a
        texts.append(tok.decode(nxt[0], skip_special_tokens=True))
    return lambdas, texts, tok.decode(gen[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    print("=== 过渡显微镜: v4c 长生成逐点 λ̄ ===")
    for q in QS:
        print(f"--- {q} ---")
        lambdas, texts, full = gen_trace(m, tok, q)
        # 分段输出: 每5步均值 (宏观)
        print("步段 λ̄ 均值:", [round(sum(lambdas[i:i+5])/min(5,len(lambdas[i:i+5])), 4) for i in range(0, len(lambdas), 5)])
        # 断裂点: λ̄<0.1 的步
        breaks = [i+1 for i, x in enumerate(lambdas) if x < 0.1]
        print(f"λ̄<0.1 的步(断裂区): {breaks}")
        # 放大断裂区: 断裂点前3步到后3步的逐点值
        if breaks:
            b = breaks[0]
            lo, hi = max(0, b-4), min(len(lambdas), b+4)
            print(f"断裂点 {b} 附近放大:")
            for i in range(lo, hi):
                mark = " <<<" if i+1 in breaks else ""
                print(f"  step{i+1}: λ̄={lambdas[i]:.4f} 输出={texts[i]!r}{mark}")
        else:
            print("无断裂(λ̄ 全>0.1) — 查看最低点附近")
            mi = lambdas.index(min(lambdas))
            lo, hi = max(0, mi-3), min(len(lambdas), mi+4)
            for i in range(lo, hi):
                print(f"  step{i+1}: λ̄={lambdas[i]:.4f} 输出={texts[i]!r}")
        print(f"全文: {full[:80]!r}")
