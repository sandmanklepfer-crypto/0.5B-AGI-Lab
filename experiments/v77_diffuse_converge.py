#!/usr/bin/env python3
"""V77 隐空间发散-收敛推理 — 架构内建, 不靠文本投票
原理:
 1 问题 → 隐状态 x0 (0.5B 对问题的深层理解)
 2 发散: 对 x0 加多方向扰动/噪声 → 状态扩散 (覆盖多种可能解读)
 3 收敛: 用模型层12的真实变换(能量景观) 把扩散状态拉回谷底
    (每轮: x ← x + α·(模型层对x的变换 - x)  ← 向模型"认为合理"的方向收缩)
 4 迭代 N 轮 发散→收敛 (交替)
 5 用收敛状态 注入生成 → 答案
对比: 直接答 vs 发散-收敛后答
"""
import os, json, time, argparse
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'

QS = [
    ("因果", "因为小猫打翻了花瓶，花瓶碎了；花瓶碎了，水撒了一地。问：为什么地上有水？"),
    ("时序", "先刷牙再洗脸，洗完脸吃早饭。问：刷牙之后先做什么？"),
    ("比较", "大象比马重，马比羊重。问：谁最轻？"),
    ("传递", "A比B高，B比C高，C比D高。问：谁最高？"),
    ("因果2", "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=6, help='发散-收敛迭代轮数')
    ap.add_argument('--noise', type=float, default=0.3, help='发散噪声强度')
    ap.add_argument('--alpha', type=float, default=0.4, help='收敛步长')
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    # 层12 MLP 权重 = 能量景观 (模型认为"合理"的变换)
    W12 = sd['model.layers.12.mlp.gate_proj.weight'].float().to('cuda')
    W13 = sd['model.layers.12.mlp.down_proj.weight'].float().to('cuda')

    def state_of(text):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1].float()
        return h / (h.norm() + 1e-9) * 3.0

    def energy_map(x):
        """模型层12的变换 = 能量景观: 返回模型把x推向的方向"""
        gate = torch.matmul(W12, x)
        act = F.silu(gate)
        out = torch.matmul(W13, act)
        return out  # 模型认为"合理"的下一步方向

    def diffuse_converge(x0, rounds):
        """发散-收敛迭代: 发散(加噪扩散) → 收敛(被能量景观拉回)"""
        x = x0.clone()
        for r in range(rounds):
            # 发散: 加噪 + 多方向微扰 (探索多种可能)
            noise = torch.randn_like(x) * args.noise
            x_d = x + noise
            # 收敛: 被模型能量景观拉回 (向合理方向收缩)
            x_c = x_d + args.alpha * (energy_map(x_d) - x_d)
            # 保幅
            x = x_c / (x_c.norm() + 1e-9) * 3.0
        return x

    # 收敛状态 → 注入生成
    inject = {'v': None}
    def make_inject():
        def hook(mod, inp, out):
            h = out[0]
            if inject['v'] is not None:
                h = h + 0.6 * inject['v'].to(h.dtype).unsqueeze(0)
            return (h,) if isinstance(out, tuple) else h
        return hook
    hk = model.model.layers[12].register_forward_hook(make_inject())

    def gen_answer(q, use_dc):
        if use_dc:
            x0 = state_of(q)
            x_final = diffuse_converge(x0, args.rounds)
            inject['v'] = x_final.to('cuda')
        prompt = f"问：{q}\n答："
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=30, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        inject['v'] = None
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print(f'[V77] 隐空间发散-收敛 (rounds={args.rounds} noise={args.noise})', flush=True)
    t0 = time.time()
    res = []
    for tag, q in QS:
        a0 = gen_answer(q, False)
        a1 = gen_answer(q, True)
        res.append((tag, q, a0, a1))
        print(f'[{tag}]\n  直答: {a0[:45]}\n  发散收敛: {a1[:45]}', flush=True)
    hk.remove()
    print(f'\n[V77 DONE] | {time.time()-t0:.0f}s | 存 v77_results.json', flush=True)
    json.dump(res, open(f'{SAVE}/v77_results.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
