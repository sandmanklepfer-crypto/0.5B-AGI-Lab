#!/usr/bin/env python3
"""V79b 全模型收敛 v2 — 状态作为真实序列的"扩展token"过全模型
把问题token序列 后面拼一个"伪token"(其embedding=状态向量), 过全模型,
末token输出 = 状态被模型全部层+注意力收敛后的结果 (有位置/上下文环境)
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
    ("比较", "大象比马重，马比羊重。问：谁最轻？"),
    ("传递", "A比B高，B比C高，C比D高。问：谁最高？"),
    ("因果2", "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--K', type=int, default=4)
    ap.add_argument('--noise', type=float, default=0.08)
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    emb = model.model.embed_tokens

    def converge_with_model(q, s0, K):
        """把状态s0(896维)作为伪embedding拼到问题序列后, 过全模型K轮"""
        cur = s0.to(torch.bfloat16)  # (896,)
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        real_emb = emb(ids)  # (1,T,896) 问题embedding
        for _ in range(K):
            cur_d = cur + torch.randn_like(cur) * args.noise
            # 伪token embedding = 状态 (拼接)
            fake = cur_d.unsqueeze(0).unsqueeze(0)  # (1,1,896)
            full = torch.cat([real_emb, fake], dim=1)  # (1,T+1,896)
            with torch.inference_mode():
                out = model(inputs_embeds=full, output_hidden_states=True)
            # 取末token(伪token位置)的末层输出 = 被全模型收敛的状态
            cur = out.hidden_states[-1][0, -1].float()
            cur = cur / (cur.norm() + 1e-9) * 3.0
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

    def state_of(text):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1]
        return h  # bf16

    def gen(q, use_dc):
        if use_dc:
            x0 = state_of(q)
            xc = converge_with_model(q, x0, args.K)
            inject['v'] = xc.to('cuda')
        prompt = f"问：{q}\n答："
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=25, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        inject['v'] = None
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    print(f'[V79b] 全模型收敛(伪token过全层) K={args.K}', flush=True)
    t0 = time.time()
    results = []
    for tag, q in QS:
        a0 = gen(q, False)
        a1 = gen(q, True)
        results.append((tag, q, a0, a1))
        print(f'[{tag}]', flush=True)
        print(f'  直答:   {a0[:45]}', flush=True)
        print(f'  收敛:   {a1[:45]}', flush=True)
    hk.remove()
    print(f'\n[DONE] {time.time()-t0:.0f}s 存 v79b.json', flush=True)
    json.dump(results, open(f'{SAVE}/v79b_results.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
