#!/usr/bin/env python3
# V150 极限剪除 — 全24层剪知识单元, 逐步加大比例(50%/70%/90%), 看极限
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
KNOW = ['中国的首都是哪里？','水的沸点是多少？','鲸鱼属于什么动物？','一年几个月？']
CTRL = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？','甲比乙高乙比丙矮谁最矮？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.clone() for k, v in model.state_dict().items()}
    # 收集所有层 gate 激活
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
    Ak = collect(KNOW); Ac = collect(CTRL)
    for hh in handles: hh.remove()
    # 每层知识单元 = 知识激活 - 控制激活 顶X%
    def prune(frac):
        sd = {k: v.clone() for k, v in sd0.items()}
        n_cut = 0
        for L in range(24):
            WN = 'model.layers.%d.mlp.gate_proj.weight' % L
            W = sd[WN].float().cpu().numpy().copy()
            know_str = Ak[L].mean(0); ctrl_str = Ac[L].mean(0)
            spec = know_str - ctrl_str
            th = np.percentile(spec, 100 - frac)
            cut = np.where(spec > th)[0]
            W[cut, :] = 0.0
            sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
            n_cut += len(cut)
        model.load_state_dict(sd, strict=True)
        return n_cut
    def test(texts):
        out = []
        with torch.no_grad():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=20, do_sample=False,
                                   repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                out.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:22])
        return out
    for frac in [0.3, 0.5, 0.7, 0.9]:
        n = prune(frac)
        print('\n=== 剪除 %.0f%% (每层%d单元) ===' % (frac*100, n//24), flush=True)
        k = test(KNOW); c = test(CTRL)
        print('知识题:', [a[:16] for a in k], flush=True)
        print('控制题:', [a[:16] for a in c], flush=True)
        # 恢复
        model.load_state_dict(sd0, strict=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
