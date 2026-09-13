#!/usr/bin/env python3
"""dim_detail.py — 200-500维度内部细节: 逐维贡献 + 分组扫描
A. 推理方向的逐维幅度分布(|r_i|): 核心维度在哪
B. 分组注入(200-300/300-400/400-500/200-350/350-500): 找核心小组
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q = "所有的A都是B，所有的B都是C，那么A是什么？"
NON_Q = "你好"

def act_layer(model, tok, text, layer=22):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_inject(model, tok, q, direction, mask, strength, max_new=20):
    state = {"done": False}
    hooks = []
    for layer in [8, 22]:
        def hook_out(module, inp, out, layer=layer):
            h = out[0]
            if not state["done"]:
                inj = direction * mask * strength
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
    r = act_layer(m, tok, Q) - act_layer(m, tok, NON_Q)
    r = r / (r.norm() + 1e-12)
    amp = r.abs()
    print("=== A. 推理方向逐维幅度分布 ===")
    print(f"前200维贡献: {amp[:200].sum().item():.3f} / {amp.sum().item():.3f}")
    print(f"200-500维贡献: {amp[200:500].sum().item():.3f}")
    print(f"500-896维贡献: {amp[500:].sum().item():.3f}")
    top = torch.topk(amp, 20).indices.tolist()
    print(f"幅度top20维度: {top}")
    # 200-500内的top维度
    in_range = [i for i in range(200, 500) if amp[i] > 0.02]
    print(f"200-500内幅度>0.02的维度: {len(in_range)}个, 例: {in_range[:20]}")

    print("\n=== B. 分组注入 (层8+22, 强度2.5) ===")
    groups = {"200-300": (200, 300), "300-400": (300, 400), "400-500": (400, 500),
              "200-350": (200, 350), "350-500": (350, 500), "200-500": (200, 500)}
    for name, (lo, hi) in groups.items():
        mask = torch.zeros(896)
        mask[lo:hi] = 1.0
        a = gen_inject(m, tok, Q, r, mask, 2.5)
        has_reason = ("子集" in a or "所以" in a or "A是C" in a)
        print(f"  {name}: {'REASON!' if has_reason else '   '} {a[:50]!r}")
