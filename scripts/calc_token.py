#!/usr/bin/env python3
"""calc_token.py — 内化计算器: 0.5B 学会"识别计算需求+输出计算标记"
训练: 算术/代数/物理公式题 -> "答案 = ⟨calc⟩表达式⟨/calc⟩"
推理: 解析标记 -> eval -> 嵌入结果 (100% 正确)
用法: calc_token.py [--train|--infer] [--out DIR]
"""
import sys, os, random, re, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'   # 起点 (v5 出来后换 v5)

# 计算标记数据生成: 题 -> 答案 = ⟨calc⟩expr⟨/calc⟩
def make_samples(n=400):
    samples = []
    # 算术
    for _ in range(n // 4):
        a, b = random.randint(6, 99), random.randint(6, 99)
        op, f = random.choice([("+", "+"), ("-", "-"), ("*", "*"), ("*", "×")])
        samples.append((f"计算：{a}{f}{b}等于多少？", f"答案 = ⟨calc⟩{a}{op}{b}⟨/calc⟩"))
    # 代数
    for _ in range(n // 4):
        x = random.randint(2, 20); a = random.randint(2, 9); b = a * x
        samples.append((f"解方程：{a}x={b}，求x。", f"答案 = ⟨calc⟩{b}/{a}⟨/calc⟩"))
    # 几何 (周长/面积)
    for _ in range(n // 8):
        r = random.randint(2, 12)
        samples.append((f"半径为{r}的圆周长（π=3.14）？", f"答案 = ⟨calc⟩2*3.14*{r}⟨/calc⟩"))
    for _ in range(n // 8):
        s = random.randint(3, 15)
        samples.append((f"边长为{s}的正方形面积？", f"答案 = ⟨calc⟩{s}*{s}⟨/calc⟩"))
    # 物理/混合 (幂/百分数)
    for _ in range(n // 8):
        a = random.randint(2, 9); b = random.randint(3, 6)
        samples.append((f"计算 {a} 的 {b} 次方。", f"答案 = ⟨calc⟩{a}**{b}⟨/calc⟩"))
    for _ in range(n // 8):
        v = random.randint(100, 999); p = random.choice([5, 10, 20, 50])
        samples.append((f"{v} 的 {p}% 是多少？", f"答案 = ⟨calc⟩{v}*{p}/100⟨/calc⟩"))
    random.shuffle(samples)
    return samples

def infer_with_calc(model, tok, prompt, max_new=80):
    """生成 + 解析 ⟨calc⟩ 标记 -> eval 嵌入结果 (可能多轮)"""
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    text = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    # 解析所有 ⟨calc⟩expr⟨/calc⟩
    for _ in range(5):
        m = re.search(r'⟨calc⟩(.+?)⟨/calc⟩', text)
        if not m: break
        expr = m.group(1)
        try:
            val = eval(expr, {"__builtins__": {}}, {"math": __import__("math")})
            val = round(val, 4) if isinstance(val, float) else val
        except Exception:
            val = "?"
        text = text[:m.start()] + str(val) + text[m.end():]
    return text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="train", choices=["train", "infer"])
    ap.add_argument("--out", default="/root/distill_calc_v1")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")

    if args.mode == "train":
        samples = make_samples(args.n)
        print(f"[data] {len(samples)} samples", flush=True)
        opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
        for ep in range(1, args.epochs + 1):
            random.shuffle(samples)
            tot = 0
            for i in range(0, len(samples), 4):
                batch = samples[i:i + 4]
                in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True,
                             truncation=True, max_length=120).to("cuda:0")
                ans_ids = tok([a for _, a in batch], return_tensors="pt", padding=True,
                              truncation=True, max_length=80).to("cuda:0")
                il = in_ids["input_ids"].shape[1]
                full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
                am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
                labels = full.clone(); labels[:, :il] = -100
                loss = model(full, attention_mask=am, labels=labels).loss
                opt.zero_grad(); loss.backward(); opt.step()
                tot += loss.item()
            print(f"[ep{ep}] loss={tot / (len(samples) // 4):.4f}", flush=True)
        model.save_pretrained(args.out); tok.save_pretrained(args.out)
        print(f"[save] {args.out}", flush=True)
        model.eval()
        # 验证
        for q in ["计算：7乘以8等于多少？", "解方程：3x=21，求x。", "半径为5的圆周长（π=3.14）？", "计算 2 的 10 次方。"]:
            print(f"Q: {q}\nA: {infer_with_calc(model, tok, q)}", flush=True)
    else:
        model.eval()
        while True:
            try:
                q = input("> ").strip()
            except EOFError:
                break
            if q:
                print(infer_with_calc(model, tok, q))

if __name__ == "__main__":
    main()
