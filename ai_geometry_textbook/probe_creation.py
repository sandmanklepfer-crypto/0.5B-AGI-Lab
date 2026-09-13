#!/usr/bin/env python3
"""probe_creation.py — 技能注入创造的几何: 基座 vs v4b(提取后) 激活差
Δ激活 = v4b - 基座 (注入改变了什么空间)
A. 逐层 Δ 大小 + Δ 的方向结构(公共/差异成分)
B. Δ 的维度分布(哪些维被改)
"""
import torch, torch.nn.functional as F
import numpy as np, struct
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "/workspace/backups_a800/distill_mix_v4b"  # 提取后(会三段论)
TEXTS = {"三段论": "所有的A都是B，所有的B都是C，那么A是什么？", "你好": "你好"}

def load_gguf_acts(path_prefix, n_embd=896):
    """读 dump_layers 输出: 每文本一个 {prefix}_L{NN}.bin? 或每层一个"""
    import glob
    files = sorted(glob.glob(f"{path_prefix}_L*.bin"))
    acts = {}
    for f in files:
        data = open(f, "rb").read()
        nl, ne = struct.unpack_from("<ii", data, 0)
        arr = np.frombuffer(data, dtype=np.float32, count=nl*ne, offset=8).reshape(nl, ne)
        acts[f] = arr
    return acts, files

if __name__ == "__main__":
    tok = AutoTokenizer.from_pretrained(MODEL); tok.pad_token = tok.eos_token
    m = AutoModelForCausalLM.from_pretrained(MODEL)
    m.eval()
    acts_g, files = load_gguf_acts("/tmp/base_act")
    print(f"基座激活文件: {len(files)}, 每文件层数: {next(iter(acts_g.values())).shape[0]}")
    # v4b 激活 (transformers)
    for name, text in TEXTS.items():
        ids = tok(text, return_tensors="pt")
        with torch.inference_mode():
            h = m(**ids, output_hidden_states=True)
        print(f"\n=== {name}: v4b vs 基座 逐层激活差 ===")
        n_layers = m.config.num_hidden_layers
        for li in [0, 4, 8, 12, 16, 20, 22, 23]:
            if li >= len(h.hidden_states): continue
            a_v = h.hidden_states[li][0].mean(0).float().numpy()
            a_v = a_v / (np.linalg.norm(a_v) + 1e-12)
            # 基座对应层 (dump_layers 的层顺序: 0=embed? 1..24?)
            g = acts_g[files[0]] if name == "三段论" else acts_g[files[1]]
            if li < g.shape[0]:
                a_g = g[li]
                a_g = a_g / (np.linalg.norm(a_g) + 1e-12)
                cos = float(np.abs(a_v @ a_g))
                d = a_v - a_g
                dnorm = np.linalg.norm(d)
                # Δ 的方向: 与 v4b 自己激活的 cos (Δ是沿v4b方向还是正交)
                c_dv = float(np.abs(d @ a_v)) / (dnorm + 1e-12)
                depth = li / n_layers * 100
                print(f"  层{li}({depth:.0f}%): cos(v4b,base)={cos:.4f} | Δ范数={dnorm:.4f} | Δ沿v4b方向={c_dv:.3f}")
