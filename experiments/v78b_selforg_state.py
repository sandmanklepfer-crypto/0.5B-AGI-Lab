#!/usr/bin/env python3
"""V78b 自组织状态层 — 发散-收敛完全自组织(无监督无目标)
状态单元挂在 layer12 后, 每次前向自动做:
  发散: 状态 + 小噪声 (探索)
  收敛: 状态被自身递归变换拉回 (自组织稳定化)
迭代K轮 → 状态自然收敛 → 用收敛状态调制生成
无任何"正确答案"监督. 纯看: 自组织收敛后是否对推理有用.
"""
import os, json, time, argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
HS = 896

QS = [
    ("因果", "因为小猫打翻了花瓶，花瓶碎了；水撒了一地。问：为什么地上有水？"),
    ("时序", "先刷牙再洗脸，洗完脸吃早饭。问：刷牙之后先做什么？"),
    ("比较", "大象比马重，马比羊重。问：谁最轻？"),
    ("传递", "A比B高，B比C高，C比D高。问：谁最高？"),
    ("因果2", "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？"),
]

class SelfOrgState(nn.Module):
    """自组织状态: 无监督发散-收敛"""
    def __init__(self, dim):
        super().__init__()
        # 收敛变换: 用随机固定正交基做递归平滑 (无训练, 纯结构)
        # 本质: 状态反复经过"平滑核" = 低通滤波 = 去掉噪声/不稳定成分
        self.register_buffer('kernel', torch.randn(dim, dim) / (dim**0.5))
    def forward(self, x, K=8, noise=0.15):
        """x: 初始状态(问题编码). 发散-收敛K轮, 返回收敛状态"""
        s = x.clone()
        for _ in range(K):
            # 发散: 加噪
            s_d = s + torch.randn_like(s) * noise
            # 收敛: 平滑核(自组织: 去掉不稳定方向, 保留主结构)
            s_c = torch.tanh(s_d @ self.kernel.T + s_d * 0.5)
            s = s_c / (s_c.norm() + 1e-9) * 3.0
        return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=8)
    ap.add_argument('--noise', type=float, default=0.15)
    args = ap.parse_args()
    torch.manual_seed(0)
    np.random.seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    st = SelfOrgState(HS).to('cuda').to(torch.bfloat16)

    def state_of(text):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1].float()
        return h

    inject = {'v': None}
    def make_inject():
        def hook(mod, inp, out):
            h = out[0]
            if inject['v'] is not None:
                h = h + 0.5 * inject['v'].to(h.dtype).unsqueeze(0)
            return (h,) if isinstance(out, tuple) else h
        return hook
    hk = model.model.layers[12].register_forward_hook(make_inject())

    def gen(q, use_selforg):
        if use_selforg:
            x0 = state_of(q)
            xc = st(x0.unsqueeze(0).to(torch.bfloat16), K=args.K, noise=args.noise)
            inject['v'] = xc[0]
        prompt = f"问：{q}\n答："
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=30, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        inject['v'] = None
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print(f'[V78b] 自组织发散-收敛 K={args.K} noise={args.noise}', flush=True)
    t0 = time.time()
    results = []
    for tag, q in QS:
        a0 = gen(q, False)
        a1 = gen(q, True)
        results.append((tag, q, a0, a1))
        print(f'[{tag}]', flush=True)
        print(f'  直答:     {a0[:42]}', flush=True)
        print(f'  自组织:   {a1[:42]}', flush=True)
    hk.remove()
    print(f'\n[DONE] {time.time()-t0:.0f}s 存 v78b.json', flush=True)
    json.dump(results, open(f'{SAVE}/v78b_results.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
