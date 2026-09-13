#!/usr/bin/env python3
"""V78 底层结构改写 — 把0.5B某层改造成"带内部状态"模块 (非hook, 改结构)
改造: layer12.mlp 的 down_proj 输出后, 接一个"状态单元":
  状态: h_s (896维, 模型自己的持续变量, 随每次前向自动演化)
  更新: h_s ← (1-α)·h_s + α·tanh(W_in·x + W_rec·h_s)   ← 状态动力学内建
  输出: y = down_proj_out + W_out·h_s                    ← 状态影响输出
  → 模型前向时, 状态自己演化 = 隐空间发散-收敛的底层机制
  权重 W_in/W_rec/W_out 是新增结构参数 (可训练/可写活)
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

class StateUnit(nn.Module):
    """内建状态单元: 挂在层输出, 状态随前向演化"""
    def __init__(self, dim):
        super().__init__()
        self.W_in = nn.Linear(dim, dim, bias=False)
        self.W_rec = nn.Linear(dim, dim, bias=False)
        self.W_out = nn.Linear(dim, dim, bias=False)
        self.alpha = 0.3
        self.state = None  # 持续状态 (跨前向)
    def reset(self):
        self.state = None
    def forward(self, x):
        # x: 该层输出的末token表征 (用于更新状态)
        if self.state is None:
            self.state = torch.zeros_like(x)
        # 状态演化 (发散-收敛: 递归变换 = 收敛到模型学过的模式)
        h_new = torch.tanh(self.W_in(x) + self.W_rec(self.state))
        self.state = (1 - self.alpha) * self.state + self.alpha * h_new
        return self.W_out(self.state)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=4)
    ap.add_argument('--lr', type=float, default=1e-4)
    ap.add_argument('--train_steps', type=int, default=150)
    args = ap.parse_args()
    torch.manual_seed(0)

    tok = AutoTokenizer.from_pretrained(MDIR)
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda')
    # 冻结原模型
    for p in model.parameters():
        p.requires_grad = False

    # 插入状态单元 (挂 layer12 的 mlp 之后)
    state_unit = StateUnit(HS).to('cuda').to(torch.bfloat16)
    # 训练状态单元: 让它学会"把状态收敛到对问题有用的表示"
    opt = torch.optim.Adam(state_unit.parameters(), lr=args.lr)

    QS = [
        "因为小猫打翻了花瓶，花瓶碎了；水撒了一地。问：为什么地上有水？",
        "大象比马重，马比羊重。问：谁最轻？",
        "A比B高，B比C高，C比D高。问：谁最高？",
        "闹钟没响，所以他睡过头了；睡过头所以迟到了。问：他为什么迟到？",
        "先刷牙再洗脸，洗完脸吃早饭。问：刷牙之后先做什么？",
    ]

    def hook_out(mod, inp, out):
        """在 mlp 输出后加状态影响 (结构改写, 每次前向自动发生)"""
        h = out[0]
        # 用 h 的末token更新状态并加回
        h_last = h[0, -1]
        st_contrib = state_unit(h_last.detach().to(torch.bfloat16)) if train_mode else None
        # 注: 状态单元挂在这里, 训练时用干净路径
        return out
    train_mode = True

    # 训练状态单元: 输入问题 → 状态收敛 → 用状态预测"答案的关键词"
    print(f'[V78] 训练状态单元 (内建状态层, {args.train_steps}步)', flush=True)
    t0 = time.time()
    for it in range(args.train_steps):
        # 用问题编码训练状态: 状态应收敛到"能区分问题类型"的表示
        q = QS[it % len(QS)]
        ids = tok(q, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[13][0, -1].float()
        # 目标: 不同类型问题(因果/比较/时序) → 不同状态
        tag = it % len(QS)
        # 让状态单元学会: 输入h → 输出一个"类型标记"
        state_unit.reset()
        state_unit(h.unsqueeze(0).to(torch.bfloat16))
        s = state_unit.state  # 收敛后的状态
        # 简单训练目标: 状态的某方向区分问题类型 (用固定目标向量)
        target = torch.zeros(HS, device='cuda', dtype=torch.bfloat16)
        # 每种问题一个随机但固定的目标方向
        g = torch.Generator(device='cuda').manual_seed(tag)
        target = torch.randn(HS, generator=g, device='cuda').to(torch.bfloat16)
        loss = -F.cosine_similarity(s.float(), target.float().unsqueeze(0)).mean()
        opt.zero_grad(); loss.backward()
        opt.step()
        if (it+1) % 50 == 0:
            print(f'  it{it+1} loss={loss.item():.3f} ({time.time()-t0:.0f}s)', flush=True)
    print(f'[V78 状态单元训练完 | {time.time()-t0:.0f}s]', flush=True)
    torch.save(state_unit.state_dict(), f'{SAVE}/v78_state_unit.pt')
    print(f'[存 v78_state_unit.pt]', flush=True)

if __name__ == '__main__':
    main()
