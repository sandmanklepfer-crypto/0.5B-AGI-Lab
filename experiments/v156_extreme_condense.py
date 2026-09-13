#!/usr/bin/env python3
# V156 全层极限浓缩: 24层全部"先收敛再删", 扫阈值(相似度0.9/0.95/0.98/0.99)
# 每档: 收敛合并 → 删冗余 → 测能力 → 报告剩余参数/能力
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TEXTS = [
    '中国的首都是哪里？水的沸点是多少？鲸鱼属于什么动物？一年几个月？光速多少？地球绕什么转？',
    '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？甲比乙高乙比丙矮谁最矮？',
    '秋天来了，落叶飘满庭院，丰收的稻谷堆满仓，我想念远方的亲人。昨夜雨疏风骤，浓睡不消残酒。',
    '在深邃的宇宙中，黑洞吞噬一切，时间在引力场中弯曲，爱因斯坦的理论改变了物理学。',
    '小明去超市买了苹果和香蕉，一共花了二十元，苹果每斤五元，香蕉每斤三元，各买了几斤？',
    '一只蜗牛白天爬3米晚上滑下2米，井深10米几天爬出？火车从北京开往上海需要五个小时。',
] * 8
TESTS = ['中国的首都是哪里？', '小明比小红大3岁小红比小刚大2岁十年后差几岁？', '秋天是什么？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    # 收集全层gate激活画像
    buf = {}
    handles = []
    for L in range(24):
        handles.append(model.model.layers[L].mlp.gate_proj.register_forward_hook(
            lambda m, i, o, L=L: buf.__setitem__(L, o[0].float().cpu())))
    acts_all = {}
    with torch.no_grad():
        for t in TEXTS:
            buf.clear()
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            model(input_ids=ids)
            for L in range(24):
                if L in buf:
                    acts_all.setdefault(L, []).append(buf[L].mean(0).numpy())
    for hh in handles: hh.remove()
    A = {L: np.array(acts_all[L]) for L in range(24)}

    def test():
        res = []
        with torch.no_grad():
            for q in TESTS:
                ids = tok(q, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=18, do_sample=False,
                                   repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                res.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:18])
        return res

    def condense(sim_th):
        """全层收敛: 每层相似单元合并, 删非代表"""
        sd = {k: v.clone() for k, v in sd0.items()}
        kept_total = 0
        for L in range(24):
            WN = 'model.layers.%d.mlp.gate_proj.weight' % L
            W = sd[WN].float().numpy()
            a = A[L]
            norm = a / (np.linalg.norm(a, axis=0, keepdims=True) + 1e-9)
            G = norm.T @ norm
            order = np.argsort(-np.linalg.norm(a, axis=0))
            used = np.zeros(a.shape[1], bool)
            reps = []
            for i in order:
                if used[i]: continue
                sim = (G[i] > sim_th) & (~used)
                reps.append(i)
                used[sim] = True
            drop = ~used
            W[drop, :] = 0.0
            sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
            kept_total += len(reps)
        model.load_state_dict(sd, strict=True)
        return kept_total

    print('=== 极限浓缩扫描 ===', flush=True)
    for th in [0.90, 0.95, 0.98, 0.99]:
        kept = condense(th)
        pct = 100*kept/(24*4864)
        r = test()
        print('相似度阈%.2f: 保留%d单元(%.1f%%) | 测试: %s' % (th, kept, pct, [x[:12] for x in r]), flush=True)
        model.load_state_dict(sd0, strict=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
