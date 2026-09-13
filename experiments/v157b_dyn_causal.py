#!/usr/bin/env python3
# V157b 动力学因果剪除(快速版): 用梯度近似因果重要性, 一次前向全单元
# importance_i ≈ |∂loss/∂gate_i * gate_i| (对输出影响 = 梯度×激活 = 因果贡献)
# 这比逐单元前向快千倍, 且是标准"动力学因果"度量(Taylor重要性)
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
L = 12
TEXTS = ['中国的首都是哪里？', '小明比小红大3岁小红比小刚大2岁十年后差几岁？', '秋天是什么样子？鲸鱼是什么动物？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    # 收集层12 gate激活 + 反向梯度
    gate_buf = {}
    h = model.model.layers[L].mlp.gate_proj.register_forward_hook(
        lambda m, i, o: gate_buf.__setitem__('g', o[0]))
    importance = np.zeros(4864)
    model.zero_grad()
    for t in TEXTS:
        ids = tok(t, return_tensors='pt').input_ids.to('cuda')
        out = model(input_ids=ids)
        logits = out.logits[0, -1]
        # 用logits的熵作为标量(对"输出结构"的敏感度)
        p = torch.softmax(logits, -1)
        loss = -(p * torch.log(p + 1e-9)).sum()   # 输出熵
        gate_act = gate_buf['g'][0]                # (seq,4864)
        model.zero_grad()
        loss.backward(retain_graph=False)
        # gate权重梯度
        gw = model.model.layers[L].mlp.gate_proj.weight.grad  # (4864,896)
        if gw is not None:
            imp = gw.abs().mean(1).float().cpu().numpy() * gate_act[-1].detach().float().cpu().numpy()
            importance += np.nan_to_num(imp) / len(TEXTS)
    h.remove()
    print('因果重要性(梯度×激活)计算完成', flush=True)
    print('分布: 中位=%.4f 前10%%>=%.4f 后50%%<=%.4f' % (
        np.median(importance), np.percentile(importance, 90), np.percentile(importance, 50)), flush=True)
    # 可删 = 因果重要性后50%(贡献微弱)
    for frac in [0.3, 0.5, 0.7]:
        th = np.percentile(importance, frac*100)
        droppable = np.where(importance < th)[0]
        sd = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd[WN].float().numpy()
        W[droppable, :] = 0.0
        sd[WN] = torch.tensor(W).to(sd[WN].dtype)
        model.load_state_dict(sd, strict=True)
        res = []
        with torch.no_grad():
            for t in ['中国的首都是哪里？', '小明比小红大3岁小红比小刚大2岁十年后差几岁？']:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=16, do_sample=False, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                res.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:16])
        print('剪后%.0f%%(弱因果): %s' % (frac*100, res), flush=True)
        model.load_state_dict({k: v.clone() for k, v in model.state_dict().items()})  # 保留(下次覆盖)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
