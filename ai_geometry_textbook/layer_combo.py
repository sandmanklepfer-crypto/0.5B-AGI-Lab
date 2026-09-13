#!/usr/bin/env python3
"""layer_combo.py — 多层组合注入 (浅/中/深组合 × 推理/露骨方向)
组合: [8] [12] [16] [22] [8+12] [16+22] [8+22] [8+12+16] [12+16+22] [8+12+16+22]
每组合: 注入方向 -> 生成对话(三段论 + 场景描写) 看输出差异
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
COMBOS = [[8], [12], [16], [22], [8, 12], [16, 22], [8, 22], [8, 12, 16], [12, 16, 22], [8, 12, 16, 22]]

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_combo(model, tok, q, layers, direction, strength, max_new=18):
    state = {"done": False}
    hooks = []
    for layer in layers:
        def hook_fn(module, inp, out, layer=layer):
            h = out[0]
            if not state["done"]:
                a = h[:, -1, :].float() if h.dim() == 3 else h[-1].float()
                inject = direction * strength
                if h.dim() == 3:
                    h[:, -1, :] = (h[:, -1, :].float() + inject).to(h.dtype)
                else:
                    h[-1] = (h[-1].float() + inject).to(h.dtype)
            return out
        hooks.append(model.model.layers[layer].self_attn.o_proj.register_forward_hook(hook_fn))
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    for h in hooks: h.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    REASON_Q = "所有的A都是B，所有的B都是C，那么A是什么？"
    NON_Q = "你好"
    ADULT_T = "她脱下衣服，身体交缠在一起，在深夜的床上呻吟"
    NORMAL_T = "她走进房间，看到桌上的信，犹豫了一下才打开"
    r_dir = (act_layer(m, tok, REASON_Q, 22) - act_layer(m, tok, NON_Q, 22))
    r_dir = r_dir / (r_dir.norm() + 1e-12)
    a_dir = (act_layer(m, tok, ADULT_T, 22) - act_layer(m, tok, NORMAL_T, 22))
    a_dir = a_dir / (a_dir.norm() + 1e-12)
    print(f"推理×露骨 cos: {F.cosine_similarity(r_dir.unsqueeze(0), a_dir.unsqueeze(0)).item():.4f}")

    for layers in COMBOS:
        name = "+".join(str(l) for l in layers)
        print(f"\n=== 组合 {name} ===")
        # 无注入基线
        base = gen_combo(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", [], r_dir, 0)
        # 推理注入
        a_r = gen_combo(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", layers, r_dir, 1.5)
        print(f"  三段论[推理注入]: {a_r[:65]!r}")
        # 露骨注入
        a_a = gen_combo(m, tok, "写一段场景描写", layers, a_dir, 1.5)
        print(f"  场景[露骨注入]: {a_a[:65]!r}")
