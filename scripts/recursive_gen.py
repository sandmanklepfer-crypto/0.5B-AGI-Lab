#!/usr/bin/env python3
"""recursive_gen.py — 递归思考测试: 生成->自检->重生成 循环 (TRM 思路推理侧)
错误检测: 重复率 / 模板前缀 / calc缺失 -> 触发重生成 (带上一轮输出作上下文)
对比: 单轮 vs 递归 N 轮的错误率
用法: recursive_gen.py [--model DIR] [--rounds N]
"""
import sys, re, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/distill_v4c'

TEMPLATES = ["请提供", "请阅读", "以下是", "Human:", "百度", "知乎", "2008年", "2009年"]
QS = [
    ("math1", "计算：3+4等于多少？"),
    ("math2", "计算：7×8等于多少？"),
    ("math3", "计算：17+25等于多少？"),
    ("math4", "解方程：3x=21，求x。"),
    ("math5", "半径为5的圆周长（π=3.14）？"),
    ("math6", "计算：2的10次方。"),
    ("logic", "所有的A都是B，所有的B都是C，那么A是什么？"),
    ("code1", "写一个Python函数计算两个数的和。"),
    ("code2", "写一个Python函数判断偶数。"),
    ("know", "水的沸点是多少度？"),
]

def detect_bad(text, q):
    """检测坏输出: 重复/模板/太短/calc缺失(数学题)"""
    reasons = []
    if len(text) < 4: reasons.append("太短")
    if len(set(text)) < len(text) * 0.3: reasons.append("字符重复")
    for t in TEMPLATES:
        if t in text: reasons.append(f"模板[{t}]"); break
    if any(c.isdigit() for c in q) and "⟨calc⟩" not in text and not any(ch.isdigit() for ch in text):
        reasons.append("无计算")
    return reasons

def gen(model, tok, prompt, max_new=60):
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def resolve_calc(text):
    for _ in range(4):
        m = re.search(r'⟨calc⟩(.+?)⟨/calc⟩', text)
        if not m: break
        try:
            v = eval(m.group(1), {"__builtins__": {}}, {"math": __import__("math")})
            v = round(v, 4) if isinstance(v, float) else v
        except Exception:
            v = "?"
        text = text[:m.start()] + str(v) + text[m.end():]
    return text

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--rounds", type=int, default=4)
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.model); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to("cuda:0")
    model.eval()

    total = {r: [0, 0] for r in range(1, args.rounds + 1)}  # round -> [ok, fail]
    print(f"=== 递归思考测试 (model={args.model}, rounds={args.rounds}) ===", flush=True)
    for tag, q in QS:
        history = ""
        final = ""
        for r in range(1, args.rounds + 1):
            prompt = q + ("\n（上一轮回答不完整或有误，请重新认真回答，只输出最终答案。" + history + "）" if history else "")
            ans = gen(model, tok, prompt)
            history += f"上一轮: {ans[:40]}"
            bad = detect_bad(resolve_calc(ans), q)
            final = ans
            if not bad:
                total[r][0] += 1
                break
            total[r][1] += 1
        ok = not detect_bad(resolve_calc(final), q)
        rounds_used = next((r for r in range(1, args.rounds + 1) if not detect_bad(resolve_calc(gen(model, tok, q)), q)), args.rounds)
        print(f"  {tag}: {'✅' if ok else '❌'} | 轮次{rounds_used} | {resolve_calc(final)[:70]!r}", flush=True)

    print("=== 累计错误率（各轮内解决）===", flush=True)
    solved = 0
    for r in range(1, args.rounds + 1):
        solved += total[r][0]
        print(f"  ≤{r}轮解决: {solved}/{len(QS)} (错误率 {(len(QS)-solved)/len(QS)*100:.0f}%)", flush=True)

if __name__ == "__main__":
    main()
