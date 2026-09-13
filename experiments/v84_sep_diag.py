#!/usr/bin/env python3
"""V84 知识/推理 分离度诊断 — 0.5B里两者激活哪些层? 重叠多少?
知识任务(事实): 首都/沸点/乘法 等 (需存储的知识)
推理任务(逻辑): 三段论/比较/因果 (需推演)
测: 每层激活 对两类任务的区分度 → 找天然分离点
"""
import os, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'

# 知识任务 (事实检索类)
KNOW_TASKS = [
    "中国的首都是什么？",
    "水的沸点是多少度？",
    "7乘以8等于多少？",
    "地球绕什么转？",
    "一年有几个月？",
]
# 推理任务 (逻辑推演类)
REASON_TASKS = [
    "所有鸟都有翅膀，企鹅是鸟。企鹅会怎样？",
    "大象比马重，马比羊重。谁最轻？",
    "A比B高，B比C高，谁最高？",
    "如果明天下雨活动取消，明天确实下雨了。活动怎样？",
    "因为地湿所以路滑，因为下雨所以地湿。为什么路滑？",
]

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    NLAY = model.config.num_hidden_layers

    def acts(texts):
        """返回 (n_task, n_layer, 896) 每任务每层的平均激活"""
        res = []
        for t in texts:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            with torch.inference_mode():
                hs = model(input_ids=ids, output_hidden_states=True).hidden_states
            # 每层: 全token平均
            layer_acts = []
            for l in range(NLAY):
                h = hs[l+1][0].float().mean(0).cpu().numpy()  # (896,)
                layer_acts.append(h)
            res.append(layer_acts)
        return np.array(res)  # (n, n_layer, 896)

    print('[V84] 采集知识/推理激活...', flush=True)
    K = acts(KNOW_TASKS)      # (5, 24, 896)
    R = acts(REASON_TASKS)    # (5, 24, 896)
    print(f'知识: {K.shape}, 推理: {R.shape}', flush=True)

    # 每层: 类内相似 vs 类间相似 (LDA式分离度)
    print(f'\n{"层":>4} {"知识内cos":>10} {"推理内cos":>10} {"类间cos":>10} {"分离度":>8}', flush=True)
    sep_layers = []
    for l in range(NLAY):
        Kk = K[:, l]  # (5,896)
        Rr = R[:, l]
        def avg_cos(X):
            c = 0; n = 0
            for i in range(len(X)):
                for j in range(i+1, len(X)):
                    c += np.dot(X[i], X[j]) / (np.linalg.norm(X[i])*np.linalg.norm(X[j])+1e-9)
                    n += 1
            return c/max(n,1)
        k_in = avg_cos(Kk)
        r_in = avg_cos(Rr)
        # 类间
        cross = 0; n = 0
        for i in range(len(K)):
            for j in range(len(R)):
                cross += np.dot(K[i,l], R[j,l]) / (np.linalg.norm(K[i,l])*np.linalg.norm(R[j,l])+1e-9)
                n += 1
        cross /= n
        sep = (k_in + r_in) / 2 - cross   # 分离度: 类内高-类间低
        sep_layers.append((l, k_in, r_in, cross, sep))
        if l % 3 == 0 or l == NLAY-1:
            print(f'{l:>4} {k_in:>10.3f} {r_in:>10.3f} {cross:>10.3f} {sep:>8.3f}', flush=True)

    # 找分离度最高/最低层
    sep_layers.sort(key=lambda x: -x[4])
    print(f'\n分离度最高的层: {[x[0] for x in sep_layers[:5]]} (sep={[round(x[4],3) for x in sep_layers[:5]]})')
    print(f'分离度最低的层: {[x[0] for x in sep_layers[-3:]]} (sep={[round(x[4],3) for x in sep_layers[-3:]]})')
    print(f'\n→ {"存在天然分离层(知识/推理在不同层)" if sep_layers[0][4] > 0.05 else "知识推理深度纠缠(需架构分离)"}')

if __name__ == '__main__':
    main()
