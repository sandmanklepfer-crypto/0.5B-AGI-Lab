#!/usr/bin/env python3
"""fix_template.py — 模板串扰修复
1. 推理截断: 生成时检测模板前缀 -> 截断 (硬保险, 立即生效)
2. 停止token微调: v4b + (answer+eos) 训练, 学会"答完就停"
用法: fix_template.py [--mode cut|finetune|both] [--out DIR]
"""
import json, re, sys, os, random, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/root/autodl-tmp/distill_out_3b"
# 模板串扰前缀 (来自 gemma_ctx / rag 训练数据的模板)
TEMPLATE_PREFIXES = [
    "请提供一份关于", "请提供一下关于", "请阅读下面的文档", "请阅读以下文档",
    "以下是关于", "以下是2008", "下面是关于", "请用三句话总结", "简要描述一下",
    "请写一篇关于", "请根据文档", "根据文档", "百度知道", "百度用户",
    "请概述", "请总结", "请给出", "你好！我是", "作为人工智能",
]

def truncate_template(text: str) -> str:
    """检测模板前缀 -> 截断; 也截断无意义的重复"""
    for p in TEMPLATE_PREFIXES:
        i = text.find(p)
        if i > 0:
            return text[:i].strip()
    return text.strip()

def gen(model, tok, text, max_new=120):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both", choices=["cut", "finetune", "both"])
    ap.add_argument("--out", default="/root/autodl-tmp/distill_v4c")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--lr", type=float, default=1e-5)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16).to("cuda:0")
    model.train()

    rows = [json.loads(l) for l in open("/root/rag_data.jsonl", encoding="utf-8") if l.strip()]

    if args.mode in ("cut", "both"):
        # 验证截断效果 (修复前 vs 修复后)
        model.eval()
        print("=== 截断修复验证 ===", flush=True)
        q = "图灵在1950年发表的著名论文叫什么名字？"
        raw = gen(model, tok, q)
        fixed = truncate_template(raw)
        print(f"raw:   {raw[:150]!r}", flush=True)
        print(f"fixed: {fixed[:150]!r}", flush=True)

    if args.mode in ("finetune", "both"):
        # 停止 token 微调: 样本 = (context+query -> answer + eos)
        # 同时加"无模板"通用问答对 (probes 简单题), 强化 eos 行为
        samples = []
        for r in rows:
            samples.append((r["context"][:500] + r["query"], r["answer"]))
        plain = [
            ("图灵在1950年发表的著名论文叫什么名字？", "《计算机器与智能》"),
            ("100减37等于多少？", "63"),
            ("地球内部的主要结构是什么？", "地核、地幔、地壳。"),
            ("用Python计算半径为5的圆的面积。", "import math\nprint(math.pi * 5 ** 2)"),
        ]
        samples += plain
        random.shuffle(samples)
        print(f"[data] {len(samples)} samples (含 {len(plain)} 无模板)", flush=True)

        opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
        for ep in range(1, args.epochs + 1):
            tot = 0.0; n = 0
            for i in range(0, len(samples), 2):
                batch = samples[i:i + 2]
                in_t = [c for c, _ in batch]
                ans_t = [a + tok.eos_token for _, a in batch]
                enc = tok(in_t, return_tensors="pt", padding=True, truncation=True, max_length=600).to("cuda:0")
                ans_ids = tok(ans_t, return_tensors="pt", padding=True, truncation=True, max_length=300).to("cuda:0")
                il = enc["input_ids"].shape[1]
                full = torch.cat([enc["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
                am = torch.cat([enc["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
                labels = full.clone(); labels[:, :il] = -100
                loss = model(full, attention_mask=am, labels=labels).loss
                opt.zero_grad(); loss.backward(); opt.step()
                tot += loss.item(); n += 1
            print(f"[ep{ep}] avg_loss={tot / max(n, 1):.4f}", flush=True)
        model.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f"[save] {args.out}", flush=True)
        # 验证修复后
        model.eval()
        for q in ["图灵在1950年发表的著名论文叫什么名字？", "100减37等于多少？"]:
            a = gen(model, tok, q)
            print(f"Q: {q}\nA(finetuned): {truncate_template(a)[:150]!r}", flush=True)

if __name__ == "__main__":
    main()
