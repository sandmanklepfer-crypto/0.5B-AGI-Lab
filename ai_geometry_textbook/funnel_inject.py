#!/usr/bin/env python3
"""funnel_inject.py — 公共带操作: 层4-20多点注入 推理+代码方向
对比: 层输出(8+22) vs 公共带(4-20多点) —— 看组合(推理式代码?)
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_REASON = "所有的A都是B，所有的B都是C，那么A是什么？"
Q_CODE = "写一个Python函数计算两个数的和"
Q_OTHER = "1+1等于几？"
NON_Q = "你好"

def act_layer(model, tok, text, layer=22):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_inject(model, tok, q, dirs, strengths, layers, max_new=18):
    state = {"done": False}
    hooks = []
    for layer in layers:
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
    c = act_layer(m, tok, Q_CODE) - act_layer(m, tok, NON_Q)
    c = c / (c.norm() + 1e-12)

    print("=== 公共带操作: 注入位置对比 ===")
    cases = {"层输出(8+22)": [8, 22], "公共带(4-20)": list(range(4, 21)),
             "汇合点附近(2-5)": [2, 3, 4, 5], "公共带+输出(4-22)": list(range(4, 23))}
    for name, layers in cases.items():
        print(f"\n--- {name} (推理+代码叠加, s=1.0) ---")
        for q in [Q_REASON, Q_CODE, Q_OTHER]:
            a = gen_inject(m, tok, q, [r, c], [1.0, 1.0], layers)
            has_r = "子集" in a or "所以" in a
            has_c = "def " in a or "return" in a
            has_m = "=" in a and any(ch.isdigit() for ch in a[:20])
            tag = ("R+C" if has_r and has_c else ("R" if has_r else ("C" if has_c else ("M" if has_m else "  "))))
            print(f"  {tag} {q[:10]} -> {a[:55]!r}")
