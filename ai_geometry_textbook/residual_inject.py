#!/usr/bin/env python3
"""residual_inject.py — 残差流注入 (99%公共通道) vs 层输出注入
层输入注入(残差流, 主通道) vs 层输出注入(局部) 在层8+22
测: 三段论推理触发 + 强度扫描
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
LAYERS = [8, 22]
Q = "所有的A都是B，所有的B都是C，那么A是什么？"
NON_Q = "你好"

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_inject(model, tok, q, layers, direction, strength, mode, max_new=20):
    """mode: 'out'=层输出注入(整层) 'in'=层输入注入(残差流)"""
    state = {"done": False}
    hooks = []
    for layer in layers:
        if mode == "out":
            def hook_out(module, inp, out, layer=layer):
                h = out[0]
                if not state["done"]:
                    if h.dim() == 3:
                        h[:, -1, :] = (h[:, -1, :].float() + direction * strength).to(h.dtype)
                    else:
                        h[-1] = (h[-1].float() + direction * strength).to(h.dtype)
                return out
            hooks.append(model.model.layers[layer].self_attn.o_proj.register_forward_hook(hook_out))
        else:
            def hook_in(module, inp, out, layer=layer):
                h = out[0]
                if not state["done"]:
                    # 残差流注入: 修改层输入(残差主通道) -> 沿残差传播
                    if h.dim() == 3:
                        h[:, -1, :] = (h[:, -1, :].float() + direction * strength).to(h.dtype)
                    else:
                        h[-1] = (h[-1].float() + direction * strength).to(h.dtype)
                return out
            # 输入注入: hook 在 layer 的输入处(用 self_attn.q_proj 的输入接近残差流)
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
    r_dir = act_layer(m, tok, Q, 22) - act_layer(m, tok, NON_Q, 22)
    r_dir = r_dir / (r_dir.norm() + 1e-12)

    print("=== 残差流注入(层输入) vs 层输出注入 (层8+22) ===")
    for mode in ["out", "in"]:
        for s in [1.0, 2.5, 4.0]:
            a = gen_inject(m, tok, Q, LAYERS, r_dir, s, mode)
            has_reason = ("子集" in a or "所以" in a or "A是C" in a)
            tag = "REASON!" if has_reason else "   "
            print(f"  {mode}注入 s={s}: {tag} {a[:55]!r}")
