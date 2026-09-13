#!/usr/bin/env python3
# V157 动力学因果剪除: 单元重要性 = 删掉它, 输出状态流变多少
# 对每单元: gate输出置0 → 前向 → 末token logits 变化 ||Δ|| = 因果重要性
# 只测一层(12)先; 高因果=必留, 低因果=可删(真正对输出没影响的才是可删)
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
L = 12
TEXTS = ['中国的首都是哪里？', '小明比小红大3岁小红比小刚大2岁十年后差几岁？', '秋天是什么样子？鲸鱼是什么动物？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    ids_all = [tok(t, return_tensors='pt').input_ids.to('cuda') for t in TEXTS]
    # 基线 logits
    with torch.no_grad():
        base = [model(input_ids=ids).logits[0, -1].float().cpu() for ids in ids_all]
    # 逐单元因果测试(层12 gate): 该单元激活置0 → logits变化
    WN = 'model.layers.%d.mlp.gate_proj.weight' % L
    sd = {k: v.clone() for k, v in model.state_dict().items()}
    causal = np.zeros(4864)
    # 分批测(每批256单元): 直接改gate bias不可行, 用hook置0输出更快
    buf = {}
    orig_forward = model.model.layers[L].mlp.gate_proj.forward
    import types
    def make_forward(mask):
        def fwd(x):
            h = orig_forward(x)
            return h * mask
        return fwd
    with torch.no_grad():
        for start in range(0, 4864, 512):
            mask = torch.ones(1, 1, 4864, dtype=torch.float16, device="cuda")
            # 逐个单元测: 一次测一个512块内单元, 掩掉该单元
            for j in range(start, min(start+512, 4864)):
                m2 = torch.ones(1, 1, 4864, dtype=torch.float16, device="cuda")
                m2[0, 0, j] = 0.0
                model.model.layers[L].mlp.gate_proj.forward = make_forward(m2)
                d = 0
                for ids, b in zip(ids_all, base):
                    lg = model(input_ids=ids).logits[0, -1].float().cpu()
                    d += (lg - b).norm().item()
                causal[j] = d / len(ids_all)
            model.model.layers[L].mlp.gate_proj.forward = orig_forward
            print('  批次 %d-%d 完成' % (start, min(start+512, 4864)), flush=True)
    # 报告: 因果重要性分布
    print('\n=== 因果重要性(层%d) ===' % L, flush=True)
    print('因果值: 中位=%.3f 前10%%>=%.3f 后50%%<=%.3f 后90%%<=%.3f' % (
        np.median(causal), np.percentile(causal, 90), np.percentile(causal, 50), np.percentile(causal, 10)), flush=True)
    # 可删候选: 因果<后30%分位(对输出几乎无影响)
    th = np.percentile(causal, 30)
    droppable = np.where(causal < th)[0]
    print('可删候选(因果<%.3f): %d 单元 (%.1f%%)' % (th, len(droppable), 100*len(droppable)/4864), flush=True)
    # 删掉试试
    sd2 = {k: v.clone() for k, v in model.state_dict().items()}
    W = sd2[WN].float().numpy()
    W[droppable, :] = 0.0
    sd2[WN] = torch.tensor(W).to(sd2[WN].dtype)
    model.load_state_dict(sd2, strict=True)
    print('\n=== 删后测试 ===', flush=True)
    with torch.no_grad():
        for t in TEXTS:
            ids = tok(t, return_tensors='pt').input_ids.to('cuda')
            o = model.generate(ids, max_new_tokens=20, do_sample=False, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
            print('  %s → %s' % (t[:12], tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)[:25]), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
