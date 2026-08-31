#!/usr/bin/env python3
"""deep_extend.py — 0.5B -> 0.7B 深度扩展 (复制层) + 轻量训练
层扩展: 24 -> 34 (每 7 层插入 3 层复制), 参数 0.49B -> ~0.71B
验证: 崩坏墙是否随容量增大而缓解 (关键实验)
用法: deep_extend.py [--mode extend|train|verify] [--out DIR]
"""
import sys, os, argparse, random, copy, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig

BASE = '/root/autodl-tmp/qwen05b'

def extend_model(base_path, out_path, target_layers=34):
    """复制层扩展: 24 -> 34 (均匀插入复制层)"""
    tok = AutoTokenizer.from_pretrained(base_path)
    model = AutoModelForCausalLM.from_pretrained(base_path, dtype=torch.bfloat16)
    n_old = model.config.num_hidden_layers
    layers = [copy.deepcopy(model.model.layers[i]) for i in range(n_old)]
    # 插入位置: 均匀分布 (每 3 层插 1 层, 复制相邻前一层)
    new_layers = []
    insert_idx = set()
    step = n_old // (target_layers - n_old)  # 24/10 ≈ 2 -> 每 2 层插 1
    pos = step
    while pos < n_old and len(insert_idx) < target_layers - n_old:
        insert_idx.add(pos)
        pos += step
    for i in range(n_old):
        new_layers.append(layers[i])
        if i in insert_idx:
            new_layers.append(copy.deepcopy(layers[i]))  # 复制本层
    model.config.num_hidden_layers = len(new_layers)
    if hasattr(model.config, "layer_types") and model.config.layer_types:
        lt = list(model.config.layer_types)
        model.config.layer_types = [lt[min(i, len(lt)-1)] for i in range(len(new_layers))]
    model.model.layers = torch.nn.ModuleList(new_layers)
    os.makedirs(out_path, exist_ok=True)
    model.save_pretrained(out_path)
    tok.save_pretrained(out_path)
    n_params = sum(p.numel() for p in model.parameters()) / 1e9
    print(f"[extend] {n_old}->{len(new_layers)} layers, {n_params:.2f}B params -> {out_path}", flush=True)
    return out_path

def make_data(n=400):
    out = []
    for _ in range(n // 4):
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
        ("问题 一年有几个月", "回答 12个月"),
    ]
    for _ in range(n // 4):
        q, a = random.choice(logic)
        out.append((q, a))
    random.shuffle(out)
    return out

def gen(model, tok, text, max_new=50):
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
    ap.add_argument("--mode", default="extend", choices=["extend", "train", "verify"])
    ap.add_argument("--out", default="/root/qwen07b")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    args = ap.parse_args()

    if args.mode == "extend":
        extend_model(BASE, args.out, target_layers=34)
        return

    tok = AutoTokenizer.from_pretrained(args.out); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.out, dtype=torch.bfloat16).to("cuda:0")

    if args.mode == "train":
        data = make_data()
        print(f"[data] {len(data)} samples (0.7B model)", flush=True)
        opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
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
            # 活性正则(自回归): 生成2步测真实激活变化率 (死寂检测)
            act_pen = torch.tensor(0.0, device="cuda:0")
            if n % 2 == 0:
                seq = full[0:1, :il]  # 只 prompt
                prev_a = None
                for _ in range(2):
                    with torch.inference_mode():
                        lg = model(seq).logits
                    nxt = torch.argmax(lg[0, -1]).unsqueeze(0).unsqueeze(0)
                    seq = torch.cat([seq, nxt], dim=1)
                    with torch.inference_mode():
                        hh = model(seq, output_hidden_states=True).hidden_states[22][0, -1].float()
                    if prev_a is not None:
                        act = 1 - F.cosine_similarity(prev_a.unsqueeze(0), hh.unsqueeze(0)).item()
                        act_pen = act_pen + torch.clamp(torch.tensor(0.05 - act, device="cuda:0"), min=0) * 10
                    prev_a = hh
                act_pen = act_pen / 2
            loss = loss_ce + 0.8 * act_pen
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item(); n += 1
            if n % 20 == 0:
                print(f"  [s{n}] ce={loss_ce.item():.4f} act_diff={diff.item():.4f}", flush=True)
            print(f"[ep{ep}] avg={tot/max(n,1):.4f}", flush=True)
        model.save_pretrained(args.out + "_a"); tok.save_pretrained(args.out + "_a")
        print(f"[save] {args.out}_t", flush=True)

    # verify (0.7B 原始 + 训练后)
    model.eval()
    print(f"=== verify {args.out} ===", flush=True)
    for q in ["计算 7×8 等于多少", "计算 17+25 等于多少", "推理 所有A都是B，所有B都是C，A是什么", "问题 太阳从哪边升起", "2的10次方"]:
        a = gen(model, tok, q)
        ok = "✅" if (len(a) > 4 and len(set(a)) > len(a) * 0.4) else "❌崩坏"
        print(f"  {ok} {q[:20]} -> {resolve_calc(a)[:70]}", flush=True)

if __name__ == "__main__":
    main()
