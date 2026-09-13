#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V155 殖民第一港 — 扫描千问0.5B星球, 找最可渗透层(殖民登陆点)
可渗透性 = 该层加"干净小扰动"后, 输出语义是否稳定(可塑) + 信息量(纹路密度)
  per-layer: 注入方向扰动(幅度0.02, V81干净修改) → 测logits变化
  → 变化小=刚性(难殖民) 变化大但不崩=可渗透(好殖民点) 变化大到乱码=脆弱(会崩)
输出: 每层 可渗透评分 → 推荐第一港
"""
import torch
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
BASE = '/root/autodl-tmp/qwen25_base_raw'
TEXTS = [
    '春天之后是夏天，夏天之后是秋天。',
    '猫在追老鼠，老鼠跑得快。',
    '我饿了，我要找吃的。',
    '苹果是红色的，香蕉是黄色的。',
    '山很高，河很长。',
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    n_layers = model.config.num_hidden_layers
    dim = model.config.hidden_size
    print('V155 殖民探测 | 层数=%d hidden=%d' % (n_layers, dim), flush=True)
    # 收集每层激活(需要hook) — 用hidden_states
    all_hs = []
    for t in TEXTS:
        ids = tok(t, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model(input_ids=ids, output_hidden_states=True)
        all_hs.append([h[0, -1].float().cpu().numpy() for h in out.hidden_states])  # 每层末token [dim]
    print('评测每层可渗透性...', flush=True)
    results = []
    for layer in range(n_layers):
        # 该层的激活均值(纹路密度/能量)
        acts = np.stack([hs[layer] for hs in all_hs])  # [ntext, dim]
        act_norm = np.mean(np.linalg.norm(acts, axis=-1))  # 激活强度
        # 可渗透性: 在该层注入方向扰动, 看末层logits变化
        # 用 hook 注入 (方向 = 该层激活主方向)
        # 可渗透性: 在该层注入强随机方向扰动(probe验证: 随机方向×5有效)
        rng = np.random.RandomState(layer)
        rand_dir = rng.randn(dim).astype(np.float32)
        rand_dir = rand_dir / (np.linalg.norm(rand_dir) + 1e-9)
        delta = torch.tensor(rand_dir, dtype=torch.float16, device='cuda') * 5.0
        st = {'v': delta, 'eta': 1.0}
        def make_hook():
            def hook(mod, inp, out):
                if st['eta'] > 0:
                    h = out[0] if isinstance(out, tuple) else out  # [b,seq,dim]
                    # 方向注入: 沿 main_dir 推 h (V120式: g=h·v 投影量, 乘v方向)
                    g = torch.matmul(h, st['v'])  # [b,seq] 投影量
                    h = h + st['eta'] * g.unsqueeze(-1) * st['v'].unsqueeze(0).unsqueeze(0)
                    return (h,) if isinstance(out, tuple) else h
                return out
            return hook
        hook = model.model.layers[layer].mlp.register_forward_hook(make_hook())
        # 测扰动后输出分布变化: 无扰动(eta=0) vs 有扰动(eta=1)
        logit_diffs = []
        for t in TEXTS:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            st['eta'] = 0.0
            with torch.no_grad():
                logits_a = model(input_ids=ids).logits[0, -1].float().cpu().numpy()
            st['eta'] = 1.0  # 加扰动
            with torch.no_grad():
                logits_b = model(input_ids=ids).logits[0, -1].float().cpu().numpy()
            # logits变化: 用argmax变化率(probe验证敏感) + top5 softmax差
            pa = torch.softmax(torch.tensor(logits_a), -1).numpy()
            pb = torch.softmax(torch.tensor(logits_b), -1).numpy()
            topa = set(np.argsort(pa)[-5:])
            topb = set(np.argsort(pb)[-5:])
            arg_change = len(topa - topb) / 5.0   # top5 变了几个
            prob_diff = np.abs(pa - pb).max()      # 最大概率差
            diff = max(arg_change, prob_diff)
            logit_diffs.append(diff)
        hook.remove()
        st['eta'] = 0.0
        mean_diff = np.mean(logit_diffs)
        # 可渗透评分: 激活强+扰动响应大且不崩
        # 响应太小(<0.01)=刚性(推不动); 太大(>0.5)=脆弱(一碰就乱)
        if mean_diff < 0.05:
            perm = '刚性(难殖民)'
        elif mean_diff > 0.8:
            perm = '脆弱(会崩)'
        else:
            perm = '可渗透✅'
        results.append((layer, act_norm, mean_diff, perm))
        print('  L%2d | 激活强度=%.1f | 扰动响应=%.3f | %s' % (
            layer, act_norm, mean_diff, perm), flush=True)
    print('\n=== 殖民推荐 ===', flush=True)
    good = [r for r in results if r[3] == '可渗透✅']
    if good:
        best = max(good, key=lambda r: r[1])  # 激活最强(纹路密)的可渗透层
        print('第一港推荐: L%d (激活%.1f 响应%.3f)' % (best[0], best[1], best[2]), flush=True)
    else:
        print('无可渗透层(全刚性或全脆弱), 需降扰动幅度重试', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
