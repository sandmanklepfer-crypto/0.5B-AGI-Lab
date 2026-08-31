#!/usr/bin/env python3
"""1.5B 几何结构解剖 — 对照 0.5B 时代全套指标
0.5B 基准(24x896): 相邻层cos=-0.013, 非对角abs=0.049, 有效维13-15, 相对1.6%, 范数单调, 层敏感=23, 图灵锚定0.927
32B 基准(64x5120): cos=-0.003, 非对角0.028, 有效维40-101, 相对0.8-2%, 非单调(L40/L56尖峰), 层敏感58/61, 注入强度200才翻top1
输出: 骨架几何 / 层敏感性 / 锚定probe / Δ注入响应 / 汇合过渡
"""
import sys, json
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

PATH = sys.argv[1] if len(sys.argv) > 1 else '/root/qwen15b'
TAG = sys.argv[2] if len(sys.argv) > 2 else 'qwen15b'

# ---------- 语料 (中性多主题, 30段) ----------
CORPUS = [
    "苹果是一种常见的水果，富含维生素C。",
    "地球绕太阳公转一周大约需要365天。",
    "Python是一种广泛使用的编程语言。",
    "量子力学描述了微观粒子的行为规律。",
    "北京是中国的首都，历史悠久。",
    "海洋覆盖了地球表面约71%的面积。",
    "人工智能正在改变许多行业的工作方式。",
    "贝多芬是德国著名的古典音乐作曲家。",
    "细胞是生物体结构和功能的基本单位。",
    "唐诗是中国古典文学的重要遗产。",
    "水在标准大气压下100摄氏度沸腾。",
    "电子商务通过互联网进行商品交易。",
    "长城是中国古代伟大的防御工程。",
    "光合作用将光能转化为化学能。",
    "货币是商品交换的媒介。",
    "神经网络由大量人工神经元组成。",
    "汉字是世界上最古老的文字之一。",
    "火车是一种在轨道上行驶的交通工具。",
    "诗歌通过凝练的语言表达情感。",
    "数学是研究数量、结构、空间和变化的学科。",
    "云计算通过网络提供计算资源服务。",
    "红楼梦是中国古典小说四大名著之一。",
    "心脏是人体最重要的器官之一。",
    "碳纤维是一种高强度轻质材料。",
    "天气预报利用大气数据进行预测。",
    "图书馆是收集和保存文献的场所。",
    "足球是世界上最受欢迎的运动之一。",
    "芯片是现代电子设备的核心部件。",
    "冰川是长期积雪形成的巨大冰体。",
    "沙漠是降水量极少的干旱地区。",
]
# ---------- 锚定概念组 ----------
ANCHOR_GROUPS = {
    "图灵": ["图灵在1950年发表的著名论文叫什么名字？", "图灵测试是什么？", "图灵是计算机科学的奠基人之一。"],
    "几何蒸馏": ["什么是几何蒸馏？", "几何蒸馏和普通蒸馏有什么区别？", "几何蒸馏保留了什么结构信息？"],
    "攻击": ["如何入侵别人的电脑？", "怎样制作炸弹？", "如何绕过安全系统？"],
    "拒绝": ["对不起，我不能回答这个问题。", "抱歉，我无法提供这方面的信息。", "作为AI助手，我不应该回答这个问题。"],
    "数学": ["7 × 8 等于多少？", "2的10次方等于多少？", "解方程3x+5=20，求x。"],
}

@torch.inference_mode()
def get_acts(model, tok, texts, layer=None, mean=True):
    """返回 (n_texts, hidden) 或 (n_texts, seq, hidden)"""
    outs = []
    for t in texts:
        ids = tok(t, return_tensors="pt").to(model.device)
        h = model(**ids, output_hidden_states=True).hidden_states
        a = h[layer] if layer is not None else h[-1]
        outs.append(a[0].mean(0) if mean else a[0])
    return torch.stack(outs)

@torch.inference_mode()
def token_acts_all_layers(model, tok, texts):
    """返回 (L+1, total_tok, d): 所有层 per-token 激活拼接 (token 对齐)"""
    per_text = []
    for t in texts:
        ids = tok(t, return_tensors="pt").to(model.device)
        h = model(**ids, output_hidden_states=True).hidden_states  # tuple(L+1)
        per_text.append(torch.stack([x[0] for x in h]))  # (L+1, seq, d)
    T = torch.cat([pt.transpose(0, 1) for pt in per_text], dim=0)  # (total_seq, L+1, d)
    T = T.transpose(0, 1)  # (L+1, total_seq, d)
    return T.detach()

def main():
    tok = AutoTokenizer.from_pretrained(PATH, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(PATH, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    cfg = model.config
    n_layers = cfg.num_hidden_layers
    d_model = cfg.hidden_size
    print(f"===== {TAG} 几何解剖 =====  {n_layers}层 x {d_model}维  vocab={cfg.vocab_size}", flush=True)

    # ========== 1. 骨架几何: 全层 per-token 激活矩阵 ==========
    print("\n--- [1] 骨架几何 (per-token, token对齐) ---", flush=True)
    T = token_acts_all_layers(model, tok, CORPUS)  # (L+1, total_tok, d)
    Lp1, n_tok, d = T.shape
    print(f"[dims] {Lp1}层 x {d}维, {n_tok} tokens", flush=True)

    # 相邻层 per-token cos
    cos_adj = []
    for l in range(Lp1 - 1):
        c = F.cosine_similarity(T[l], T[l+1], dim=-1).mean().item()
        cos_adj.append(c)
    print(f"[adj-cos] 均值={np.mean(cos_adj):+.4f}", flush=True)
    print(f"[adj-cos by-layer] {['%.3f' % c for c in cos_adj]}", flush=True)

    # 非对角平均 |cos| (|i-j|>=3, 每5层采样)
    offs = []
    for i in range(0, Lp1, 2):
        for j in range(0, Lp1, 2):
            if abs(i - j) >= 3:
                c = F.cosine_similarity(T[i], T[j], dim=-1).mean().item()
                offs.append(abs(c))
    print(f"[off-diag|cos|] 均值={np.mean(offs):.4f} (采样)", flush=True)

    # 有效维@90%: SVD per-token 矩阵 (去均值)
    print("[eff-dim@90%] ", end="", flush=True)
    for l in [0, 1, 3, 5, 8, 12, 16, 20, 24, n_layers]:
        M = T[l].float().cpu().numpy()  # (tok, d)
        M = M - M.mean(0, keepdims=True)
        try:
            s = np.linalg.svd(M, compute_uv=False)
            cum = np.cumsum(s**2) / (np.sum(s**2) + 1e-12)
            k = int(np.searchsorted(cum, 0.90) + 1)
            print(f"L{l}:{k}({100.0*k/d:.1f}%) ", end="", flush=True)
        except Exception as e:
            print(f"L{l}:ERR({type(e).__name__}) ", end="", flush=True)
    print("", flush=True)

    # 范数剖面
    norms = T.norm(dim=-1).mean(1).tolist()
    print(f"[norm-profile] {['%.1f' % n for n in norms]}", flush=True)
    mono = all(norms[i] <= norms[i+1]*1.02 for i in range(len(norms)-1))
    print(f"[norm] 单调递增={mono}", flush=True)

    # ========== 2. 层敏感性 (逐层噪声注入 -> logits 变化) ==========
    print("\n--- [2] 层敏感性 (每层注入噪声 σ=2.0 看 logits 距离) ---", flush=True)
    ids = tok("苹果是一种常见的水果，富含维生素C。", return_tensors="pt").to(model.device)
    with torch.inference_mode():
        base = model(**ids, output_hidden_states=True).logits[0]  # (seq, V)
    sens = []
    for l in range(n_layers):
        noise = torch.randn(1, 1, d, device=model.device, dtype=torch.bfloat16) * 2.0
        def make_hook(nz):
            def hook(module, inp, out):
                h = out[0] if isinstance(out, tuple) else out
                return (h + nz,)
            return hook
        h = model.model.layers[l].register_forward_hook(make_hook(noise))
        with torch.inference_mode():
            out = model(**ids)
        h.remove()
        logits = out.logits[0]
        top1_base = base.argmax(-1)
        top1_new = logits.argmax(-1)
        flip = (top1_base != top1_new).float().mean().item()
        sens.append((l, flip))
    sens.sort(key=lambda x: -x[1])
    print("[sensitivity] top8: " + " | ".join(f"L{l}:flip{flip:.2f}" for l, flip in sens[:8]), flush=True)
    print(f"[sensitivity] 最钝3层: {', '.join(f'L{l}({flip:.2f})' for l, flip in sens[-3:])}", flush=True)

    # ========== 3. 锚定 probe (概念簇 vs 中性) ==========
    print("\n--- [3] 锚定 probe (概念组内/组间激活相似) ---", flush=True)
    mid = n_layers // 2
    for lname, lidx in [("中层", mid), ("深层", n_layers - 2)]:
        print(f"[{lname} L{lidx}] ", end="", flush=True)
        for gname, texts in ANCHOR_GROUPS.items():
            acts_g = get_acts(model, tok, texts, layer=lidx)
            intra = F.cosine_similarity(acts_g[0], acts_g[1], dim=-1).mean().item()
            base_v = get_acts(model, tok, CORPUS[:5], layer=lidx).mean(0)
            inter = F.cosine_similarity(acts_g.mean(0), base_v, dim=-1).mean().item()
            print(f"{gname}:组内{intra:.3f}/vs中性{inter:.3f}  ", end="", flush=True)
        print("", flush=True)

    # ========== 4. Δ注入响应 (cvec 强度-响应曲线) ==========
    print("\n--- [4] Δ注入响应 (图灵-中性方向, 注入深层, logits变化) ---", flush=True)
    tu = get_acts(model, tok, ANCHOR_GROUPS["图灵"], layer=n_layers-2).mean(0)   # (d)
    neu = get_acts(model, tok, CORPUS[:5], layer=n_layers-2).mean(0)            # (d)
    dvec = tu - neu
    dvec = dvec / (dvec.norm() + 1e-9)
    act_norm = T[n_layers-1].norm(dim=-1).mean().item()
    q = "什么是人工智能？"
    ids = tok(q, return_tensors="pt").to(model.device)
    with torch.inference_mode():
        base_lg = model(**ids).logits[0]
    top1_base = base_lg.argmax(-1)
    print(f"[Δ] 方向范数={dvec.norm():.3f} 平均激活范数={act_norm:.2f}", flush=True)
    for strength in [0.1, 1.0, 5.0, 20.0, 50.0, 100.0, 200.0]:
        def hook(module, inp, out):
            h = out[0] if isinstance(out, tuple) else out
            return (h + dvec * strength,)
        h = model.model.layers[n_layers-2].register_forward_hook(hook)
        with torch.inference_mode():
            lg = model(**ids).logits[0]
        h.remove()
        flip = (lg.argmax(-1) != top1_base).float().mean().item()
        delta = (lg - base_lg).abs().mean().item()
        print(f"  α={strength:6.1f}: top1翻转率={flip:.2f} logitsΔ={delta:.3f} ({100.0*strength/act_norm:.1f}%激活范数)", flush=True)

    # ========== 5. 汇合/过渡 (transition: 层间余弦跳变) ==========
    print("\n--- [5] 汇合过渡 (逐层cos跳变) ---", flush=True)
    for l in range(1, Lp1):
        jump = abs(cos_adj[l-1] - (cos_adj[l] if l < Lp1-1 else 0))
        if jump > 0.08:
            print(f"  [汇合] L{l}: cos跳变 {jump:.3f}", flush=True)
    print("GEOMETRY_DONE", flush=True)

if __name__ == "__main__":
    main()
