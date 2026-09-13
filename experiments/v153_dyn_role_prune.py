#!/usr/bin/env python3
# V153 按动力学角色剪 — 不看%, 看每个gate神经元在状态流里的功能
# 角色分类(基于激活动力学):
#   C-控制: 跨任务稳定激活(慢/恒)      → 保留(骨架)
#   K-知识: 任务特异激活(某任务爆)      → 剪(知识)
#   N-噪音/从不激活: 所有任务都≈0      → 剪(死单元, 白占)
#   R-残余: 波动但非特异(语言基础?)    → 小心(可能是语言骨架)
# 每层各自分类, 报告各类占比, 然后只剪K+N, 看还剩多少+是否更纯
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TASKS_K = ['中国的首都是哪里？','水的沸点是多少？','鲸鱼属于什么动物？','光速大约多少？','一年几个月？','地球绕什么转？']
TASKS_C = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？','甲比乙高乙比丙矮谁最矮？','如果P则Q，P真Q怎样？','所有鸟有翅膀企鹅是鸟企鹅怎样？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    buf = {}
    handles = []
    for L in range(24):
        handles.append(model.model.layers[L].mlp.gate_proj.register_forward_hook(
            lambda m, i, o, L=L: buf.__setitem__(L, o[0].float().cpu())))
    def collect(texts):
        acc = {L: [] for L in range(24)}
        with torch.no_grad():
            for t in texts:
                buf.clear()
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                model(input_ids=ids)
                for L in range(24):
                    if L in buf: acc[L].append(buf[L].mean(0).numpy())
        return {L: np.array(acc[L]) for L in range(24)}
    Ak = collect(TASKS_K); Ac = collect(TASKS_C)
    for hh in handles: hh.remove()

    print('=== 每层 gate 动力学角色 ===', flush=True)
    total_c = total_k = total_n = total_r = 0
    for L in range(24):
        K = Ak[L]; C = Ac[L]
        kmean = K.mean(0); cmean = C.mean(0)
        kstd = K.std(0); cstd = C.std(0)
        # 激活强度(平均所有任务)
        allmean = (kmean + cmean) / 2
        # 角色判定
        # 死单元: 所有任务都≈0
        dead = allmean < 0.02
        # 知识: 知识任务激活 > 控制任务*1.5 (知识爆发)
        know = (~dead) & (kmean > cmean * 1.5 + 0.05)
        # 控制: 两任务都激活且稳定(控制任务有响应 且 差值小)
        ctrl = (~dead) & (~know) & (cmean > 0.05) & (np.abs(kmean - cmean) < 0.3 * (cmean + 0.1))
        # 残余: 剩下(有响应但不稳定/难归类)
        rest = ~(dead | know | ctrl)
        n_d, n_k, n_c, n_r = dead.sum(), know.sum(), ctrl.sum(), rest.sum()
        total_c += n_c; total_k += n_k; total_n += n_d; total_r += n_r
        if L % 4 == 0:
            print('层%2d: 控制=%d 知识=%d 死=%d 残余=%d' % (L, n_c, n_k, n_d, n_r), flush=True)
    print('\n总计(24层): 控制=%d (%.1f%%) | 知识=%d | 死=%d | 残余=%d' % (
        total_c, 100*total_c/(24*4864), total_k, total_n, total_r), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
