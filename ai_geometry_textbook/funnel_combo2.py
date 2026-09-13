#!/usr/bin/env python3
"""funnel_combo2.py — 精确组合(两级): 公共带粗调 + 层输出精调
新技能: 翻译 × 总结 (换掉推理×代码)
测: 翻译题/总结题/组合任务(翻译并总结)
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
Q_TRAN = "把你好翻译成英文"
Q_SUM = "用一句话总结这段话：人工智能正在改变世界"
Q_COMBO = "把这句话翻译成英文并用一句话总结：人工智能正在改变世界"
NON_Q = "你好"

def act_layer(model, tok, text, layer=22):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    a = h.hidden_states[layer][0].mean(0).float()
    return a / (a.norm() + 1e-12)

def gen_two(model, tok, q, dirs, strengths, coarse_layers, fine_layers, max_new=20):
    state = {"done": False}
    hooks = []
    for layer in coarse_layers + fine_layers:
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
    t = act_layer(m, tok, Q_TRAN) - act_layer(m, tok, NON_Q)
    t = t / (t.norm() + 1e-12)
    s = act_layer(m, tok, Q_SUM) - act_layer(m, tok, NON_Q)
    s = s / (s.norm() + 1e-12)
    print(f"翻译×总结 cos: {F.cosine_similarity(t.unsqueeze(0), s.unsqueeze(0)).item():.4f}")

    coarse = list(range(4, 21))
    fine = [8, 22]
    print("\n=== 精确组合(两级: 公共带粗调+层输出精调) ===")
    cases = {
        "无注入": ([], [], 0),
        "公共带粗调(翻译+总结)": ([t, s], [1.0, 1.0], 0),
        "层输出精调(翻译+总结)": ([], [], 0),
        "两级(粗调1.0+精调0.5)": ([t, s], [1.0, 1.0], 0),
    }
    # 简化: 四级强度组合
    for name, dl, sl, extra in [
        ("无注入", [], [], 0),
        ("仅公共带粗调", [t, s], [1.0, 1.0], 0),
        ("仅层输出精调", [t, s], [0, 0], 0),
        ("两级: 粗1.0+精0.5", [t, s], [1.0, 1.0], 0),
    ]:
        # 由于同函数, 用参数区分: coarse注入 vs fine注入
        pass
    # 直接实现四组
    print("--- ① 无注入 ---")
    for q in [Q_TRAN, Q_SUM, Q_COMBO]:
        a = gen_two(m, tok, q, [], [], [], [])
        print(f"  {q[:12]} -> {a[:50]!r}")
    print("--- ② 公共带粗调(4-20, 翻译+总结s=1.0) ---")
    for q in [Q_TRAN, Q_SUM, Q_COMBO]:
        a = gen_two(m, tok, q, [t, s], [1.0, 1.0], coarse, [])
        print(f"  {q[:12]} -> {a[:50]!r}")
    print("--- ③ 层输出精调(8+22, 翻译+总结s=0.5) ---")
    for q in [Q_TRAN, Q_SUM, Q_COMBO]:
        a = gen_two(m, tok, q, [t, s], [0.5, 0.5], [], fine)
        print(f"  {q[:12]} -> {a[:50]!r}")
    print("--- ④ 两级(粗1.0 + 精0.5) ---")
    for q in [Q_TRAN, Q_SUM, Q_COMBO]:
        a = gen_two(m, tok, q, [t, s], [1.0, 1.0], coarse, fine)
        print(f"  {q[:12]} -> {a[:55]!r}")
