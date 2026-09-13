#!/usr/bin/env python3
"""distill_top.py — 0.5B 吸收 R1-32B 顶级示范 (数学步骤+calc答案, 代码函数)
数据: /root/top_r1_math/*.bin (R1 解题步骤) + /root/top_r1_code/*.bin (R1 代码)
      + 规则 calc 答案 (数学确定性 100% 正确)
损失: CE (文本级, 已验证转移路径) + denoise (结构稳定)
用法: distill_top.py [--out DIR] [--epochs N] [--lr X]
"""
import struct, glob, os, sys, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'
S_LAYER = 22

def load_dump(path, n_vocab=151643):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    prompt = prompt[prompt < n_vocab]
    gen = gen[gen < n_vocab]
    return prompt, gen

def decode(tokens, tok):
    return tok.decode([int(t) for t in tokens if 0 <= int(t) < 151643], skip_special_tokens=True)

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

    # 数学样本: R1 步骤 + 规则 calc 答案
    samples = []
    meta = json.load(open('/root/top_demos_meta.json', encoding='utf-8'))
    m_files = sorted(glob.glob('/root/top_r1_math/p*.bin'))
    for i, (q, f) in enumerate(zip(meta['math'], m_files)):
        _, gen_t = load_dump(f)
        steps = decode(gen_t, tok)[:400]
        # 规则答案: 从题目提取表达式 (简化: 常见模式)
        expr = None
        m = re.search(r'(\d+)\+(\d+)', q)
        if m: expr = f"{m.group(1)}+{m.group(2)}"
        m = re.search(r'(\d+)-(\d+)', q)
        if m: expr = f"{m.group(1)}-{m.group(2)}"
        m = re.search(r'(\d+)×(\d+)', q)
        if m: expr = f"{m.group(1)}*{m.group(2)}"
        if expr:
            samples.append((f"题目：{q}\n{steps}\n答案", f" = ⟨calc⟩{expr}⟨/calc⟩"))
    # 代码样本: R1 代码
    c_files = sorted(glob.glob('/root/top_r1_code/p*.bin'))
    for i, (q, f) in enumerate(zip(meta['code'], c_files)):
        _, gen_t = load_dump(f)
        code = decode(gen_t, tok)[:400]
        if 'python' in code or 'def ' in code:
            samples.append((f"需求：{q}\n代码", f"\n{code}\n"))
    print(f"[data] {len(samples)} top samples (math+R1steps+calc, code+R1)", flush=True)
    random.shuffle(samples)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), 2):
            batch = samples[i:i+2]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=500).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=200).to("cuda:0")
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

    # 验证
    model.eval()
    print("=== 验证 ===", flush=True)
    for q in ["计算：3+4等于多少？", "计算：7×8等于多少？", "解方程：3x=21，求x。", "半径为5的圆周长（π=3.14）？",
              "写一个函数计算两个数的和。", "写一个函数判断偶数。", "写一个函数计算阶乘。"]:
        a = gen(model, tok, q)
        print(f"  Q: {q}\n  A: {resolve_calc(a)[:110]}", flush=True)

if __name__ == "__main__":
    main()
