#!/usr/bin/env python3
"""V87 时间结构需求验证 — 推理任务需多步演化才稳定, 知识任务一步稳定?
方法:
 1 知识/推理任务 → 深层状态(层23末token)
 2 把状态当初始点, 用模型层变换迭代演化 T 步
 3 测每步状态变化量: 知识任务几步收敛? 推理任务几步收敛?
如果推理需要更多步才收敛 → "时间结构需求"差异证实
"""
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
KNOW = ["中国的首都是什么？", "水的沸点是多少？", "7乘8等于多少？", "一年有几个月？", "太阳从哪升起？"]
REASON = ["所有鸟有翅膀，企鹅是鸟，企鹅会怎样？", "大象比马重马比羊重谁最轻？",
          "A比B高B比C高谁最高？", "因为地湿所以路滑因为下雨所以地湿为什么路滑？",
          "张三比李四高李四比王五矮谁最矮？"]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to('cuda').eval()
    # 用层20-23的 mlp 权重做演化变换 (时间步)
    Ws = []
    for L in range(20, 24):
        Ws.append(model.state_dict()[f'model.layers.{L}.mlp.down_proj.weight'].float())
    W22 = model.state_dict()['model.layers.22.mlp.gate_proj.weight'].float()

    def state_of(text, L=23):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.inference_mode():
            h = model(input_ids=ids, output_hidden_states=True).hidden_states[L+1][0, -1].float()
        return h / (h.norm() + 1e-9) * 3.0

    def evolve(s, n_steps=20):
        """把状态当伪输入, 用层22变换迭代演化, 记录每步变化"""
        cur = s
        changes = []
        for i in range(n_steps):
            gate = torch.matmul(W22, cur)  # 注意: gate_proj 是 (inter,896)? 检查维度
            return cur, changes

    # 简化正确做法: 用完整 layer22 前向 (带 attention) 太重; 改用 mlp 块迭代
    # 直接: 状态过 layer22 的完整模块 (用 model.model.layers[22] 前向, 需hidden_states格式)
    def evolve_full(s, n_steps=15):
        cur = s
        changes = []
        with torch.inference_mode():
            for i in range(n_steps):
                h_in = cur.unsqueeze(0).unsqueeze(0)  # (1,1,896) 伪hidden
                # 过 layer22 (位置编码问题: 单token position 0, 用 rope 需要 cos/sin)
                # 简化: 只用 mlp 部分 (LN + mlp), 跳过 attention — 纯非线性变换
                ln = model.model.layers[22].post_attention_layernorm
                mlp = model.model.layers[22].mlp
                x = ln(h_in)
                x = mlp(x)[0]
                cur2 = cur + x[0, 0].float() * 0.3  # 残差小步
                chg = (cur2 - cur).norm().item()
                changes.append(chg)
                cur = cur2 / (cur2.norm() + 1e-9) * 3.0
        return changes

    print('[V87] 时间结构需求: 知识 vs 推理 演化收敛步数', flush=True)
    for name, tasks in [('知识', KNOW), ('推理', REASON)]:
        conv_steps = []
        for q in tasks:
            s = state_of(q)
            chg = evolve_full(s)
            # 收敛步 = 变化量降到 < 首步20% 的那步
            base = chg[0] if chg else 1
            cstep = None
            for i, c in enumerate(chg):
                if c < base * 0.2:
                    cstep = i
                    break
            conv_steps.append(cstep if cstep is not None else len(chg))
            print(f'  [{name}] {q[:18]}... 收敛步={cstep}', flush=True)
        print(f'  {name}平均收敛步: {np.mean(conv_steps):.1f}', flush=True)

if __name__ == '__main__':
    main()
