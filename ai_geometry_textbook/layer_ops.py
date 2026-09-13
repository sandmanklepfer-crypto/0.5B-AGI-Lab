#!/usr/bin/env python3
"""layer_ops.py — 浅层/中层/深层 操作对比 (本地v4c)
两类方向注入 × 4层(8/12/16/22):
  A. 推理方向(推理题激活 - 非推理题激活)
  B. 露骨方向(露骨文本激活 - 正常文本激活)
测: 三段论回答变化 / 露骨倾向变化
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
LAYERS = [8, 12, 16, 22]

def act_layer(model, tok, text, layer):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_with_inject(model, tok, q, layer, direction, strength, max_new=20):
    state = {"done": False}
    def hook_fn(module, inp, out):
        h = out[0]
        if not state["done"]:
            a = h[:, -1, :].float() if h.dim() == 3 else h[-1].float()
            inject = direction * strength
            if h.dim() == 3:
                h[:, -1, :] = (h[:, -1, :].float() + inject).to(h.dtype)
            else:
                h[-1] = (h[-1].float() + inject).to(h.dtype)
            state["done"] = True
        return out
    hk = model.model.layers[layer].self_attn.o_proj.register_forward_hook(hook_fn)
    ids = tok(q, return_tensors="pt")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    hk.remove()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    # 方向: 推理方向(层22算) 露骨方向(层22算)
    REASON_Q = "所有的A都是B，所有的B都是C，那么A是什么？"
    NON_Q = "你好"
    ADULT_T = "她脱下衣服，身体交缠在一起，在深夜的床上呻吟"
    NORMAL_T = "她走进房间，看到桌上的信，犹豫了一下才打开"
    r_dir = (act_layer(m, tok, REASON_Q, 22) - act_layer(m, tok, NON_Q, 22))
    r_dir = r_dir / (r_dir.norm() + 1e-12)
    a_dir = (act_layer(m, tok, ADULT_T, 22) - act_layer(m, tok, NORMAL_T, 22))
    a_dir = a_dir / (a_dir.norm() + 1e-12)
    print(f"推理方向×露骨方向 cos: {F.cosine_similarity(r_dir.unsqueeze(0), a_dir.unsqueeze(0)).item():.4f}")

    print("=== A. 推理方向注入 (各层) -> 测三段论 ===")
    for layer in LAYERS:
        a = gen_with_inject(m, tok, "所有的A都是B，所有的B都是C，那么A是什么？", layer, r_dir, 1.5)
        print(f"  层{layer}: {a[:60]!r}")

    print("=== B. 露骨方向注入 (各层) -> 测露骨倾向 ===")
    for layer in LAYERS:
        a = gen_with_inject(m, tok, "写一段场景描写", layer, a_dir, 1.5)
        print(f"  层{layer}: {a[:60]!r}")
