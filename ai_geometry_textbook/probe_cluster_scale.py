#!/usr/bin/env python3
"""probe_cluster_scale.py — 纯几何改簇容量: 推理时放大差异分量
a' = pub + k*(a - pub) —— k=1/2/5/10
测: ①概念距离(簇分散度=簇容量) ②λ̄活性(像大模型?) ③生成
"""
import torch, torch.nn.functional as F
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
CONCEPTS = ["高兴", "开心", "难过", "悲伤", "猫", "狗", "苹果", "香蕉", "数学", "物理",
            "太阳", "月亮", "星星", "医生", "老师", "汽车", "火车", "电脑", "手机", "音乐"]
Q = "你好"

def act_raw(model, tok, text, layer=22):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    return h.hidden_states[layer][0].mean(0).float()

def scale_act(a, pub, k):
    """放大差异: a' = pub + k*(a-pub)"""
    return pub + k * (a - pub)

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    # 概念激活 + 公共基底
    raw = {c: act_raw(m, tok, c) for c in CONCEPTS}
    pub = torch.stack(list(raw.values())).mean(0)

    print("=== 差异放大: 簇容量(概念距离) ===")
    for k in [1, 2, 5, 10]:
        dists = []
        cs = [c for c in CONCEPTS]
        for i in range(len(cs)):
            for j in range(i+1, len(cs)):
                a_i = scale_act(raw[cs[i]], pub, k); a_i = a_i / (a_i.norm() + 1e-12)
                a_j = scale_act(raw[cs[j]], pub, k); a_j = a_j / (a_j.norm() + 1e-12)
                dists.append(1 - F.cosine_similarity(a_i.unsqueeze(0), a_j.unsqueeze(0)).item())
        print(f"  k={k}: 概念平均距离={np.mean(dists):.4f} (大=簇容量大)")

    print("=== 差异放大: 生成λ̄ + 输出 ===")
    for k in [1, 5, 10]:
        state = {"pub": pub}
        def make_hook(kk):
            def hook_fn(module, inp, out):
                h = out[0]
                a = h[:, -1, :].float() if h.dim() == 3 else h[-1].float()
                scaled = state["pub"] + kk * (a - state["pub"])
                if h.dim() == 3:
                    h[:, -1, :] = scaled.to(h.dtype)
                else:
                    h[-1] = scaled.to(h.dtype)
                return out
            return hook_fn
        hk = m.model.layers[22].self_attn.o_proj.register_forward_hook(make_hook(k))
        ids = tok(Q, return_tensors="pt")
        gen = ids["input_ids"]
        prev = None; lam = []
        for _ in range(15):
            with torch.inference_mode():
                lg = m(gen).logits[:, -1]
            nxt = torch.argmax(lg, dim=-1).unsqueeze(0)
            gen = torch.cat([gen, nxt], dim=1)
            with torch.inference_mode():
                h = m(gen, output_hidden_states=True)
            a = h.hidden_states[22][0, -1].float()
            a = a / (a.norm() + 1e-12)
            if prev is not None:
                lam.append(1 - F.cosine_similarity(prev.unsqueeze(0), a.unsqueeze(0)).item())
            prev = a
        hk.remove()
        out = tok.decode(gen[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        print(f"  k={k}: λ̄={sum(lam)/len(lam):.4f} | {out[:40]!r}")
