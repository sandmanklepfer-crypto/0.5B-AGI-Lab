#!/usr/bin/env python3
# V155 先收敛再删: 激活聚类合并(功能相似单元合一) → 再删空出的
# 步骤: 大量多样文本 → 每单元激活向量 → 聚类(相似单元) → 每簇保留1代表(其余删)
#       = 功能保留, 单元数大减
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TEXTS = [
    '中国的首都是哪里？水的沸点是多少？鲸鱼属于什么动物？一年几个月？光速多少？',
    '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？甲比乙高乙比丙矮谁最矮？',
    '秋天来了，落叶飘满庭院，丰收的稻谷堆满仓，我想念远方的亲人。',
    '在深邃的宇宙中，黑洞吞噬一切，时间在引力场中弯曲，爱因斯坦的理论改变了物理学。',
    '小明去超市买了苹果和香蕉，一共花了二十元，苹果每斤五元，香蕉每斤三元。',
    '昨夜雨疏风骤，浓睡不消残酒，试问卷帘人，却道海棠依旧。',
] * 10   # 重复让激活统计稳定

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    L = 12   # 先试一层
    buf = {}
    h = model.model.layers[L].mlp.gate_proj.register_forward_hook(
        lambda m, i, o: buf.__setitem__('g', o[0].float().cpu()))
    acts = []
    with torch.no_grad():
        for t in TEXTS:
            buf.clear()
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            model(input_ids=ids)
            if 'g' in buf: acts.append(buf['g'].mean(0).numpy())
    h.remove()
    A = np.array(acts)  # (N,4864)
    # 单元激活画像(跨文本) + 相似度聚类
    # 简版: 归一化激活向量, 算单元间cos, 高相似(>0.9)合并
    norm = A / (np.linalg.norm(A, axis=0, keepdims=True) + 1e-9)  # (N,4864)
    G = norm.T @ norm  # (4864,4864) 单元相似度
    print('单元相似度矩阵计算完', flush=True)
    # 贪心合并: 相似>0.95 的单元并成簇, 每簇留最强(激活范数最大)代表
    used = np.zeros(4864, bool)
    reps = []
    order = np.argsort(-np.linalg.norm(A, axis=0))  # 从强到弱
    for i in order:
        if used[i]: continue
        # 找与i相似的未用单元
        sim = G[i] > 0.95
        sim = sim & (~used)
        # 但避免连坐太多: 只合并sim中那些
        reps.append(i)
        used[sim] = True
    n_rep = len(reps)
    print('收敛结果: 4864 → %d 代表单元 (删%.1f%%)' % (n_rep, 100*(4864-n_rep)/4864), flush=True)
    # 删除: 非代表单元 gate 行置零(它们和代表相似, 功能由代表覆盖)
    sd = {k: v.clone() for k, v in sd0.items()}
    WN = 'model.layers.%d.mlp.gate_proj.weight' % L
    W = sd[WN].float().numpy()
    drop = ~np.zeros(4864, bool); drop[:] = True
    drop[reps] = False
    W[drop, :] = 0.0
    sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
    model.load_state_dict(sd, strict=True)
    print('已删', int(drop.sum()), '个冗余单元(层%d)' % L, flush=True)
    # 测试
    def test(texts):
        with torch.no_grad():
            for q in texts:
                ids = tok(q, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=22, do_sample=False,
                                   repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                print('  %s → %s' % (q[:14], tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)[:25]), flush=True)
    print('=== 单层收敛+剪除后 ===', flush=True)
    test(['中国的首都是哪里？', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？', '秋天是什么样子？'])
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
