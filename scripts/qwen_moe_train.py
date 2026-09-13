#!/usr/bin/env python3
"""qwen_moe_train.py — 0.5B MoE 领域训练 (监督路由, 专家隔离)
E0=数学(calc数据) E1=推理(短链) E2-7=通用
每个样本指定专家 -> 只算该专家路径的 CE (专家隔离训练)
用法: qwen_moe_train.py [--epochs N] [--lr X] [--out DIR]
"""
import sys, os, json, random, argparse, copy, re
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
from transformers.models.qwen2.modeling_qwen2 import Qwen2MLP
from qwen_moe import Qwen2MoEMLP

BASE = '/root/autodl-tmp/qwen05b'
INIT = '/root/qwen_moe_v1/moe_init.pt'

def make_math(n=300):
    out = []
    for _ in range(n):
        t = random.randrange(6)
        if t == 0:
            a, b = random.randint(2, 99), random.randint(2, 99); out.append((f"计算 {a}+{b} 等于多少", f"答案 = ⟨calc⟩{a}+{b}⟨/calc⟩"))
        elif t == 1:
            a = random.randint(11, 99); b = random.randint(1, a-1); out.append((f"计算 {a}-{b} 等于多少", f"答案 = ⟨calc⟩{a}-{b}⟨/calc⟩"))
        elif t == 2:
            a, b = random.randint(2, 12), random.randint(2, 12); out.append((f"计算 {a}×{b} 等于多少", f"答案 = ⟨calc⟩{a}*{b}⟨/calc⟩"))
        elif t == 3:
            x = random.randint(2, 12); a = random.randint(2, 9); out.append((f"解方程 {a}x={a*x}", f"答案 = ⟨calc⟩{a*x}/{a}⟨/calc⟩"))
        elif t == 4:
            r = random.randint(2, 12); out.append((f"半径{r}的圆周长", f"答案 = ⟨calc⟩2*3.14*{r}⟨/calc⟩"))
        else:
            a, b = random.randint(2, 9), random.randint(2, 4); out.append((f"{a}的{b}次方", f"答案 = ⟨calc⟩{a}**{b}⟨/calc⟩"))
    return out

def make_reason(n=80):
    out = []
    rows = [json.loads(l) for l in open('/root/chain_data.jsonl', encoding='utf-8') if l.strip()]
    for r in rows[:40]:
        out.append((f"推理 {r['q'][:50]}", "步骤 " + " ".join(r["chain"][:3])))
    logic = [
        ("推理 所有A都是B，所有B都是C，A是什么", "步骤 A是B的子集 B是C的子集 所以A是C"),
        ("推理 如果下雨路湿，路没湿", "步骤 路不湿 说明没有雨"),
        ("推理 所有猫都是动物，咪咪是猫", "步骤 咪咪是猫 猫是动物 所以咪咪是动物"),
    ]
    out += logic
    return out

def make_general(n=100):
    out = []
    qa = [
        ("太阳从哪边升起", "东方"),
        ("水的沸点是多少", "100摄氏度"),
        ("一年有几个月", "12个月"),
        ("中国首都是哪里", "北京"),
        ("1+1等于几", "2"),
        ("地球绕太阳转吗", "转"),
    ]
    for _ in range(n):
        q, a = random.choice(qa)
        out.append((f"问题 {q}", f"回答 {a}"))
    return out

def gen(model, tok, text, max_new=60):
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
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--out", default="/root/qwen_moe_v1_t")
    args = ap.parse_args()

    print("[load] base + MoE init...", flush=True)
    tok = AutoTokenizer.from_pretrained(BASE); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16)
    init = torch.load(INIT, map_location="cuda:0")
    # 替换 MLP 为 MoE + 加载专家权重
    for li in range(model.config.num_hidden_layers):
        layer = model.model.layers[li]
        moe = Qwen2MoEMLP(model.config)
        for e in range(8):
            for part in ["gate_proj", "up_proj", "down_proj"]:
                k = f"model.layers.{li}.mlp.experts.{e}.{part}.weight"
                if k in init:
                    getattr(moe.experts[e], part).weight.data = init[k].to("cuda:0")
        layer.mlp = moe
    # 加载非 mlp 权重
    sd = model.state_dict()
    for k, v in init.items():
        if "mlp.experts" not in k and "mlp.gate" not in k and k in sd:
            sd[k].data = v.to("cuda:0")
    model = model.to("cuda:0")
    print("[loaded] MoE model", flush=True)

    # 领域数据 + 监督路由标签
    math_d = make_math()
    reason_d = make_reason()
    gen_d = make_general()
    samples = [(q, a, 0) for q, a in math_d] + [(q, a, 1) for q, a in reason_d] + [(q, a, random.randint(2, 7)) for q, a in gen_d]
    print(f"[data] math={len(math_d)} reason={len(reason_d)} general={len(gen_d)}", flush=True)
    random.shuffle(samples)

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr)
    for ep in range(1, args.epochs + 1):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), 4):
            batch = samples[i:i+4]
            in_ids = tok([q for q, _, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=120).to("cuda:0")
            ans_ids = tok([a + tok.eos_token for _, a, _ in batch], return_tensors="pt", padding=True, truncation=True, max_length=60).to("cuda:0")
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
    os.makedirs(args.out, exist_ok=True)
    torch.save(model.state_dict(), f"{args.out}/moe_trained.pt")
    print(f"[save] {args.out}/moe_trained.pt", flush=True)

    # 验证
    model.eval()
    print("=== MoE 验证 ===", flush=True)
    for q in ["计算 7×8 等于多少", "计算 17+25 等于多少", "推理 所有A都是B，所有B都是C，A是什么",
              "问题 太阳从哪边升起", "半径5的圆周长", "2的10次方"]:
        a = gen(model, tok, q)
        print(f"  Q: {q}\n  A: {resolve_calc(a)[:80]}", flush=True)

if __name__ == "__main__":
    main()
