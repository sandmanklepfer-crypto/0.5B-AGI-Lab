#!/usr/bin/env python3
"""assertion_train.py — 训练通用验证器的解析器: 0.5B 学"断言提取"
输入: 候选答案文本 -> 输出: 断言列表 (短格式 "断言: expr" 每行一个)
工具仲裁: 提取的断言 -> calc/exec 验证 (确定性)
数据: 数字/方程/代码/事实 四种格式, 泛化提取模式
用法: assertion_train.py [--out DIR] [--epochs N]
"""
import sys, os, random, argparse, json
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'

def make_data(n=240):
    """候选答案文本 -> 断言行 (训练 0.5B 提取)"""
    out = []
    def add(text, asserts):
        if asserts:
            out.append((f"候选答案 {text}\n提取断言", "\n".join(f"断言 = ⟨a⟩{a}⟨/a⟩" for a in asserts)))
    # 数字断言 (对/错混合)
    for _ in range(n // 4):
        a, b = random.randint(2, 99), random.randint(2, 99)
        correct = random.random() < 0.5
        v = a + b if correct else a + b + random.choice([1, 2, -1, -2])
        add(f"计算结果是 {v}。", [f"{a}+{b}={v}"])
    # 方程断言
    for _ in range(n // 8):
        x = random.randint(2, 15); a = random.randint(2, 9)
        correct = random.random() < 0.5
        v = x if correct else x + random.choice([1, -1, 2])
        add(f"解得 x={v}。", [f"{a}x={a*x}, x={v}"])
    # 幂断言
    for _ in range(n // 8):
        a, b = random.randint(2, 9), random.randint(2, 4)
        correct = random.random() < 0.5
        v = a ** b if correct else a ** b + random.choice([1, -1])
        add(f"{a}的{b}次方等于 {v}。", [f"{a}**{b}={v}"])
    # 代码断言 (函数返回)
    for _ in range(n // 8):
        a, b = random.randint(1, 20), random.randint(1, 20)
        add(f"函数返回 {a+b}。", [f"add({a},{b})->{a+b}"])
    # 事实断言 (常识对/错)
    facts = [("水的沸点是100度。", ["水的沸点=100"]), ("一年有13个月。", ["一年有12个月"]),
             ("太阳从西边升起。", ["太阳从东方升起"]), ("地球绕太阳转。", ["地球绕太阳转"])]
    for _ in range(n // 8):
        t, a = random.choice(facts)
        add(t, a)
    random.shuffle(out)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/assert_v1")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")
    data = make_data()
    print(f"[data] {len(data)} assertion-extraction samples", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(data)
        tot = 0.0; n = 0
        for i in range(0, len(data), 4):
            batch = data[i:i+4]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=120).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=60).to("cuda:0")
            il = in_ids["input_ids"].shape[1]
            full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
            am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
            labels = full.clone(); labels[:, :il] = -100
            logits_f = model(full, attention_mask=am).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), full.view(-1), reduction='none')
            mask = (labels.view(-1) != -100)
            loss = ce_all[mask].mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f"[ep{ep}] avg={tot/max(n,1):.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)
    # 验证: 提取断言
    model.eval()
    print("=== 验证: 断言提取 ===", flush=True)
    for t in ["计算结果是 62。", "解得 x=8。", "7的3次方等于 344。", "函数返回 12。", "水的沸点是100度。"]:
        ids = tok(f"候选答案 {t}\n提取断言", return_tensors="pt").to("cuda:0")
        with torch.inference_mode():
            out = model.generate(**ids, max_new_tokens=40, do_sample=False, pad_token_id=tok.eos_token_id)
        print(f"  输入: {t}\n  提取: {tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()[:60]!r}", flush=True)

if __name__ == "__main__":
    main()
