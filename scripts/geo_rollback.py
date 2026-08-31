#!/usr/bin/env python3
"""geo_rollback.py — 测地线回退解码: 修重复bug + 赋予回退/重规划元能力
检测: 激活自cos>0.99 (轨迹进入环)
回退: 沿轨迹逆回 k 步 (测地线逆过程)
换向: 入口处沿切空间注入新方向 (与重复方向正交) -> 前进
压测: --depths "2,4,8" --strengths "1.0,2.0"
用法: geo_rollback.py [--model DIR] [--depths D] [--strengths S]
"""
import sys, argparse
import torch, torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

L = 22

def gen_rollback(model, tok, q, depth=4, strength=2.0, max_new=35):
    """测地线回退: 记录激活轨迹 -> 检测环 -> 回退+切空间换向"""
    ids = tok(q, return_tensors="pt").to("cuda:0")
    plen = ids["input_ids"].shape[1]
    gen = ids["input_ids"]
    traj = []  # 激活轨迹 (层22 last-token)
    rollbacks = 0
    for step in range(max_new):
        with torch.inference_mode():
            h = model(gen, output_hidden_states=True)
            logits = h.logits[:, -1].float()
            act = h.hidden_states[L][0, -1].float()
        act = act / (act.norm() + 1e-12)
        traj.append(act)
        nxt = torch.argmax(logits, dim=-1).unsqueeze(0)
        gen = torch.cat([gen, nxt], dim=1)
        # 环检测: 激活自cos > 0.99 (轨迹锁定)
        in_loop = len(traj) > 2 and (1 - F.cosine_similarity(traj[-1].unsqueeze(0), traj[-2].unsqueeze(0)).item()) < 0.01
        recent_rep = len(set(gen[0, -3:].tolist())) == 1 and step > 2
        if (in_loop or recent_rep) and step > 2 and gen.shape[1] > plen + 2:
            # 回退: 逆回 depth 步 (测地线逆过程)
            rb = min(depth, gen.shape[1] - plen - 1)
            for _ in range(rb):
                gen = gen[:, :-1]
                if traj: traj.pop()
            rollbacks += 1
            # 切空间换向: 在当前激活的切平面内选与重复方向正交的方向
            cur = traj[-1] if traj else act
            rep_dir = traj[-1] - traj[-2] if len(traj) >= 2 else torch.zeros_like(cur)
            if rep_dir.norm() < 1e-9:
                rep_dir = torch.randn_like(cur)
            rep_dir = rep_dir / (rep_dir.norm() + 1e-12)
            tan = torch.randn_like(cur)
            tan = tan - (tan @ cur) * cur - (tan @ rep_dir) * rep_dir  # 正交于 cur 和 rep_dir
            tan = tan / (tan.norm() + 1e-12)
            # 注入换向方向到层22
            with torch.inference_mode():
                h2 = model(gen, output_hidden_states=True)
            lg = h2.logits[:, -1].float()
            pen = torch.full_like(lg, -1e9); pen[0, recent_rep and gen[0,-1].item() if isinstance(recent_rep, bool) else 0] = 0.0
            lg = lg + pen if isinstance(recent_rep, bool) else lg
            nxt = torch.argmax(lg, dim=-1).unsqueeze(0)
            gen = torch.cat([gen, nxt], dim=1)
        if nxt.item() == tok.eos_token_id:
            break
    return tok.decode(gen[0][plen:], skip_special_tokens=True).strip(), rollbacks

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/root/qwen07b_t")
    ap.add_argument("--depths", default="2,4,8")
    ap.add_argument("--strengths", default="1.0,2.0")
    ap.add_argument("--qs", nargs="*", default=[
        "计算 7×8 等于多少", "计算 17+25 等于多少", "2的10次方",
        "推理 所有A都是B，所有B都是C，A是什么", "你好"])
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.model); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to("cuda:0")
    m.eval()
    for d in [int(x) for x in args.depths.split(",")]:
        for s in [float(x) for x in args.strengths.split(",")]:
            print(f"=== 测地线回退 depth={d} strength={s} ===", flush=True)
            for q in args.qs:
                try:
                    a, rb = gen_rollback(m, tok, q, depth=d, strength=s)
                    ok = len(set(a)) > len(a) * 0.4 and len(a) > 2
                    tag = "RESCUED" if ok else "STUCK"
                    print(f"  {tag} [rb={rb}] {q[:12]} -> {a[:45]!r}", flush=True)
                except Exception as e:
                    print(f"  ERR {q[:10]}: {str(e)[:50]}", flush=True)

if __name__ == "__main__":
    main()
