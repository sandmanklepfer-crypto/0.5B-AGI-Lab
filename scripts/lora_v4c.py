#!/usr/bin/env python3
"""lora_v4c.py — 容量预算训练: v4c 冻结主权重 + LoRA 小适配器 (1-5% 参数)
格式装进适配器, 主权重保留余量 -> 不死寂 (容量上限框架的正解)
验证: 训练后不崩 + 数学格式学会
用法: lora_v4c.py [--out DIR] [--r RANK] [--epochs N]
"""
import sys, os, random, argparse, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = '/root/distill_v4c'

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
        ("问题 太阳从哪边升起", "回答 东方"),
        ("问题 水的沸点是多少", "回答 100摄氏度"),
    ]
    for _ in range(n // 6):
        q, a = random.choice(logic)
        out.append((q, a))
    random.shuffle(out)
    return out

def gen(model, tok, text, max_new=25):
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
    ap.add_argument("--out", default="/root/distill_v4c_lora")
    ap.add_argument("--r", type=int, default=16, help="LoRA rank (小=容量预算紧)")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=3e-4)
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16).to("cuda:0")
    # 冻结全部主权重
    for p in model.parameters():
        p.requires_grad = False
    # LoRA: 在 q_proj/v_proj 加低秩适配器
    loras = []
    for li in range(model.config.num_hidden_layers):
        for proj in ["o_proj"]:
            layer = model.model.layers[li].self_attn
            orig = getattr(layer, proj)
            h = orig.in_features
            A = torch.nn.Parameter(torch.randn(h, args.r, device="cuda:0", dtype=torch.bfloat16) * 0.01, requires_grad=True)
            B = torch.nn.Parameter(torch.zeros(args.r, h, device="cuda:0", dtype=torch.bfloat16), requires_grad=True)
            layer.register_parameter(f"lora_{proj}_A", A)
            layer.register_parameter(f"lora_{proj}_B", B)
            loras.append((layer, proj, A, B))
    n_train = sum(1 for p in model.parameters() if p.requires_grad)
    n_total = sum(1 for p in model.parameters())
    print(f"[lora] 训练参数 {n_train} / {n_total} 组 ({n_train/n_total*100:.1f}%)", flush=True)
    # 前向时加 LoRA 输出
    orig_forwards = {}
    def make_lora_forward(layer, proj, A, B):
        orig_fwd = getattr(layer, proj).forward
        def fwd(x, *a, **kw):
            y = orig_fwd(x, *a, **kw)
            if x.dim() == 3:
                lora_out = (x @ A @ B)
                return y + lora_out
            return y + (x @ A @ B)
        return fwd
    for layer, proj, A, B in loras:
        orig_forwards[(id(layer), proj)] = getattr(layer, proj).forward
        setattr(getattr(layer, proj), "forward", make_lora_forward(layer, proj, A, B))
    lora_params = [p for l, pr, A, B in loras for p in [A, B]]

    data = make_data()
    print(f"[data] {len(data)} samples", flush=True)
    opt = torch.optim.AdamW(lora_params, lr=args.lr)
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
            loss = ce_all[mask].mean()
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1; step += 1
            if step % 20 == 0:
                print(f"  [s{step}] ce={loss.item():.4f}", flush=True)
        print(f"[ep{ep}] avg={tot/max(n,1):.4f}", flush=True)
    # 保存 LoRA 权重 (主权重不变)
    os.makedirs(args.out, exist_ok=True)
    torch.save({f"{id(layer)}_{proj}_A": A.detach().cpu() for layer, proj, A, B in loras}, f"{args.out}/lora_A.pt")
    torch.save({f"{id(layer)}_{proj}_B": B.detach().cpu() for layer, proj, A, B in loras}, f"{args.out}/lora_B.pt")
    model.save_pretrained(args.out + "_base"); tok.save_pretrained(args.out + "_base")
    print(f"[save] {args.out} (lora + base)", flush=True)

    # 验证 (LoRA 生效状态)
    model.eval()
    print("=== 验证 (v4c+LoRA) ===", flush=True)
    for q in ["计算 7×8 等于多少", "计算 17+25 等于多少", "2的10次方", "推理 所有A都是B，所有B都是C，A是什么", "你好"]:
        a = gen(model, tok, q)
        ok = len(set(a)) > len(a) * 0.4 and len(a) > 2
        tag = "OK" if ok else "DEAD"
        print(f"  {tag} {q[:12]} -> {resolve_calc(a)[:50]!r}", flush=True)

if __name__ == "__main__":
    main()
