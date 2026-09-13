#!/usr/bin/env python3
"""curriculum_math.py — 数学专精: 二十级课程 (幼儿→博士) 高频逐级训练
每级: 20新样本 + 10复习 -> 1 ep (秒级) -> 保存 + 对话演示 (每几秒可见变化)
用法: curriculum_math.py [--out-prefix DIR] [--levels 0-18] [--quick N]
"""
import sys, os, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'   # 母模 (橡皮泥基座)

def make_level(level, n=20):
    """课程分级: 0=个位加, 1=个位减, 2=十以内, 3=两位加, 4=两位减, 5=小乘法表,
    6=大乘法表, 7=四则混合, 8=简单方程+, 9=乘法方程, 10=负数, 11=分数,
    12=幂/平方, 13=圆周长, 14=百分数, 15=数列, 16=根式, 17=三角, 18=微积分基础"""
    out = []
    def add(q, expr):
        out.append((q, f"答案 = ⟨calc⟩{expr}⟨/calc⟩"))
    for _ in range(n):
        if level == 0:
            a, b = random.randint(1, 9), random.randint(1, 9); add(f"计算：{a}+{b}等于多少？", f"{a}+{b}")
        elif level == 1:
            a = random.randint(2, 9); b = random.randint(1, a-1); add(f"计算：{a}-{b}等于多少？", f"{a}-{b}")
        elif level == 2:
            a, b = random.randint(1, 9), random.randint(1, 9)
            op = random.choice(["+", "-"]); add(f"计算：{a}{op}{b}等于多少？", f"{a}{op}{b}")
        elif level == 3:
            a, b = random.randint(11, 99), random.randint(11, 99); add(f"计算：{a}+{b}等于多少？", f"{a}+{b}")
        elif level == 4:
            a = random.randint(21, 99); b = random.randint(11, a-1); add(f"计算：{a}-{b}等于多少？", f"{a}-{b}")
        elif level == 5:
            a, b = random.randint(2, 5), random.randint(2, 9); add(f"计算：{a}×{b}等于多少？", f"{a}*{b}")
        elif level == 6:
            a, b = random.randint(6, 9), random.randint(6, 9); add(f"计算：{a}×{b}等于多少？", f"{a}*{b}")
        elif level == 7:
            a, b, c = random.randint(2, 9), random.randint(2, 9), random.randint(2, 9)
            add(f"计算：{a}+{b}×{c}等于多少？", f"{a}+{b}*{c}")
        elif level == 8:
            x = random.randint(2, 20); k = random.randint(2, 9); add(f"解方程：x+{k}={x+k}，求x。", f"{x+k}-{k}")
        elif level == 9:
            x = random.randint(2, 12); a = random.randint(2, 9); add(f"解方程：{a}x={a*x}，求x。", f"{a*x}/{a}")
        elif level == 10:
            a, b = random.randint(1, 9), random.randint(1, 9); add(f"计算：-{a}+{b}等于多少？", f"-{a}+{b}")
        elif level == 11:
            a, b = random.randint(1, 9), random.randint(1, 9); add(f"计算：{a}/{b}（保留2位小数）", f"round({a}/{b},2)")
        elif level == 12:
            a, b = random.randint(2, 9), random.randint(2, 5); add(f"计算：{a}的{b}次方。", f"{a}**{b}")
        elif level == 13:
            r = random.randint(2, 12); add(f"半径为{r}的圆周长（π=3.14）？", f"2*3.14*{r}")
        elif level == 14:
            v, p = random.randint(100, 999), random.choice([5, 10, 20, 50]); add(f"{v}的{p}%是多少？", f"{v}*{p}/100")
        elif level == 15:
            a, d = random.randint(1, 9), random.randint(2, 9)
            add(f"等差数列 {a},{a+d},{a+2*d},... 的第5项？", f"{a}+4*{d}")
        elif level == 16:
            s = random.randint(2, 12); add(f"边长为{s}的正方形面积？", f"{s}*{s}")
        elif level == 17:
            a, b = random.randint(3, 10), random.randint(3, 10)
            add(f"直角三角形两直角边{a}和{b}，斜边长（保留2位）？", f"round(({a}**2+{b}**2)**0.5,2)")
        elif level == 18:
            x = random.randint(2, 9); add(f"求 x={x} 时 x²+2x 的值。", f"{x}**2+2*{x}")
    return out

def gen(model, tok, text, max_new=40):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def resolve_calc(text):
    import re
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
    ap.add_argument("--out-prefix", default="/root/distill_math")
    ap.add_argument("--max-level", type=int, default=18)
    ap.add_argument("--lr", type=float, default=1.5e-5)
    ap.add_argument("--epochs", type=int, default=1)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")

    DEMO = ["计算：3+4等于多少？", "计算：7×8等于多少？", "计算：17+25等于多少？", "解方程：3x=21，求x。", "半径为5的圆周长（π=3.14）？", "计算：2的10次方。"]

    cur = BASE
    for lv in range(args.max_level + 1):
        samples = make_level(lv, 20)
        if lv >= 2:
            samples += make_level(lv - 1, 6) + make_level(lv - 2, 4)  # 复习防遗忘
        random.shuffle(samples)
        opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
        tot = 0.0
        for ep in range(args.epochs):
            for i in range(0, len(samples), 4):
                batch = samples[i:i+4]
                in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=100).to("cuda:0")
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
                tot += loss.item()
        out_dir = f"{args.out_prefix}_L{lv}"
        os.makedirs(out_dir, exist_ok=True)
        model.save_pretrained(out_dir); tok.save_pretrained(out_dir)
        # 对话演示 (秒级可见变化)
        model.eval()
        demo_q = DEMO[min(lv, len(DEMO)-1)]
        ans = resolve_calc(gen(model, tok, demo_q))
        print(f"[L{lv}] loss={tot/max(len(samples)//4,1):.4f} | 演示: {demo_q} -> {ans[:60]}", flush=True)
        model.train()

if __name__ == "__main__":
    main()
