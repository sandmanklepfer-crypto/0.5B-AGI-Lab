#!/usr/bin/env python3
"""quick_top.py — 保底快速训练 (不等 R1): 规则 calc 数学 + 标准代码示范
数学: 规则生成 300 条 calc 样本 (各级别, 确定性正确)
代码: 10 条标准函数示范 (固定低熵格式)
验证: 数学 calc 解析 + 代码生成
用法: quick_top.py [--out DIR] [--epochs N]
"""
import sys, os, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'
S_LAYER = 22

def make_math(n=300):
    """全级别 calc 数学样本 (规则, 100% 正确)"""
    out = []
    def add(q, expr):
        out.append((f"题目：{q}\n解题步骤：\n步骤1：根据题意列出算式。\n步骤2：计算。\n答案", f" = ⟨calc⟩{expr}⟨/calc⟩"))
    for _ in range(n):
        t = random.randrange(8)
        if t == 0:
            a, b = random.randint(1, 99), random.randint(1, 99); add(f"{a}+{b}等于多少", f"{a}+{b}")
        elif t == 1:
            a = random.randint(11, 99); b = random.randint(1, a-1); add(f"{a}-{b}等于多少", f"{a}-{b}")
        elif t == 2:
            a, b = random.randint(2, 12), random.randint(2, 12); add(f"{a}×{b}等于多少", f"{a}*{b}")
        elif t == 3:
            x = random.randint(2, 15); k = random.randint(2, 9); add(f"解方程 x+{k}={x+k}", f"{x+k}-{k}")
        elif t == 4:
            x = random.randint(2, 12); a = random.randint(2, 9); add(f"解方程 {a}x={a*x}", f"{a*x}/{a}")
        elif t == 5:
            a, b = random.randint(2, 9), random.randint(2, 5); add(f"{a}的{b}次方", f"{a}**{b}")
        elif t == 6:
            r = random.randint(2, 12); add(f"半径为{r}的圆周长(π=3.14)", f"2*3.14*{r}")
        else:
            v, p = random.randint(100, 999), random.choice([5, 10, 15, 20, 50]); add(f"{v}的{p}%", f"{v}*{p}/100")
    return out

CODES = [
    ("写一个函数计算两个数的和", "def add(a, b):\n    \"\"\"返回 a 和 b 的和\"\"\"\n    return a + b"),
    ("写一个函数判断偶数", "def is_even(n):\n    \"\"\"判断 n 是否为偶数\"\"\"\n    return n % 2 == 0"),
    ("写一个函数计算列表平均值", "def average(nums):\n    \"\"\"返回列表平均值\"\"\"\n    return sum(nums) / len(nums)"),
    ("写一个函数返回字符串长度", "def str_len(s):\n    \"\"\"返回字符串长度\"\"\"\n    return len(s)"),
    ("写一个函数找列表最大值", "def find_max(nums):\n    \"\"\"返回列表最大值\"\"\"\n    return max(nums)"),
    ("写一个函数计算阶乘", "def factorial(n):\n    \"\"\"计算 n 的阶乘\"\"\"\n    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result"),
    ("写一个函数反转字符串", "def reverse_str(s):\n    \"\"\"反转字符串\"\"\"\n    return s[::-1]"),
    ("写一个函数判断质数", "def is_prime(n):\n    \"\"\"判断 n 是否为质数\"\"\"\n    if n < 2:\n        return False\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            return False\n    return True"),
    ("写一个函数把摄氏温度转华氏", "def c_to_f(c):\n    \"\"\"摄氏转华氏\"\"\"\n    return c * 9 / 5 + 32"),
    ("写一个函数求斐波那契第n项", "def fib(n):\n    \"\"\"返回斐波那契数列第 n 项\"\"\"\n    if n <= 1:\n        return n\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a"),
]

def gen(model, tok, text, max_new=80):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def resolve_calc(text):
    for _ in range(4):
        m = re.search(r'⟨calc⟩(.+?)⟨/calc⟩', text)
        if not m: break
        try:
            val = eval(m.group(1), {"__builtins__": {}}, {"math": __import__("math")})
            val = round(val, 4) if isinstance(val, float) else val
        except Exception:
            val = "?"
        text = text[:m.start()] + str(val) + text[m.end():]
    return text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/distill_top_v1")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")
    n_vocab = model.config.vocab_size

    samples = make_math() + [(f"需求：{q}\n代码", f"\n{c}\n") for q, c in CODES]
    print(f"[data] {len(samples)} samples ({len(samples)-len(CODES)} math + {len(CODES)} code)", flush=True)
    random.shuffle(samples)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), 2):
            batch = samples[i:i+2]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=300).to("cuda:0")
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
            loss = loss_ce + 0.5 * loss_den
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
        print(f"[ep{ep}] avg={tot/max(n,1):.4f} ce={loss_ce.item():.4f} den={loss_den.item():.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)
    model.eval()
    print("=== 验证 ===", flush=True)
    for q in ["题目：3+4等于多少\n解题步骤：\n步骤1：根据题意列出算式。\n步骤2：计算。\n答案",
              "题目：7×8等于多少\n解题步骤：\n步骤1：根据题意列出算式。\n步骤2：计算。\n答案",
              "题目：解方程 3x=21\n解题步骤：\n步骤1：根据题意列出算式。\n步骤2：计算。\n答案",
              "需求：写一个函数计算两个数的和\n代码", "需求：写一个函数计算阶乘\n代码"]:
        a = gen(model, tok, q, 60)
        print(f"  Q: {q[:26]}...\n  A: {resolve_calc(a)[:100]}", flush=True)

if __name__ == "__main__":
    main()
