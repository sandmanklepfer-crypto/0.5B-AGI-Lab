#!/usr/bin/env python3
"""V86 权重矩阵分块 — 用知识/推理分离方向, 把 down_proj 权重分成两块独立子空间
方法:
 1 采知识任务/推理任务在层12的输入激活 (down_proj 的输入 â)
 2 找两类的分离方向 (LDA): w_sep
 3 构造投影: 输入 â → 分解成 [知识分量, 推理分量] (沿 w_sep 及正交)
 4 把 W 重新组织: W ≈ W_k + W_r, 其中
    W_k 只作用知识分量 (沿知识子空间), W_r 只作用推理分量
 5 验证: 分块后 知识任务输出 主要来自 W_k, 推理任务输出主要来自 W_r
"""
import os, json, time
import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1'
LAYER = 12

KNOW = ["中国的首都是什么？", "水的沸点是多少？", "7乘8等于多少？", "地球绕什么转？",
        "一年几个月？", "太阳从哪升起？", "光速大约多少？", "水的化学式？"]
REASON = ["所有鸟有翅膀，企鹅是鸟，企鹅会怎样？", "大象比马重马比羊重谁最轻？",
          "A比B高B比C高谁最高？", "明天下雨活动取消明天确实下雨活动怎样？",
          "地湿路滑下雨地湿为什么路滑？", "猫会抓老鼠小花是猫小花会抓老鼠吗？",
          "如果P则QP真则Q怎样？", "张三比李四高李四比王五矮谁最矮？"]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    sd = model.state_dict()
    WN = f'model.layers.{LAYER}.mlp.down_proj.weight'
    W = sd[WN].float()  # (896, 4864)

    # 采集 down_proj 输入 (4864维: gate/up 输出后)
    def collect_acts(texts):
        acts = []
        buf = {}
        def hook(mod, inp, out):
            buf['x'] = inp[0][0, -1].float().cpu()  # 应为 (4864,)
            return out
        h = model.model.layers[LAYER].mlp.down_proj.register_forward_hook(hook)
        with torch.inference_mode():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                model(input_ids=ids)
                acts.append(buf['x'].numpy())
        h.remove()
        return np.array(acts)

    print('[V86] 采集知识/推理的 mlp 输入...', flush=True)
    Ak = collect_acts(KNOW)   # (8, 4864)
    Ar = collect_acts(REASON) # (8, 4864)
    print(f'知识输入: {Ak.shape}, 推理输入: {Ar.shape}', flush=True)

    # LDA 分离方向 (在4864输入空间)
    mk, mr = Ak.mean(0), Ar.mean(0)
    Sw = np.cov(Ak.T) + np.cov(Ar.T) + 1e-6*np.eye(Ak.shape[1])
    w = np.linalg.solve(Sw, mk - mr)
    w = w / (np.linalg.norm(w) + 1e-9)
    # 验证可分性
    pk, pr = Ak @ w, Ar @ w
    dprime = abs(pk.mean()-pr.mean())/np.sqrt((pk.var()+pr.var())/2+1e-9)
    print(f'输入空间 LDA 分离度 d\'={dprime:.2f}', flush=True)

    # 构造分块: 输入 â = â_k + â_r
    # â_k = 沿 w 的知识分量投影, â_r = 剩余(推理主导)
    # W 分块: W_k 只从 â_k 取贡献 (W_k = W 投影到 â_k 方向)
    # 做法: 对 W 的每列(对应输入维), 按其在 w 上的分量分成两组?
    # 更稳: W_k = W * outer(w, w) 的输入侧投影? 不对, W列=输入维
    # 正确: 输入 â 分解 â = (â·w)w + (â-(â·w)w)
    #       W_k = W 只接受知识分量 → W_k = W @ P_k, P_k = outer(w,w)
    #       W_r = W @ P_r, P_r = I - outer(w,w)
    # 则 W_kâ = W P_k â = W (â·w)w = (â·w) W w  (只沿知识方向走)
    # 验证: 知识输入的 W_k 输出 vs 推理输入的 W_k 输出 差异
    Pk = np.outer(w, w)
    Pr = np.eye(len(w)) - Pk
    Wk = W.cpu().numpy() @ Pk   # 知识块
    Wr = W.cpu().numpy() @ Pr   # 推理块

    # 验证: 每类输入经过 Wk 和 Wr 的输出能量
    print('\n=== 分块验证 ===', flush=True)
    for name, A in [('知识', Ak), ('推理', Ar)]:
        ok = (A @ Wk.T)  # (n,896)
        orr = (A @ Wr.T)
        ek = np.linalg.norm(ok, axis=1).mean()
        er = np.linalg.norm(orr, axis=1).mean()
        print(f'  {name}输入: 经知识块能量={ek:.1f} 经推理块能量={er:.1f} 比={ek/max(er,1e-9):.2f}', flush=True)

    # 存分块权重
    torch.save({'Wk': torch.tensor(Wk).half(), 'Wr': torch.tensor(Wr).half(),
                'w': torch.tensor(w), 'dprime': dprime}, f'{SAVE}/v86_blocks.pt')
    print(f'\n[V86] 分块完成 存 v86_blocks.pt (Wk={Wk.shape}, Wr={Wr.shape})', flush=True)

if __name__ == '__main__':
    main()
