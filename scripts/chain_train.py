#!/usr/bin/env python3
"""chain_train.py — R1 顶级短链补进 v4c (短格式防崩坏)
样本: 题目 -> 5 步短链 (空格分隔, 无冒号等号分隔符)
验证: 给难题 -> 生成短链 -> 检查步骤质量
用法: chain_train.py [--out DIR] [--epochs N]
"""
import sys, os, json, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'
S_LAYER = 22

def gen(model, tok, text, max_new=60):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/distill_chain_v1")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=1.5e-5)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")
    n_vocab = model.config.vocab_size

    rows = [json.loads(l) for l in open('/root/chain_data.jsonl', encoding='utf-8') if l.strip()]
    # 样本: 题目 -> "推理链 s1 s2 s3 s4 s5" (空格分隔无符号)
    samples = [(f"题目 {r['q']} 推理链", " " + " ".join(r["chain"])) for r in rows]
    print(f"[data] {len(samples)} chain samples", flush=True)
    random.shuffle(samples)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), 2):
            batch = samples[i:i+2]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=120).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=120).to("cuda:0")
            il = in_ids["input_ids"].shape[1]
            full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
            am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
            labels = full.clone(); labels[:, :il] = -100
            logits_f = model(full, attention_mask=am).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), full.view(-1), reduction='none')
            mask = (labels.view(-1) != -100)
            loss_ce = ce_all[mask].mean()
            with torch.inference_mode():
                a0 = model(full, attention_mask=am, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            xs_n = torch.where(torch.rand(full.shape, device="cuda:0") < 0.15,
                               torch.randint(0, n_vocab, full.shape, device="cuda:0"), full)
            a1 = model(xs_n, attention_mask=am, output_hidden_states=True).hidden_states[S_LAYER][:, -8:].float()
            loss_den = 1 - F.cosine_similarity(a0, a1, dim=-1).abs().mean()
            loss = loss_ce + 0.4 * loss_den
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f"[ep{ep}] avg={tot/max(n,1):.4f} ce={loss_ce.item():.4f} den={loss_den.item():.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)

    # 验证: 难题 -> 短链
    model.eval()
    print("=== 验证: 顶级短链生成 ===", flush=True)
    for r in rows[:6]:
        a = gen(model, tok, f"题目 {r['q']} 推理链")
        print(f"  Q: {r['q'][:28]}", flush=True)
        print(f"  GOLD: {' '.join(r['chain'])[:80]}", flush=True)
        print(f"  GEN:  {a[:80]}", flush=True)

if __name__ == "__main__":
    main()
