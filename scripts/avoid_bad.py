#!/usr/bin/env python3
"""avoid_bad.py — v4c 防崩内化训练 (逐级正常训练 + 崩坏几何内化)
1. 正样本: 简单题 (calc 标记, 逐级) — 正常学习
2. L_repel: v4c 激活在坏方向(来自 v5c 崩坏)的投影最小化 — 流形远离崩溃区
3. L_neg: 崩坏文本 -> v4c 学会识别"这是错误输出" — 内化反面教材
用法: avoid_bad.py [--out DIR] [--epochs N]
"""
import sys, os, json, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

START = '/root/distill_v4c'
S_LAYER = 22

def make_pos(n=400):
    """正样本: 简单算术 (calc 标记) + 基础逻辑 — 逐级第一级"""
    samples = []
    for _ in range(n // 3):
        a, b = random.randint(2, 99), random.randint(2, 99)
        op, sym = random.choice([("+", "+"), ("-", "-"), ("*", "*")])
        samples.append((f"计算：{a}{sym}{b}等于多少？", f"答案 = ⟨calc⟩{a}{op}{b}⟨/calc⟩"))
    for _ in range(n // 6):
        x = random.randint(2, 12); a = random.randint(2, 8); b = a * x
        samples.append((f"解方程：{a}x={b}，求x。", f"答案 = ⟨calc⟩{b}/{a}⟨/calc⟩"))
    logic = [
        ("所有的猫都是动物，咪咪是猫，咪咪是什么？", "咪咪是动物。"),
        ("如果今天下雨路会湿，今天路没湿，今天下雨了吗？", "今天没有下雨。"),
        ("所有的A都是B，所有的B都是C，那么A是什么？", "A是C。"),
        ("1+1等于几？", "2。"),
    ]
    for _ in range(n // 6):
        q, a = random.choice(logic)
        samples.append((q, a))
    random.shuffle(samples)
    return samples

def gen(model, tok, text, max_new=60):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def act_pool(model, ids, layer):
    with torch.inference_mode():
        h = model(ids, output_hidden_states=True)
    return h.hidden_states[layer][0].mean(0).float()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/distill_v4d")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--w_repel", type=float, default=1.0)
    ap.add_argument("--w_neg", type=float, default=0.5)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(START); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(START, dtype=torch.bfloat16).to("cuda:0")
    n_vocab = model.config.vocab_size

    pos = make_pos()
    neg = json.load(open('/root/neg_samples.json', encoding='utf-8'))
    bad_dirs = torch.tensor(np.load('/root/bad_dirs.npz')['dirs'], dtype=torch.float32, device="cuda:0")  # [5,896]
    print(f"[data] pos={len(pos)} neg={len(neg)} bad_dirs={bad_dirs.shape}", flush=True)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(pos)
        tot = 0.0; n = 0
        for i in range(0, len(pos), 4):
            batch = pos[i:i+4]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=100).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=60).to("cuda:0")
            il = in_ids["input_ids"].shape[1]
            full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
            am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
            labels = full.clone(); labels[:, :il] = -100
            logits_f = model(full, attention_mask=am).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), full.view(-1), reduction='none')
            mask = (labels.view(-1) != -100)
            loss_ce = ce_all[mask].mean()

            # L_repel: 训练样本激活远离坏方向 (正常模式, 梯度流通)
            acts = model(full, attention_mask=am, output_hidden_states=True).hidden_states[S_LAYER][0].mean(0).float()
            cos_bad = (acts.unsqueeze(0) @ bad_dirs.T).abs().mean()  # 对 5 个坏方向的投影
            loss_repel = cos_bad

            # L_neg: 崩坏识别 — 输入崩坏文本, 学会说"这是错误输出" (正常模式)
            loss_neg = torch.tensor(0.0, device="cuda:0")
            if n % 3 == 0:
                nb = random.choice(neg)
                nq = nb["q"] + "\n候选回答：" + nb["bad"][:150]
                na = "这个回答是错误的、崩坏的。正确做法是：先理解问题，再逐步推理，最后给出准确答案。"
                n_ids = tok([nq], return_tensors="pt").to("cuda:0")
                na_ids = tok([na], return_tensors="pt").to("cuda:0")
                nl = n_ids["input_ids"].shape[1]
                nfull = torch.cat([n_ids["input_ids"], na_ids["input_ids"][:, :nl]], dim=1)
                nlab = nfull.clone(); nlab[:, :nl] = -100
                nlogits = model(nfull).logits.float()
                nce = F.cross_entropy(nlogits.view(-1, nlogits.shape[-1]), nfull.view(-1), reduction='none')
                nmask = (nlab.view(-1) != -100)
                loss_neg = nce[nmask].mean() if nmask.any() else torch.tensor(0.0, device="cuda:0")

            loss = loss_ce + args.w_repel * loss_repel + args.w_neg * loss_neg
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f"[ep{ep}] avg={tot/max(n,1):.4f} ce={loss_ce.item():.4f} repel={loss_repel.item():.4f} neg={loss_neg.item():.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)

    # 验证
    model.eval()
    print("=== 验证 (正常题 + 崩坏识别) ===", flush=True)
    for q in ["100减37等于多少？", "7乘以8等于多少？", "图灵在1950年发表的著名论文叫什么名字？", "所有的A都是B，所有的B都是C，那么A是什么？"]:
        print(f"  Q: {q}\n  A: {gen(model, tok, q)[:90]}", flush=True)
    nb = random.choice(neg)
    qq = nb["q"] + "\n候选回答：" + nb["bad"][:120]
    print(f"  [崩坏识别] {gen(model, tok, qq, 40)[:80]}", flush=True)

if __name__ == "__main__":
    main()
