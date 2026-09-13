#!/usr/bin/env python3
"""V79 全模型收敛器 — 状态被0.5B完整语义景观拉回 (非随机/非单层)
发散: 状态加噪
收敛: 把状态当"伪token"喂给0.5B全部层 (embed→24层), 输出末层状态 = 被模型知识景观拉回
迭代K轮 → 看能否收敛到"语义正确"的吸引子
"""
import os, json, time, argparse
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'

QS = [
    ("因果", "因为小猫打翻了花瓶，花瓶碎了；水撒了一地。问：为什么地上有水？"),
    ("时序", "先刷牙再洗脸，洗完脸吃早饭。问：刷牙之后先做什么？"),
    ("比较", "大象比马重，马比羊重。问：谁最轻？"),
    ("传递", "A比B高，B比C高，C比D高。问：谁最高？"),
    ("因果2", "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=5, help='发散-收敛轮数')
    ap.add_argument('--noise', type=float, default=0.1)
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()

    def state_of(text):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1].float()
        return h

    def fullmodel_converge(s, K):
        """把状态s当伪token喂全模型, 输出末层 = 被语义景观收敛"""
        cur = s.to(torch.bfloat16)  # (896,)
        for _ in range(K):
            # 发散: 加噪
            cur_d = cur + torch.randn_like(cur) * args.noise
            # 收敛: 状态作为伪token过全模型 (embed→norm→24层)
            with torch.inference_mode():
                # 构造伪输入: 状态当 hidden_state, 需位置编码才能过attention
                h = cur_d.unsqueeze(0).unsqueeze(0)  # (1,1,896) 伪hidden
                # 获取位置编码 (rope: 需要cos/sin; 直接给pos_ids=0的rope)
                bsz, seq, _ = h.shape
                pos_ids = torch.arange(seq, device=h.device).unsqueeze(0)  # (1,1)
                for layer in model.model.layers:
                    h = layer(h, position_embeddings=(None, None))[0] if False else \
                        layer(h, position_embeddings=None, use_cache=False)[0] if False else \
                        layer(h)[0]
                # 上面尝试复杂; 换简单方案: 逐层过 但跳过attention的位置依赖
                out_h = h[0, 0].float()
            cur = out_h / (out_h.norm() + 1e-9) * 3.0
        return cur

    inject = {'v': None}
    def make_inject():
        def hook(mod, inp, out):
            h = out[0]
            if inject['v'] is not None:
                h = h + 0.5 * inject['v'].to(h.dtype).unsqueeze(0)
            return (h,) if isinstance(out, tuple) else h
        return hook
    hk = model.model.layers[12].register_forward_hook(make_inject())

    def gen(q, use_dc):
        if use_dc:
            x0 = state_of(q)
            xc = fullmodel_converge(x0, args.K)
            inject['v'] = xc.to('cuda')
        prompt = f"问：{q}\n答："
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=25, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        inject['v'] = None
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print(f'[V79] 全模型语义景观收敛 K={args.K}', flush=True)
    t0 = time.time()
    results = []
    for tag, q in QS:
        a0 = gen(q, False)
        a1 = gen(q, True)
        results.append((tag, q, a0, a1))
        print(f'[{tag}]', flush=True)
        print(f'  直答:   {a0[:45]}', flush=True)
        print(f'  全模型: {a1[:45]}', flush=True)
    hk.remove()
    print(f'\n[DONE] {time.time()-t0:.0f}s 存 v79.json', flush=True)
    json.dump(results, open(f'{SAVE}/v79_results.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
