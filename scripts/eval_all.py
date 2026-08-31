#!/usr/bin/env python3
"""eval_all.py — 对比评估: 基座/v4/v4b/rag_v1/geom_v1
指标:
  A. RAG 有context作答 (56题, 答案含数字率)
  B. 无context内化作答 (同query, 含数字率 = 参数内检索迹象)
  C. 几何对齐: 96 probes 距离矩阵 vs R1 D_t 的 RMSE (核心!)
  D. 图灵锚定 (冷门概念锚定保留)
用法: eval_all.py
"""
import json, sys, re, subprocess, argparse
import numpy as np
import torch

sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

MODELS = {
    "v4b": "/root/autodl-tmp/distill_mix_v4b",
    "v4c": "/root/distill_v4c",
}
    "base_qwen05b": "/root/autodl-tmp/qwen05b",
    "v4":           "/root/autodl-tmp/distill_mix_v4",
    "v4b":          "/root/autodl-tmp/distill_mix_v4b",
    "rag_v1":       "/root/autodl-tmp/distill_rag_v1",
    "geom_v1":      "/root/autodl-tmp/distill_geom_v1",
}
S_LAYER = 22

def has_num(t): return bool(re.search(r'\d+', t))

def split_sents(t):
    return [p.strip() for p in re.split(r'(?<=[。！？；;])|\n+', t) if len(p.strip()) >= 4]

@torch.inference_mode()
def sent_acts(model, tok, texts, layer, dev):
    outs = []
    for t in texts:
        sents = split_sents(t) or [t]
        acts = []
        for s in sents:
            ids = tok(s, return_tensors="pt").to(dev)
            h = model(**ids, output_hidden_states=True)
            acts.append(h.hidden_states[layer][0].mean(0))
        outs.append(torch.stack(acts))
    return outs

def gen(model, tok, text, max_new=110):
    ids = tok(text, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    rows = [json.loads(l) for l in open("/root/rag_data.jsonl", encoding="utf-8") if l.strip()]
    probes = [l.strip() for l in open("/root/probes.txt", encoding="utf-8") if l.strip()]
    G = np.load("/root/probe_geom_t.npz")
    D_t = G["D"]
    results = {}
    for name, path in MODELS.items():
        try:
            tok = AutoTokenizer.from_pretrained(path); tok.pad_token = tok.eos_token
            model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.bfloat16).to("cuda:0")
            model.eval()
        except Exception as e:
            print(f"{name}: LOAD FAIL {e}", flush=True); continue
        # A: RAG 有context
        a_ok = 0
        for r in rows[:20]:
            p = f"请阅读下面的文档，然后回答问题。\n\n文档：{r['context'][:400]}\n\n问题：{r['query']}"
            a_ok += has_num(gen(model, tok, p))
        # B: 无context
        b_ok = 0
        for r in rows[:20]:
            b_ok += has_num(gen(model, tok, f"问题：{r['query']}"))
        # C: 几何对齐 (距离矩阵 RMSE)
        acts = sent_acts(model, tok, probes, S_LAYER, "cuda:0")
        A = torch.cat([a for a in acts], dim=0).float().cpu().numpy()
        U, S, Vt = np.linalg.svd(A, full_matrices=False)
        P = Vt[:min(256, A.shape[0])].T
        Ap = A @ P
        Ap = Ap / (np.linalg.norm(Ap, axis=1, keepdims=True) + 1e-12)
        D_s = 1.0 - np.abs(Ap @ Ap.T)
        # 尺寸对齐: D_s 和 D_t 都 [96,96]
        m = min(D_s.shape[0], D_t.shape[0])
        geom_rmse = np.sqrt(((D_s[:m, :m] - D_t[:m, :m]) ** 2).mean())
        # D: 图灵锚定 (概念书名的相关度)
        def anchor(q):
            ids = tok(q, return_tensors="pt").to("cuda:0")
            with torch.inference_mode():
                h = model(**ids, output_hidden_states=True)
            return h.hidden_states[S_LAYER][0].mean(0).float().cpu().numpy()
        v_turing = anchor("图灵在1950年提出了什么著名的测试")
        v_book = anchor("图灵发表的论文《计算机器与智能》")
        v_math = anchor("1+1等于几")
        c_tb = abs(np.dot(v_turing / (np.linalg.norm(v_turing) + 1e-12),
                          v_book / (np.linalg.norm(v_book) + 1e-12)))
        c_tm = abs(np.dot(v_turing / (np.linalg.norm(v_turing) + 1e-12),
                          v_math / (np.linalg.norm(v_math) + 1e-12)))
        results[name] = dict(rag_ctx=a_ok, noctx=b_ok, geom_rmse=round(geom_rmse, 4),
                             turing_sim=round(c_tb, 3), turing_baseline=round(c_tm, 3))
        print(f"{name}: ctx={a_ok}/20 noctx={b_ok}/20 geom_rmse={geom_rmse:.4f} "
              f"turing={c_tb:.3f}(base {c_tm:.3f})", flush=True)
        del model; torch.cuda.empty_cache()
    print("\n=== SUMMARY ===")
    for k, v in results.items():
        print(f"{k:>14}: {v}")

if __name__ == "__main__":
    main()
