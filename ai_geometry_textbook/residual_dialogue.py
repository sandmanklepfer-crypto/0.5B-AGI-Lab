#!/usr/bin/env python3
"""residual_dialogue.py — 残差流注入 × 三个对话场景
对话1: 三段论(推理方向) | 对话2: 场景描写(露骨方向) | 对话3: 你好(推理方向干扰?)
层8+22 残差流注入(层输入), 强度2.5
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
LAYERS = [8, 22]
S = 2.5

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_res(model, tok, q, direction, max_new=18):
    state = {"done": False}
    hooks = []
    for layer in LAYERS:
        def hook_in(module, inp, out, layer=layer):
            h = out[0]
            if not state["done"]:
                if h.dim() == 3:
                    h[:, -1, :] = (h[:, -1, :].float() + direction * S).to(h.dtype)
                else:
                    h[-1] = (h[-1].float() + direction * S).to(h.dtype)
            return out
        hooks.append(model.model.layers[layer].self_attn.q_proj.register_forward_hook(hook_in))
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    for h in hooks: h.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    r_dir = act_layer(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", 22) - act_layer(m, tok, "你好", 22)
    r_dir = r_dir / (r_dir.norm() + 1e-12)
    a_dir = act_layer(m, tok, "她脱下衣服，身体交缠在一起，在深夜的床上呻吟", 22) - act_layer(m, tok, "她走进房间，看到桌上的信，犹豫了一下才打开", 22)
    a_dir = a_dir / (a_dir.norm() + 1e-12)

    print("=== 残差流注入(层8+22输入, 99%通道) × 三个对话 ===")
    print("\n[对话1 三段论 | 推理方向注入]")
    base = gen_res(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", r_dir * 0)
    inj = gen_res(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", r_dir)
    print(f"  基线: {base[:60]!r}")
    print(f"  注入: {inj[:80]!r}")
    print("\n[对话2 场景描写 | 露骨方向注入]")
    base2 = gen_res(m, tok, "写一段场景描写", a_dir * 0)
    inj2 = gen_res(m, tok, "写一段场景描写", a_dir)
    print(f"  基线: {base2[:60]!r}")
    print(f"  注入: {inj2[:80]!r}")
    print("\n[对话3 你好 | 推理方向注入(看是否干扰日常)]")
    inj3 = gen_res(m, tok, "你好", r_dir)
    print(f"  注入: {inj3[:60]!r}")
