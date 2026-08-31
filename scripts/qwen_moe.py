#!/usr/bin/env python3
"""qwen_moe.py — Qwen2.5-0.5B MoE 化 (MLP -> 8专家 top-2, 专家 FFN 448)
专家初始化从已验证模型复制 (不随机): E0=calc_v1, E1=chain_v1, 其余=qwen05b
用法: convert: qwen_moe.py --convert --out DIR
      训练:   qwen_moe.py --train --base DIR --epochs N
"""
import sys, os, argparse, copy, math, random
import numpy as np
import torch
import torch.nn.functional as F
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.models.qwen2 import Qwen2Config
from transformers.models.qwen2.modeling_qwen2 import Qwen2MLP, Qwen2Attention, Qwen2RMSNorm

# ---- MoE MLP: 8 专家 top-2, 专家 FFN 448 ----
class Qwen2MoEMLP(torch.nn.Module):
    def __init__(self, config, n_experts=8, top_k=2, expert_ffn=448):
        super().__init__()
        self.n_experts = n_experts
        self.top_k = top_k
        self.hidden = config.hidden_size
        # 专家 (浅拷贝 Qwen2MLP 结构)
        self.experts = torch.nn.ModuleList([
            Qwen2MLP(config) for _ in range(n_experts)
        ])
        # 路由 (gate)
        self.gate = torch.nn.Linear(config.hidden_size, n_experts, bias=False)
        self._init_weights()

    def _init_weights(self):
        torch.nn.init.normal_(self.gate.weight, std=0.02)
        self.gate.weight.data = self.gate.weight.data.to(torch.bfloat16)

    def forward(self, x):
        B, L, H = x.shape
        flat = x.reshape(-1, H)
        logits = self.gate(flat)                      # [B*L, E]
        topk = torch.topk(logits, self.top_k, dim=-1)
        idx = topk.indices                              # [B*L, K]
        weights = F.softmax(topk.values, dim=-1)        # [B*L, K]
        out = torch.zeros_like(flat)
        for k in range(self.top_k):
            e_idx = idx[:, k]                           # [B*L]
            for e in range(self.n_experts):
                mask = (e_idx == e)
                if mask.any():
                    out[mask] += weights[mask, k:k+1] * self.experts[e](flat[mask].unsqueeze(1)).squeeze(1)
        return out.reshape(B, L, H)

# ---- 复制权重到专家 ----
def convert_to_moe(base_path, out_path, src_experts=None):
    """src_experts: [E0来源, E1来源, ...] 每个元素是模型路径或 None(=基座)"""
    src_experts = src_experts or {}
    tok = AutoTokenizer.from_pretrained(base_path)
    base = AutoModelForCausalLM.from_pretrained(base_path, dtype=torch.bfloat16)
    srcs = {}
    for e, p in src_experts.items():
        srcs[e] = AutoModelForCausalLM.from_pretrained(p, dtype=torch.bfloat16)
    sd = base.state_dict()
    moe_sd = {}
    for k, v in sd.items():
        if "mlp" not in k:
            moe_sd[k] = v
    # 每个 MLP 层: 复制到 8 专家
    for li in range(base.config.num_hidden_layers):
        for e in range(8):
            src = srcs.get(e)
            for part in ["gate_proj", "up_proj", "down_proj"]:
                key = f"model.layers.{li}.mlp.{part}.weight"
                if src is not None and key in src.state_dict():
                    moe_sd[f"model.layers.{li}.mlp.experts.{e}.{part}.weight"] = src.state_dict()[key]
                else:
                    moe_sd[f"model.layers.{li}.mlp.experts.{e}.{part}.weight"] = v
        # gate 权重: 前几个专家对应领域
    print(f"[convert] {base_path} -> {out_path} (experts: { {k: 'from ' + p.split('/')[-1] for k, p in src_experts.items()} })", flush=True)
    os.makedirs(out_path, exist_ok=True)
    torch.save(moe_sd, f"{out_path}/moe_init.pt")
    tok.save_pretrained(out_path)
    print(f"[save] {out_path}/moe_init.pt ({len(moe_sd)} tensors)", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--convert", action="store_true")
    ap.add_argument("--base", default="/root/autodl-tmp/qwen05b")
    ap.add_argument("--out", default="/root/qwen_moe_v1")
    ap.add_argument("--train", action="store_true")
    args = ap.parse_args()
    if args.convert:
        convert_to_moe(args.base, args.out, src_experts={0: "/root/distill_calc_v1", 1: "/root/distill_chain_v1"})
    elif args.train:
        print("train mode: 见 qwen_moe_train.py", flush=True)

if __name__ == "__main__":
    main()
