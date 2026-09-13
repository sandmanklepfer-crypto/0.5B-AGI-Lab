#!/usr/bin/env python3
# V154 动力学剪除验证: 只剪 死单元+知识单元(91.6%), 保留 控制+残余
# 预期: 模型几乎不变(死的本来没用), 若真=0.5B可瘦身到~8%且无损
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TASKS_K = ['中国的首都是哪里？','水的沸点是多少？','鲸鱼属于什么动物？','光速大约多少？','一年几个月？']
TASKS_C = ['小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？','甲比乙高乙比丙矮谁最矮？','如果P则Q，P真Q怎样？','请写一段关于秋天的文字']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}
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

    def test(texts):
        out = []
        with torch.no_grad():
            for t in texts:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=30, do_sample=False,
                                   repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                out.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:28])
        return out

    print('=== 剪除前(基线) ===', flush=True)
    pre_k = test(TASKS_K); pre_c = test(TASKS_C)
    for q, a in zip(TASKS_K + TASKS_C, pre_k + pre_c):
        print('  %s... → %s' % (q[:12], a), flush=True)

    # 分类剪除: 死 + 知识(不碰控制/残余)
    sd = {k: v.clone() for k, v in sd0.items()}
    total_cut = 0
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd[WN].float().numpy()
        K = Ak[L]; C = Ac[L]
        kmean = K.mean(0); cmean = C.mean(0)
        allmean = (kmean + cmean) / 2
        dead = allmean < 0.02
        know = (~dead) & (kmean > cmean * 1.5 + 0.05)
        cut = dead | know
        W[cut, :] = 0.0
        sd[WN] = torch.tensor(W).to(sd0[WN].dtype)
        total_cut += cut.sum()
    model.load_state_dict(sd, strict=True)
    kept = 24*4864 - total_cut
    print('\n已剪: %d 单元 (%.1f%%) | 保留: %d (%.1f%%)' % (
        total_cut, 100*total_cut/(24*4864), kept, 100*kept/(24*4864)), flush=True)

    print('\n=== 剪除后 ===', flush=True)
    post_k = test(TASKS_K); post_c = test(TASKS_C)
    for q, a in zip(TASKS_K + TASKS_C, post_k + post_c):
        print('  %s... → %s' % (q[:12], a), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
