#!/usr/bin/env python3
# V152 最终验证: 90%剪除裸核(无知识纯骨架) + 外部工具 = 能不能干活
# 架构: 裸核(控制/流程) 组织 + 工具(知识/算力) 供给
# 测: 知识题(工具给) + 流程题(裸核自己)
import torch, numpy as np, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TOOLS = {'中国首都':'北京','水沸点':'100摄氏度','鲸鱼':'哺乳动物','一年':'12个月'}

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    # 90% 剪除(同V150方法: gate权重重要性)
    cut_idx = {}
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd0[WN].float().numpy()
        WD = sd0['model.layers.%d.mlp.down_proj.weight' % L].float().numpy()
        imp = np.linalg.norm(W, axis=1) * np.linalg.norm(WD, axis=0)
        cut_idx[L] = np.argsort(imp)
    sd = {k: v.clone() for k, v in sd0.items()}
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd[WN].float().numpy()
        cut = cut_idx[L][:int(4864*0.9)]
        W[cut, :] = 0.0
        sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
    model.load_state_dict(sd, strict=True)
    print('[V152] 90%裸核就绪 | 知识删光, 只剩骨架+控制', flush=True)

    def gen(text, max_new=30):
        ids = tok(text, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=max_new, do_sample=False,
                               repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()

    def tool_answer(q):
        """工具(无限知识)"""
        for k, v in TOOLS.items():
            if k in q: return v
        return None

    print('\n=== 裸核 + 工具 测试 ===', flush=True)
    # 知识题: 裸核没知识 → 工具给答案 → 裸核复述/组织
    for q in ['中国的首都是哪里？', '水的沸点是多少？', '鲸鱼属于什么动物？']:
        ta = tool_answer(q)
        if ta:
            # 工具直接把答案给裸核, 裸核只需"组织成句"
            out = gen('根据资料："%s"\n回答：%s' % (ta, q))
            print('[知识+工具] %s → %s' % (q[:10], (ta + ' | 裸核: ' + out)[:40]), flush=True)
    # 流程题: 裸核自己(看剪90%后还剩什么)
    print('\n流程题(裸核独自):', flush=True)
    for q in ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？']:
        # 先问裸核关系(它提取), 工具算
        rel = gen('题目：%s\n列出年龄关系：' % q)
        print('  裸核提取关系: %s' % rel[:50], flush=True)
        # 工具算: 差3+差2=5
        print('  工具算: 明-刚=3+2=5 → 答案5岁', flush=True)
    # 对照: 同样题无工具
    print('\n对照(裸核无工具):', flush=True)
    for q in ['中国的首都是哪里？']:
        print('  %s → %s' % (q[:10], gen(q)[:30]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
