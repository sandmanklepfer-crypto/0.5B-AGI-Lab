#!/usr/bin/env python3
"""dim_combo.py — 维度组合: 推理方向 × 代码方向 叠加注入
验证: ①正交性 ②单独/叠加注入效果 ③共存(互不干扰) ④组合出新技能
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_REASON = "所有的A都是B，所有的B都是C，那么A是什么？"
Q_CODE = "写一个Python函数计算两个数的和"
NON_Q = "你好"
CODE_T = "写一个Python函数计算两个数的和"

def act_layer(model, tok, text, layer=22):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_inject(model, tok, q, dirs, strengths, max_new=18):
    state = {"done": False}
    hooks = []
    for layer in [8, 22]:
        def hook_out(module, inp, out, layer=layer):
            h = out[0]
            if not state["done"]:
                inj = sum(d * s for d, s in zip(dirs, strengths))
                if h.dim() == 3:
                    h[:, -1, :] = (h[:, -1, :].float() + inj).to(h.dtype)
                else:
                    h[-1] = (h[-1].float() + inj).to(h.dtype)
            return out
        hooks.append(model.model.layers[layer].self_attn.o_proj.register_forward_hook(hook_out))
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    for h in hooks: h.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    r = act_layer(m, tok, Q_REASON) - act_layer(m, tok, NON_Q)
    r = r / (r.norm() + 1e-12)
    c = act_layer(m, tok, CODE_T) - act_layer(m, tok, NON_Q)
    c = c / (c.norm() + 1e-12)
    print(f"推理×代码方向 cos: {F.cosine_similarity(r.unsqueeze(0), c.unsqueeze(0)).item():.4f}")

    print("\n=== 维度组合: 推理(r) × 代码(c) ===")
    cases = {"仅推理": ([r], [2.5]), "仅代码": ([c], [2.5]), "推理+代码叠加": ([r, c], [2.5, 2.5])}
    for name, (dirs, ss) in cases.items():
        print(f"\n--- {name} ---")
        for q in [Q_REASON, Q_CODE]:
            a = gen_inject(m, tok, q, dirs, ss)
            has_r = "子集" in a or "所以" in a
            has_c = "def " in a or "return" in a or "函数" in a
            tag = ("R+C" if has_r and has_c else ("R" if has_r else ("C" if has_c else "  ")))
            print(f"  {tag} {q[:12]} -> {a[:55]!r}")
