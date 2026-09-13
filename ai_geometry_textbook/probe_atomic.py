#!/usr/bin/env python3
"""probe_atomic.py — 组合的原子级几何: 线性/非线性检验 + 头级组合
A. 组合激活 vs 翻译/总结/线性叠加(翻译+总结) 每层cos
   高cos(叠加)=1+1线性 | 低cos=非线性涌现(新模式)
B. 注意力头级: 组合/翻译/总结在各头投影
"""
import torch, torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_v4c"
T_COMBO = "把这句话翻译成英文并用一句话总结：人工智能正在改变世界"
T_TRAN = "把这句话翻译成英文：人工智能正在改变世界"
T_SUM = "用一句话总结这段话：人工智能正在改变世界"
T_NON = "你好"

def all_layer_acts(model, tok, text):
    ids = tok(text, return_tensors="pt")
    with torch.inference_mode():
        h = model(**ids, output_hidden_states=True)
    acts = []
    for li in range(len(h.hidden_states)):
        a = h.hidden_states[li][0].mean(0).float()
        acts.append(a / (a.norm() + 1e-12))
    return acts

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    a_c = all_layer_acts(m, tok, T_COMBO)
    a_t = all_layer_acts(m, tok, T_TRAN)
    a_s = all_layer_acts(m, tok, T_SUM)
    a_n = all_layer_acts(m, tok, T_NON)
    n = m.config.num_hidden_layers

    print("=== A. 组合 = 线性叠加 or 非线性涌现? (每层cos) ===")
    print("层 | 深度% | cos(组合,翻译) | cos(组合,总结) | cos(组合,翻译+总结) | 判定")
    lin_total = 0
    for li in range(n + 1):
        c_t = F.cosine_similarity(a_c[li].unsqueeze(0), a_t[li].unsqueeze(0)).item()
        c_s = F.cosine_similarity(a_c[li].unsqueeze(0), a_s[li].unsqueeze(0)).item()
        # 线性叠加: 归一化翻译+总结
        add = a_t[li] + a_s[li]
        add = add / (add.norm() + 1e-12)
        c_add = F.cosine_similarity(a_c[li].unsqueeze(0), add.unsqueeze(0)).item()
        judge = "线性叠加" if c_add > 0.8 else ("部分重叠" if c_add > 0.5 else "★非线性涌现")
        depth = li / n * 100
        print(f"{li:>3} | {depth:>4.0f}% | {c_t:.3f} | {c_s:.3f} | {c_add:.3f} | {judge}")
        lin_total += (1 if c_add > 0.8 else 0)
    print(f"线性层数: {lin_total}/{n+1} (低=组合是非线性涌现)")

    print("\n=== B. 头级组合 (层22, 14个注意力头) ===")
    def head_proj(text):
        ids = tok(text, return_tensors="pt")
        with torch.inference_mode():
            out = m.model.layers[22].self_attn(ids["input_ids"], position_embeddings=m.model.rotary_emb(m.model.embed_tokens(ids["input_ids"]), torch.arange(ids["input_ids"].shape[1]).unsqueeze(0)), attention_mask=None)
        return out[0]
    # 用隐藏状态简化: 头投影用 q_proj 分头
    def heads_of(text):
        ids = tok(text, return_tensors="pt")
        h = m.model.embed_tokens(ids["input_ids"])
        pos = torch.arange(ids["input_ids"].shape[1]).unsqueeze(0)
        pe = m.model.rotary_emb(h, pos)
        for li in range(22):
            h = m.model.layers[li](h, position_embeddings=pe, attention_mask=None)[0]
        q = m.model.layers[22].self_attn.q_proj(h)[0, -1].view(-1, 14, 64).mean(2).float()  # [14]
        return q / (q.norm() + 1e-12)
    h_c = heads_of(T_COMBO); h_t = heads_of(T_TRAN); h_s = heads_of(T_SUM)
    print("头 | cos(组合头,翻译头) | cos(组合头,总结头) | 双高?")
    for i in range(14):
        ct = F.cosine_similarity(h_c[i].unsqueeze(0), h_t[i].unsqueeze(0)).item()
        cs = F.cosine_similarity(h_c[i].unsqueeze(0), h_s[i].unsqueeze(0)).item()
        dual = "★双服务" if ct > 0.8 and cs > 0.8 else ""
        print(f"{i:>2} | {ct:.3f} | {cs:.3f} | {dual}")
