#!/usr/bin/env python3
"""mlp_combo.py — 非线性处组合: MLP中间(down_proj输入)注入两个技能方向
方向=MLP中间激活差(4864维), 注入到非线性处(乘积+激活后)
对比: 单独/叠加注入 → 看组合(推理式代码?) 
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_REASON = "所有的A都是B，所有的B都是C，那么A是什么？"
Q_CODE = "写一个Python函数计算两个数的和"
NON_Q = "你好"

def mlp_mid_act(model, tok, text, layer=22):
    """层22 MLP中间激活(act(gate)*up, down_proj输入, 4864维)"""
    cache = {}
    def pre_hook(module, inp):
        cache["x"] = inp[0].detach()
        return inp
    hk = model.model.layers[layer].mlp.down_proj.register_forward_pre_hook(pre_hook)
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        model(**ids)
    hk.remove()
    a = cache["x"][0, -1].float()
    return a / (a.norm() + 1e-12)

def gen_mlp(model, tok, q, dirs, strengths, layer=22, max_new=18):
    state = {"done": False}
    def pre_hook(module, inp):
        if not state["done"]:
            inj = sum(d * s for d, s in zip(dirs, strengths))
            x = inp[0]
            x = x.clone()
            x[:, -1, :] = x[:, -1, :] + inj.to(x.dtype)
            state["done"] = True
            return (x,)
        return inp
    hk = model.model.layers[layer].mlp.down_proj.register_forward_pre_hook(pre_hook)
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    hk.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    r = mlp_mid_act(m, tok, Q_REASON) - mlp_mid_act(m, tok, NON_Q)
    r = r / (r.norm() + 1e-12)
    c = mlp_mid_act(m, tok, Q_CODE) - mlp_mid_act(m, tok, NON_Q)
    c = c / (c.norm() + 1e-12)
    print(f"MLP中间 推理×代码 cos: {F.cosine_similarity(r.unsqueeze(0), c.unsqueeze(0)).item():.4f}")

    print("\n=== MLP中间(非线性)注入 ===")
    cases = {"仅推理": ([r], [2.5]), "仅代码": ([c], [2.5]), "推理+代码叠加": ([r, c], [2.5, 2.5])}
    for name, (dirs, ss) in cases.items():
        print(f"\n--- {name} ---")
        for q in [Q_REASON, Q_CODE]:
            a = gen_mlp(m, tok, q, dirs, ss)
            has_r = "子集" in a or "所以" in a
            has_c = "def " in a or "return" in a or "函数" in a
            tag = ("R+C" if has_r and has_c else ("R" if has_r else ("C" if has_c else "  ")))
            print(f"  {tag} {q[:12]} -> {a[:60]!r}")
