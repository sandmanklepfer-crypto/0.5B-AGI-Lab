#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V137 养权重·第一代 — 权重级进化原型 (原生生命第一步)
环境: 会验证的算术世界 (命题→对/错, 错=撞墙扣能量, 对=回血)
种群: 从 antiheb_05b 变异出 POP 个个体 (干净小扰动, 每体不同seed)
每代: 每个体在环境里活一段时间, 适应度 = 存活时长 + 答对数
选择: 适应度前 KEEP 名 → 变异繁衍下一代 (交叉: 平均两父权重 + 扰动)
测: 种群平均适应度随代上升? (权重真的在进化)
注意: 这是第一代原型, 先跑 3 代看机制通不通, 不全量烧算力
"""
import torch, time
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
POP = 8            # 种群大小
KEEP = 2           # 每代保留几个
GENS = 3           # 代数
MUT_SCALE = 0.01   # 变异幅度(干净小扰动)
N_QUEST = 20       # 每体每代答几题
# 算术题库(可验证): (题, 答案)
PROBLEMS = [
    ('1加2等于多少？', '3'), ('3加4等于多少？', '7'), ('5加6等于多少？', '11'),
    ('7加8等于多少？', '15'), ('9加10等于多少？', '19'), ('2乘3等于多少？', '6'),
    ('4乘5等于多少？', '20'), ('6乘7等于多少？', '42'), ('8乘9等于多少？', '72'),
    ('10减3等于多少？', '7'), ('15减8等于多少？', '7'), ('20减9等于多少？', '11'),
    ('100减1等于多少？', '99'), ('2的平方等于多少？', '4'), ('3的平方等于多少？', '9'),
    ('4的平方等于多少？', '16'), ('5的平方等于多少？', '25'), ('1加1等于多少？', '2'),
    ('10加10等于多少？', '20'), ('12加8等于多少？', '20'),
]

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    base = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    # 取一层权重做变异基底(干净小扰动, 不碰全部防崩)
    LAYER = 12
    WN = 'model.layers.%d.mlp.down_proj.weight' % LAYER
    sd = base.state_dict()
    W0 = sd[WN].float().cpu().numpy().copy()

    def make_model(delta):
        """用 delta 变异出个体(返回可推理的模型)"""
        m = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
        sd2 = dict(m.state_dict())
        sd2[WN] = torch.tensor(W0 + delta).to(sd2[WN].dtype)
        m.load_state_dict(sd2, strict=True)
        return m

    def fitness(model):
        """适应度: 答对率 (20题里答对几题)"""
        ok = 0
        for q, a in PROBLEMS:
            ids = tok(q, return_tensors='pt').input_ids.to('cuda')
            with torch.no_grad():
                o = model.generate(ids, max_new_tokens=8, do_sample=False,
                                   pad_token_id=tok.eos_token_id)
            ans = tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)
            if a in ans:
                ok += 1
        return ok / len(PROBLEMS)

    # 初始化种群: 从0开始变异
    pop_deltas = []
    for i in range(POP):
        rng = np.random.RandomState(i)
        d = rng.randn(*W0.shape).astype(np.float64)
        d = d / np.linalg.norm(d) * (np.linalg.norm(W0) * MUT_SCALE)
        pop_deltas.append(d)

    print('V137 养权重 | %d个体 %d代 变异%.3f 算术环境' % (POP, GENS, MUT_SCALE), flush=True)
    # 基线: 原模型适应度
    fit_base = fitness(base)
    print('基线(未变异): 适应度=%.2f' % fit_base, flush=True)

    for gen in range(GENS):
        print('\n===== 第%d代 =====' % (gen+1), flush=True)
        fits = []
        for i, d in enumerate(pop_deltas):
            m = make_model(d)
            f = fitness(m)
            fits.append(f)
            del m; torch.cuda.empty_cache()
            print('  个体%d 适应度=%.2f' % (i, f), flush=True)
        # 选择: 前KEEP
        order = np.argsort(-np.array(fits))
        best = [pop_deltas[i] for i in order[:KEEP]]
        print('  保留个体: %s (适应度 %.2f, %.2f)' % (
            [int(i) for i in order[:KEEP]], fits[order[0]], fits[order[1]]), flush=True)
        # 繁衍: 交叉(两父平均)+变异
        new_pop = []
        for i in range(POP):
            p1, p2 = best[np.random.randint(KEEP)], best[np.random.randint(KEEP)]
            child = (p1 + p2) / 2
            rng = np.random.RandomState(1000 + gen * 100 + i)
            noise = rng.randn(*W0.shape).astype(np.float64)
            noise = noise / np.linalg.norm(noise) * (np.linalg.norm(W0) * MUT_SCALE)
            new_pop.append(child + noise)
        pop_deltas = new_pop
    print('\n[done] 3代完成, 看适应度是否随代上升', flush=True)

if __name__ == '__main__':
    main()
