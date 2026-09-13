#!/usr/bin/env python3
# V146 在0.5B权重里找"通用控制核": 跨任务稳定激活的gate神经元
# 方法: 多种任务 → hook每层gate输出 → 找"跨任务都激活"的神经元(=控制/路由单元)
#      vs "特定任务才激活"(=内容单元)
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TASKS = [
    '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？',
    '中国的首都是哪里？',
    '一只蜗牛白天爬3米晚上滑下2米，井深10米几天爬出？',
    '请写一段关于秋天的文字',
    '如果人可以删除记忆该不该有这能力？',
    '1+1等于几？',
    '鲸鱼属于什么动物？',
]

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    # hook 所有层 gate 输出(激活前, 即SiLU输入或输出)
    gates = {}
    handles = []
    for L in range(24):
        handles.append(model.model.layers[L].mlp.gate_proj.register_forward_hook(
            lambda m, i, o, L=L: gates.setdefault(L, []).append(o[0].float().cpu())))
    acts = {L: [] for L in range(24)}
    with torch.no_grad():
        for t in TASKS:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            model(input_ids=ids)
            for L in range(24):
                # 取最后token的gate激活
                acts[L].append(gates[L][-1][-1])   # (4864,)
            gates.clear()
    for h in handles: h.remove()
    # 分析每层: 跨任务一致激活的神经元
    print('=== 每层 gate 神经元: 通用控制单元扫描 ===', flush=True)
    for L in [0, 4, 8, 12, 16, 20, 23]:
        A = torch.stack(acts[L])       # (7任务, 4864)
        # 神经元跨任务的激活稳定性(归一化后)
        std = A.std(0)                 # 跨任务标准差(低=跨任务稳定=通用)
        mean = A.mean(0)
        # 通用单元: 平均激活高 且 跨任务std低(不管任务都开/都关)
        stable = (std < std.median()) & (mean > mean.median())
        n_stable = stable.sum().item()
        # 任务特异单元: std高
        spec = std > std.median() * 1.5
        n_spec = spec.sum().item()
        print('层%2d: 通用控制候选=%d/4864 (%.1f%%) | 任务特异=%d' % (
            L, n_stable, 100*n_stable/4864, n_spec), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
