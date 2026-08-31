#!/usr/bin/env python3
"""simple_fix.py — v5b 补救: 简单题重建正确内容 (难度课程第一级)
v5b_s3 起点 + 简单算术(calc标记) + 基础逻辑/知识 + 答案即停(eos)
保留难题结构, 洗掉错误内容 (62/16/模板)
用法: simple_fix.py [--out DIR] [--epochs N]
"""
import sys, os, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

START = '/root/distill_v5b_s3'

def make_simple(n=500):
    """简单题: 算术(calc标记) + 基础逻辑 + 基础知识 + 答案即停"""
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
        ("一周有几天？", "7天。"),
    ]
    for _ in range(n // 6):
        q, a = random.choice(logic)
        samples.append((q, a))
    for _ in range(n // 6):
        samples.append(("太阳从哪边升起？", "东方。"))
        samples.append(("水的沸点是多少？", "100摄氏度。"))
    # 模板终止: 答案即停 (eos)
    for _ in range(n // 6):
        samples.append(("写一句话介绍你自己。", "我是助手。"))
    random.shuffle(samples)
    return samples

def gen(model, tok, text, max_new=60):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/distill_v5c")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--n", type=int, default=500)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(START); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(START, dtype=torch.bfloat16).to("cuda:0")
    n_vocab = model.config.vocab_size
    samples = make_simple(args.n)
    print(f"[data] {len(samples)} simple samples", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), 4):
            batch = samples[i:i+4]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=100).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=60).to("cuda:0")
            il = in_ids["input_ids"].shape[1]
            full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
            am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
            labels = full.clone(); labels[:, :il] = -100
            # CE fp32
            with torch.inference_mode():
                logits_f = model(full, attention_mask=am).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), full.view(-1), reduction='none')
            mask = (labels.view(-1) != -100)
            loss_ce = ce_all[mask].mean()
            # denoise 保结构
            with torch.inference_mode():
                a0 = model(full, attention_mask=am, output_hidden_states=True).hidden_states[22][:, -8:].float()
            xs_n = torch.where(torch.rand(full.shape, device="cuda:0") < 0.15,
                               torch.randint(0, n_vocab, full.shape, device="cuda:0"), full)
            a1 = model(xs_n, attention_mask=am, output_hidden_states=True).hidden_states[22][:, -8:].float()
            loss_den = 1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean()
            loss = loss_ce + 0.5 * loss_den
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f"[ep{ep}] avg={tot/max(n,1):.4f} ce={loss_ce.item():.4f} den={loss_den.item():.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)
    # 验证
    model.eval()
    print("=== 验证 ===", flush=True)
    for q in ["100减37等于多少？", "7乘以8等于多少？", "图灵在1950年发表的著名论文叫什么名字？",
              "所有的A都是B，所有的B都是C，那么A是什么？", "计算：12加35等于多少？"]:
        a = gen(model, tok, q)
        print(f"  Q: {q}\n  A: {a[:90]}", flush=True)

if __name__ == "__main__":
    main()
