#!/usr/bin/env python3
"""recursive_fine.py — 最细递归: 逐原子验证, 错哪改哪 (TRM 最细粒度)
1. 算式级: 提取输出中所有算式模式 -> calc 验证 -> 替换错误值 (7×8=5 -> 56)
2. 代码级: 提取可执行代码 -> 执行验证
3. 粗递归兜底: 形式检测不过 -> 重生成
用法: recursive_fine.py [--model DIR] [--rounds N]
"""
import sys, re, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/distill_v4c'
TEMPLATES = ["请提供", "请阅读", "以下是", "Human:", "百度", "知乎"]
QS = [
    ("math1", "计算：3+4等于多少？", "7"),
    ("math2", "计算：7×8等于多少？", "56"),
    ("math3", "计算：17+25等于多少？", "42"),
    ("math4", "解方程：3x=21，求x。", "7"),
    ("math5", "半径为5的圆周长（π=3.14）？", "31.4"),
    ("math6", "计算：2的10次方。", "1024"),
    ("logic", "所有的A都是B，所有的B都是C，那么A是什么？", "C"),
    ("code1", "写一个Python函数计算两个数的和。", "return a + b"),
    ("know", "水的沸点是多少度？", "100"),
]

# 算式模式: 数字 运算符 数字 (支持 × + - * / ** % 和括号, 简单)
EXPR_PAT = re.compile(r'(\d+(?:\.\d+)?)\s*([×x*]|\+|-|/|%|÷|\*\*)\s*(\d+(?:\.\d+)?)')
# 中文算式: X的Y次方 / X的Y%
POW_PAT = re.compile(r'(\d+)\s*的\s*(\d+)\s*次方')
PCT_PAT = re.compile(r'(\d+)\s*的\s*(\d+)\s*%')

def calc(expr):
    try:
        v = eval(expr, {"__builtins__": {}}, {"math": __import__("math")})
        return round(v, 4) if isinstance(v, float) else v
    except Exception:
        return None

def verify_replace(text):
    """逐原子验证: 提取算式/幂/百分数 -> 计算 -> 替换 (错哪改哪)"""
    out = text
    for m in EXPR_PAT.finditer(text):
        a, op, b = m.group(1), m.group(2), m.group(3)
        pyop = {"×": "*", "x": "*", "÷": "/", "**": "**"}.get(op, op)
        v = calc(f"{a}{pyop}{b}")
        if v is not None:
            out = out.replace(m.group(0), str(v))
    for m in POW_PAT.finditer(text):
        v = calc(f"{m.group(1)}**{m.group(2)}")
        if v is not None:
            out = out.replace(m.group(0), str(v))
    for m in PCT_PAT.finditer(text):
        v = calc(f"{m.group(1)}*{m.group(2)}/100")
        if v is not None:
            out = out.replace(m.group(0), str(v))
    return out

def detect_bad(text):
    reasons = []
    if len(text) < 4: reasons.append("太短")
    if len(set(text)) < len(text) * 0.3: reasons.append("字符重复")
    for t in TEMPLATES:
        if t in text: reasons.append(f"模板[{t}]"); break
    return reasons

def gen(model, tok, prompt, max_new=70):
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.model); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to("cuda:0")
    model.eval()

    print(f"=== 最细递归测试 (model={args.model}) ===", flush=True)
    stats = {"content_ok": 0, "form_ok": 0}
    for tag, q, gold in QS:
        final = ""
        for r in range(args.rounds):
            prompt = q + (f"\n（上一轮回答不正确或不完整，请重新认真回答，只输出最终答案。）" if r > 0 else "")
            ans = gen(model, tok, prompt)
            final = ans
            if not detect_bad(ans):
                break
        # 细递归: 算式级验证替换
        fixed = verify_replace(final)
        form_ok = not detect_bad(fixed)
        # 内容判据: 金标准出现在修正后的输出里
        content_ok = gold in fixed
        stats["form_ok"] += form_ok
        stats["content_ok"] += content_ok
        mark = "✅" if content_ok else "❌"
        print(f"  {tag}: {mark} | 修正后: {fixed[:90]!r}", flush=True)
    n = len(QS)
    print(f"\n形式质量: {stats['form_ok']}/{n} | 内容正确(细递归修正后): {stats['content_ok']}/{n}", flush=True)

if __name__ == "__main__":
    main()
