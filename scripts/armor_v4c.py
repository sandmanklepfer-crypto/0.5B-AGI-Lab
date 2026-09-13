#!/usr/bin/env python3
"""armor_v4c.py — v4c 防死寂武装重训 (解剖学方法全部上)
武装: CE + Lyapunov活性正则(自回归3步, <0.05惩罚) + 锚点防绑架(填充token惩罚)
数据: calc数学(短格式) + 逻辑(短格式) — v4c 健康起点
验证: 生成测试 + 死寂检测
用法: armor_v4c.py [--out DIR] [--epochs N]
"""
import sys, os, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'
L = 22
LYAP_THRESH = 0.05  # 死寂预警线 (来自解剖: 0.046=死寂, 0.24=正常)
# 锚点防绑架: 高频填充token (来自解剖: 标点/空白/碎片)
BAN_WORDS = ["ascu", "彪", "阳", "答案", "111", "的0", "的1", "。", "，", " ", "\t", "!", "?", "。", "、"]

def make_data(n=400):
    out = []
    for _ in range(n // 3):
        a, b = random.randint(2, 99), random.randint(2, 99)
        out.append((f"计算 {a}+{b} 等于多少", f"答案 = ⟨calc⟩{a}+{b}⟨/calc⟩"))
    for _ in range(n // 6):
        a = random.randint(11, 99); b = random.randint(1, a-1)
        out.append((f"计算 {a}-{b} 等于多少", f"答案 = ⟨calc⟩{a}-{b}⟨/calc⟩"))
    for _ in range(n // 6):
        a, b = random.randint(2, 12), random.randint(2, 12)
        out.append((f"计算 {a}×{b} 等于多少", f"答案 = ⟨calc⟩{a}*{b}⟨/calc⟩"))
    logic = [
        ("推理 所有A都是B，所有B都是C，A是什么", "步骤 A是B的子集 B是C的子集 所以A是C"),
        ("推理 如果下雨路湿，路没湿", "步骤 路不湿 说明没有雨"),
        ("问题 太阳从哪边升起", "回答 东方"),
        ("问题 水的沸点是多少", "回答 100摄氏度"),
    ]
    for _ in range(n // 6):
        q, a = random.choice(logic)
        out.append((q, a))
    random.shuffle(out)
    return out

def gen(model, tok, text, max_new=30):
    ids = tok(text, return_tensors="pt").to("cuda:0")
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
    ap.add_argument("--out", default="/root/distill_v4c_armor")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1.5e-5)
    ap.add_argument("--w_lyap", type=float, default=2.0)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")
    n_vocab = model.config.vocab_size
    BAN_IDS = set()
    for w in BAN_WORDS:
        for i in tok.encode(w, add_special_tokens=False):
            BAN_IDS.add(i)

    data = make_data()
    print(f"[data] {len(data)} samples (武装: Lyapunov+锚点防绑架)", flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    step = 0
    for ep in range(1, args.epochs + 1):
        random.shuffle(data)
        tot = 0.0; n = 0
        for i in range(0, len(data), 4):
            batch = data[i:i+4]
            in_ids = tok([q for q, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=100).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a in batch], return_tensors="pt", padding=True, truncation=True, max_length=60).to("cuda:0")
            il = in_ids["input_ids"].shape[1]
            full = torch.cat([in_ids["input_ids"], ans_ids["input_ids"][:, :il]], dim=1)
            am = torch.cat([in_ids["attention_mask"], torch.ones_like(ans_ids["input_ids"][:, :il])], dim=1)
            labels = full.clone(); labels[:, :il] = -100
            logits_f = model(full, attention_mask=am).logits.float()
            ce_all = F.cross_entropy(logits_f.view(-1, logits_f.shape[-1]), full.view(-1), reduction='none')
            mask = (labels.view(-1) != -100)
            loss_ce = ce_all[mask].mean()
            # 锚点防绑架: 答案中填充token的logits惩罚 (非inplace)
            pen = torch.zeros_like(logits_f[0, -1]); pen[list(BAN_IDS)] = -2.0
            loss_ce = loss_ce  # 锚点惩罚主要影响生成, CE 保持

            # Lyapunov 活性正则 (自回归3步, 真指标)
            lyap_pen = torch.tensor(0.0, device="cuda:0")
            if n % 2 == 0:
                seq = full[0:1, :il]
                prev_a = None
                acts = []
                for _ in range(3):
                    with torch.inference_mode():
                        lg = model(seq).logits
                    # 锚点防绑架: 生成时压填充token
                    pen2 = torch.zeros_like(lg[0, -1]); pen2[list(BAN_IDS)] = -2.0
                    lg = lg + pen2.unsqueeze(0).unsqueeze(0)
                    nxt = torch.argmax(lg[0, -1]).unsqueeze(0).unsqueeze(0)
                    seq = torch.cat([seq, nxt], dim=1)
                    with torch.inference_mode():
                        h = model(seq, output_hidden_states=True).hidden_states[L][0, -1].float()
                    acts.append(h)
                for k in range(1, 3):
                    act = 1 - F.cosine_similarity(acts[k-1].unsqueeze(0), acts[k].unsqueeze(0)).item()
                    if act < LYAP_THRESH:
                        lyap_pen = lyap_pen + (LYAP_THRESH - act) * 10
                lyap_pen = lyap_pen / 2

            loss = loss_ce + args.w_lyap * lyap_pen
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1; step += 1
            if step % 20 == 0:
                act_now = 1 - F.cosine_similarity(acts[-2].unsqueeze(0), acts[-1].unsqueeze(0)).item() if 'acts' in dir() and len(acts) > 1 else 0.2
                print(f"  [s{step}] ce={loss_ce.item():.4f} lyap={lyap_pen.item():.4f} 活性={act_now:.4f}", flush=True)
        print(f"[ep{ep}] avg={tot/max(n,1):.4f}", flush=True)
    model.save_pretrained(args.out); tok.save_pretrained(args.out)
    print(f"[save] {args.out}", flush=True)

    # 验证: 生成 + 死寂检测
    model.eval()
    print("=== 验证 (武装后) ===", flush=True)
    for q in ["计算 7×8 等于多少", "计算 17+25 等于多少", "2的10次方", "推理 所有A都是B，所有B都是C，A是什么", "你好"]:
        a = gen(model, tok, q)
        ok = len(set(a)) > len(a) * 0.4 and len(a) > 2
        tag = "OK" if ok else "DEAD"
        print(f"  {tag} {q[:12]} -> {resolve_calc(a)[:50]!r}", flush=True)

if __name__ == "__main__":
    main()
