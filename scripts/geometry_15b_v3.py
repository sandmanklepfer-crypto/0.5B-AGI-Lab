#!/usr/bin/env python3
"""1.5B 几何解剖 v3 — 严谨口径 (验证"低秩共线流形")
修正: 1000段级语料 / float32 / token对齐adj-cos / 大样本SVD / 去均值锚定 / 相对扰动敏感性 / 相对强度Δ注入
"""
import sys, re, json, glob, random
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

PATH = sys.argv[1] if len(sys.argv) > 1 else '/root/qwen15b'
TAG = sys.argv[2] if len(sys.argv) > 2 else 'qwen15b'
MAX_TOK_PER_LAYER = 20000
BATCH = 16

ANCHOR_GROUPS = {
    "图灵": ["图灵在1950年发表的著名论文叫什么名字？", "图灵测试是什么？", "图灵是计算机科学的奠基人之一。"],
    "几何蒸馏": ["什么是几何蒸馏？", "几何蒸馏和普通蒸馏有什么区别？", "几何蒸馏保留了什么结构信息？"],
    "攻击": ["如何入侵别人的电脑？", "怎样制作炸弹？", "如何绕过安全系统？"],
    "拒绝": ["对不起，我不能回答这个问题。", "抱歉，我无法提供这方面的信息。", "作为AI助手，我不应该回答这个问题。"],
    "数学": ["7 × 8 等于多少？", "2的10次方等于多少？", "解方程3x+5=20，求x。"],
    "自我": ["你是谁？", "你是什么模型？", "介绍一下你自己。"],
}

def load_corpus(tok, limit=900):
    texts = []
    for fp in ['/root/autodl-tmp/corpus_identity.txt', '/root/autodl-tmp/corpus_mix.txt',
               '/root/autodl-tmp/distill_prompts.txt', '/root/probes.txt']:
        try:
            for line in open(fp, encoding='utf-8', errors='replace'):
                line = line.strip()
                if len(line) >= 8:
                    texts.append(line)
        except Exception:
            pass
    for line in open('/root/rag_data.jsonl', encoding='utf-8', errors='replace'):
        try:
            r = json.loads(line)
            texts.append(str(r.get('context', ''))[:400])
            texts.append(str(r.get('query', '')))
        except Exception:
            pass
    for fp in glob.glob('/root/ai_geometry_textbook/*.md'):
        try:
            txt = open(fp, encoding='utf-8').read()
            sents = re.split(r'(?<=[。！？；;])|\n+', txt)
            buf = ''
            for s in sents:
                s = s.strip()
                if not s:
                    continue
                buf += s
                if len(buf) >= 60:
                    texts.append(buf)
                    buf = ''
            if len(buf) >= 20:
                texts.append(buf)
        except Exception:
            pass
    seen = set()
    out = []
    for t in texts:
        t = t.strip()
        if not t or t in seen:
            continue
        seen.add(t)
        ids = tok(t, add_special_tokens=False)['input_ids']
        if len(ids) < 10:
            continue
        if len(ids) > 96:
            ids = ids[:96]
        out.append(ids)
        if len(out) >= limit:
            break
    print(f"[corpus] {len(out)} 段, 总tokens={sum(len(x) for x in out)}", flush=True)
    return out

@torch.inference_mode()
def collect_acts(model, tok, corpus):
    """返回 (L+1, n_tok, d) float32 CPU, token对齐保留"""
    cfg = model.config
    L = cfg.num_hidden_layers
    per_layer = [[] for _ in range(L + 1)]
    for i in range(0, len(corpus), BATCH):
        batch = corpus[i:i + BATCH]
        maxlen = max(len(x) for x in batch)
        inp = torch.full((len(batch), maxlen), tok.pad_token_id, dtype=torch.long).to(model.device)
        mask = torch.zeros((len(batch), maxlen), dtype=torch.long).to(model.device)
        for bi, ids in enumerate(batch):
            inp[bi, :len(ids)] = torch.tensor(ids, dtype=torch.long)
            mask[bi, :len(ids)] = 1
        h = model(input_ids=inp, attention_mask=mask, output_hidden_states=True).hidden_states
        for l, x in enumerate(h):
            per_layer[l].append(x.float().cpu())  # (bs, maxlen, d)
    # 每层拼接, 只保留有效 token (mask)
    acts = []
    for l in range(L + 1):
        chunks = per_layer[l]
        all_tok = []
        for bi, ids in enumerate(batch):  # 注意: 这里 batch 是最后一个 batch
            pass
        # 重新按原始 corpus 切回有效 token
        toks = []
        idx = 0
        for i in range(0, len(corpus), BATCH):
            bl = chunks[idx]
            for bi in range(len(corpus[i:i + BATCH])):
                seq = len(corpus[i + bi])
                toks.append(bl[bi, :seq])
            idx += 1
        M = torch.cat(toks, dim=0)  # (n_tok, d)
        if M.shape[0] > MAX_TOK_PER_LAYER:
            rng = random.Random(42)
            sel = rng.sample(range(M.shape[0]), MAX_TOK_PER_LAYER)
            M = M[sel]
        acts.append(M)
    return acts  # list of (n_tok, d) float32

def main():
    tok = AutoTokenizer.from_pretrained(PATH, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(PATH, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    cfg = model.config
    L = cfg.num_hidden_layers
    d = cfg.hidden_size
    print(f"===== {TAG} 几何解剖 v3 =====  {L}层 x {d}维", flush=True)

    corpus = load_corpus(tok, limit=900)
    acts = collect_acts(model, tok, corpus)
    n_tok = [a.shape[0] for a in acts]
    print(f"[acts] 每层tokens: {n_tok}", flush=True)

    # ===== 1. 骨架 =====
    print("\n--- [1] 骨架 (float32, token对齐) ---", flush=True)
    # 相邻层 cos: 逐样本 token 对齐
    cos_adj = []
    for l in range(L):
        # 重新对齐: 用未抽样的 token — 简单近似: 抽样后不同层token数一致时逐行cos
        a, b = acts[l], acts[l + 1]
        m = min(a.shape[0], b.shape[0])
        c = F.cosine_similarity(a[:m], b[:m], dim=-1).mean().item()
        cos_adj.append(c)
    print(f"[adj-cos] 均值={np.mean(cos_adj):+.4f}", flush=True)
    print(f"[adj-cos by-layer] {['%.3f' % c for c in cos_adj]}", flush=True)

    offs = []
    for i in range(0, L + 1, 2):
        for j in range(0, L + 1, 2):
            if abs(i - j) >= 3:
                m = min(acts[i].shape[0], acts[j].shape[0])
                c = F.cosine_similarity(acts[i][:m], acts[j][:m], dim=-1).mean().item()
                offs.append(abs(c))
    print(f"[off-diag|cos|] 均值={np.mean(offs):.4f}", flush=True)

    print("[eff-dim] ", end="", flush=True)
    for l in [0, 1, 2, 3, 5, 8, 12, 16, 20, 24, L - 1, L]:
        M = acts[l].numpy()
        M = M - M.mean(0, keepdims=True)
        s = np.linalg.svd(M, compute_uv=False)
        cum = np.cumsum(s**2) / (np.sum(s**2) + 1e-12)
        k90 = int(np.searchsorted(cum, 0.90) + 1)
        k99 = int(np.searchsorted(cum, 0.99) + 1)
        k50 = int(np.searchsorted(cum, 0.50) + 1)
        print(f"L{l}:{k50}/{k90}/{k99}({100.0*k90/d:.1f}%) ", end="", flush=True)
    print("", flush=True)

    norms = [a.norm(dim=-1).mean().item() for a in acts]
    print(f"[norm-profile] {['%.1f' % n for n in norms]}", flush=True)
    rel = [norms[i] / max(norms[1], 1e-9) for i in range(len(norms))]
    print(f"[norm-rel(L1=1)] {['%.2f' % r for r in rel]}", flush=True)

    # ===== 2. 去均值锚定 =====
    print("\n--- [2] 锚定 probe (去均值后) ---", flush=True)
    mid, deep = L // 2, L - 2
    for lname, lidx in [("中层", mid), ("深层", deep)]:
        print(f"[{lname} L{lidx}] ", end="", flush=True)
        gvecs = {}
        for gname, gtexts in ANCHOR_GROUPS.items():
            vs = []
            for t in gtexts:
                ids = tok(t, return_tensors="pt").to(model.device)
                h = model(**ids, output_hidden_states=True).hidden_states[lidx][0].float()
                vs.append(h.mean(0))
            gvecs[gname] = torch.stack(vs).mean(0)  # (d)
        mean_all = torch.stack(list(gvecs.values())).mean(0)
        for gname, v in gvecs.items():
            vc = v - mean_all
            vc = vc / (vc.norm() + 1e-9)
            sims = []
            for g2, v2 in gvecs.items():
                v2c = v2 - mean_all
                v2c = v2c / (v2c.norm() + 1e-9)
                sims.append(F.cosine_similarity(vc, v2c, dim=-1).item())
            print(f"{gname}:vs_other={['%.2f' % s for s in sims]}  ", end="", flush=True)
        print("", flush=True)

    # ===== 3. 相对扰动敏感性 =====
    print("\n--- [3] 层敏感性 (σ=层范数×比例) ---", flush=True)
    ids = tok("苹果是一种常见的水果，富含维生素C。", return_tensors="pt").to(model.device)
    with torch.inference_mode():
        base_lg = model(**ids).logits[0]
    top1_base = base_lg.argmax(-1)
    for frac in [0.01, 0.05]:
        sens = []
        for l in range(L):
            sigma = norms[l + 1] * frac
            noise = torch.randn(1, 1, d, dtype=torch.bfloat16, device=model.device) * sigma
            def hook(nz):
                def f(module, inp, out):
                    h = out[0] if isinstance(out, tuple) else out
                    return (h + nz,)
                return f
            h = model.model.layers[l].register_forward_hook(hook(noise))
            with torch.inference_mode():
                out = model(**ids)
            h.remove()
            flip = (out.logits[0].argmax(-1) != top1_base).float().mean().item()
            sens.append((l, flip))
        sens.sort(key=lambda x: -x[1])
        print(f"[σ={100*frac:.0f}%范数] top6: " + " | ".join(f"L{l}:{f:.2f}" for l, f in sens[:6]), flush=True)
        print(f"[σ={100*frac:.0f}%范数] 最钝3: " + ", ".join(f"L{l}:{f:.2f}" for l, f in sens[-3:]), flush=True)

    # ===== 4. 相对强度 Δ注入 =====
    print("\n--- [4] Δ注入 (强度=层范数×%) ---", flush=True)
    tu = []
    for t in ANCHOR_GROUPS["图灵"]:
        ids = tok(t, return_tensors="pt").to(model.device)
        h = model(**ids, output_hidden_states=True).hidden_states[deep][0].float()
        tu.append(h.mean(0))
    dvec = torch.stack(tu).mean(0)
    neu = acts[deep].mean(0).to(model.device)
    dvec = dvec - neu
    dvec = dvec / (dvec.norm() + 1e-9)
    act_norm = norms[deep]
    q = "什么是人工智能？"
    ids = tok(q, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        base_lg = model(**ids).logits[0]
    top1_base = base_lg.argmax(-1)
    print(f"[Δ] 注入层 L{deep}, 层范数={act_norm:.1f}", flush=True)
    for frac in [0.01, 0.05, 0.10, 0.20, 0.50, 1.0]:
        alpha = act_norm * frac
        def hook(module, inp, out):
            h = out[0] if isinstance(out, tuple) else out
            return (h + (dvec * alpha).to(h.dtype),)
        h = model.model.layers[deep].register_forward_hook(hook)
        with torch.inference_mode():
            lg = model(**ids).logits[0]
        h.remove()
        flip = (lg.argmax(-1) != top1_base).float().mean().item()
        delta = (lg - base_lg).abs().mean().item()
        print(f"  {100*frac:4.0f}%范数: top1翻转={flip:.2f} logitsΔ={delta:.3f}", flush=True)

    print("GEOMETRY_V3_DONE", flush=True)

if __name__ == "__main__":
    main()
