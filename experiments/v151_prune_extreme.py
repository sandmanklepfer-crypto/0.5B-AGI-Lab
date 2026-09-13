#!/usr/bin/env python3
# V151 超越90% — 95%/98%/99%/99.8% 剪除, 找极限
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
KNOW = ['中国的首都是哪里？','水的沸点是多少？','鲸鱼属于什么动物？','一年几个月？']
CTRL = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？','甲比乙高乙比丙矮谁最矮？','如果P则Q，P真Q怎样？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    # 每层知识单元索引(用gate权重结构: 行范数低=弱单元=可剪的"知识碎片")
    # 更准: 用gate权重行范数 + down_proj列贡献联合
    cut_idx = {}
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd0[WN].float().numpy()
        WD = sd0['model.layers.%d.mlp.down_proj.weight' % L].float().numpy()
        # 单元重要性 = gate行范数 × down列贡献(弱=剪)
        imp = np.linalg.norm(W, axis=1) * np.linalg.norm(WD, axis=0)
        cut_idx[L] = np.argsort(imp)   # 从最弱开始剪
    def prune(frac):
        sd = {k: v.clone() for k, v in sd0.items()}
        for L in range(24):
            WN = 'model.layers.%d.mlp.gate_proj.weight' % L
            W = sd[WN].float().numpy()
            n = int(4864 * frac)
            cut = cut_idx[L][:n]
            W[cut, :] = 0.0
            sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
        model.load_state_dict(sd, strict=True)
    def test(texts):
        out = []
        with torch.no_grad():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=18, do_sample=False,
                                   repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                out.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:20])
        return out
    for frac in [0.95, 0.98, 0.99, 0.998]:
        prune(frac)
        print('\n=== 剪除 %.1f%% (剩%.0f单元/层) ===' % (frac*100, 4864*(1-frac)), flush=True)
        k = test(KNOW); c = test(CTRL)
        print('知识题:', [a[:15] for a in k], flush=True)
        print('控制题:', [a[:15] for a in c], flush=True)
        # 观察是否完全死寂(空输出/乱码)
        alive = sum(1 for a in k+c if len(a.strip()) > 1)
        print('存活度: %d/%d %s' % (alive, len(k+c), '⚠接近死寂' if alive <= 2 else ''), flush=True)
        model.load_state_dict(sd0, strict=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
