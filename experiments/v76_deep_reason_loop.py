#!/usr/bin/env python3
"""V76 内部深度推理循环 — 循环状态题内多步演化 + 跨题状态 + 写活
内部演化: 用0.5B真实层(embed→layer12)把状态向量当输入, 做R步深度变换(内部思考)
跨题: h_state 传递
写活: anti-Hebbian
"""
import os, json, time, argparse
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'

QUESTIONS = [
    ("因果", "因为小猫打翻了花瓶，花瓶碎了；花瓶碎了，水撒了一地。问：为什么地上有水？"),
    ("时序", "先刷牙再洗脸，洗完脸吃早饭。问：刷牙之后先做什么？"),
    ("演绎", "所有会游泳的都在水里，鸭子会游泳。问：鸭子在哪？"),
    ("比较", "大象比马重，马比羊重。问：谁最轻？"),
    ("条件", "如果天晴我们就去公园，今天天晴。问：我们去哪？"),
    ("因果2", "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？"),
    ("时序2", "先烧水再放茶叶，泡完茶倒进杯子。问：放茶叶之前做了什么？"),
    ("传递", "A比B高，B比C高，C比D高。问：谁最高？"),
    ("因果3", "忘记关窗，所以雨飘进来；雨飘进来所以地板湿了。问：地板为什么湿？"),
    ("条件2", "只有满18岁才能进，小明满18了。问：小明能进吗？"),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--R', type=int, default=3)
    ap.add_argument('--eta_w', type=float, default=0.04)
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = 'model.layers.12.mlp.down_proj.weight'
    W0 = sd[WN].float().clone()

    # 内部深度变换: 用模型真实权重把状态向量做非线性变换 (h→norm→down_proj→激活)
    # 用 layer12 的 mlp 权重构造一个固定内部变换 (等价于"状态过一层"的思考)
    W12 = sd['model.layers.12.mlp.gate_proj.weight'].float().to('cuda')   # (inter,896)
    W13 = sd['model.layers.12.mlp.down_proj.weight'].float().to('cuda')   # (896,inter)
    inter_dim = W12.shape[0]
    print(f'[V76] 内部深度推理循环 R={args.R} 层12维度 inter={inter_dim}', flush=True)

    def internal_think(h, R):
        """h(896,) 内部演化 R 步: 每步 = 过 layer12 的 MLP 非线性 (真实思考变换)"""
        cur = h
        for _ in range(R):
            x = cur  # (896,)
            gate = torch.matmul(W12, x)          # (inter,)
            act = torch.nn.functional.silu(gate)  # SiLU 激活
            out = torch.matmul(W13, act)          # (896,)
            cur = cur + 0.05 * out                # 残差小步演化 (稳定)
            cur = cur / (cur.norm() + 1e-9) * 3.0  # 保幅
        return cur

    h_state = None
    act_buf = {}
    def hook_in(mod, inp, out):
        act_buf['a'] = inp[0][0, -1].float().detach().cpu()
        return out
    h_in = model.model.layers[12].mlp.down_proj.register_forward_hook(hook_in)

    def make_loop():
        def hook(mod, inp, out):
            h = out[0]
            if h_state is not None:
                h = h + 0.3 * h_state.to(h.dtype).unsqueeze(0)
            return (h,) if isinstance(out, tuple) else h
        return hook
    h_loop = model.model.layers[6].register_forward_hook(make_loop())

    def gen_answer(q):
        prompt = f"问：{q}\n答："
        ids = tok(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            out = model.generate(input_ids=ids, max_new_tokens=30, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    def state_of(text):
        ids = tok(text[-200:], return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1].float()
        return h / (h.norm() + 1e-12)

    t0 = time.time()
    results = []
    for qi, (tag, q) in enumerate(QUESTIONS):
        # 内部深度思考 (上题状态先内部演化R步 = 跨题"想")
        if h_state is not None:
            h_state = internal_think(h_state, args.R)
        ans = gen_answer(q)
        results.append((tag, q, ans))
        v = state_of(q + ans)
        h_state = v if h_state is None else 0.7 * h_state + 0.3 * v
        if 'a' in act_buf and h_state is not None:
            svec = h_state / (h_state.norm() + 1e-12)
            d = v - (v @ svec) * svec
            if d.norm() > 0.05:
                avec = act_buf['a'].to('cuda'); avec = avec / (avec.norm() + 1e-12)
                with torch.no_grad():
                    sd[WN].add_((args.eta_w * torch.outer((d / d.norm()).float(), avec.float())).to(sd[WN].dtype))
        print(f'  [{tag}] {ans[:40]}', flush=True)
    h_in.remove(); h_loop.remove()
    print(f'\n[V76 DONE] {len(results)}题 | {time.time()-t0:.0f}s | 存 v76_results.json', flush=True)
    json.dump(results, open(f'{SAVE}/v76_results.json', 'w'), ensure_ascii=False, indent=1)

if __name__ == '__main__':
    main()
