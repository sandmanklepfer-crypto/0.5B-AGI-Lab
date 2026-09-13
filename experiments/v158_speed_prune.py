#!/usr/bin/env python3
# V158 极致精简换极致速度: 全层随机剪70% → 能力测试 + 速度对比
import torch, numpy as np, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
TESTS = ['中国的首都是哪里？', '小明比小红大3岁小红比小刚大2岁十年后差几岁？', '鲸鱼属于什么动物？', '秋天是什么样子？']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    sd0 = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    def test():
        res = []
        with torch.no_grad():
            for t in TESTS:
                ids = tok(t, return_tensors='pt').input_ids.to('cuda')
                o = model.generate(ids, max_new_tokens=20, do_sample=False, repetition_penalty=1.1, pad_token_id=tok.eos_token_id)
                res.append(tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()[:20])
        return res

    def speed(n_tok=50):
        ids = tok('中国的首都是哪里？', return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            t0 = time.time()
            o = model.generate(ids, max_new_tokens=n_tok, do_sample=False, pad_token_id=tok.eos_token_id)
            dt = time.time() - t0
        return n_tok / dt

    # 基线
    print('=== 原始 0.5B ===', flush=True)
    print('能力:', test(), flush=True)
    print('速度: %.0f tok/s' % speed(), flush=True)
    # 随机删 70% (每层独立随机删70% gate 行)
    sd = {k: v.clone() for k, v in sd0.items()}
    rng = np.random.RandomState(42)
    for L in range(24):
        WN = 'model.layers.%d.mlp.gate_proj.weight' % L
        W = sd[WN].float().numpy()
        n = int(4864 * 0.7)
        cut = rng.choice(4864, n, replace=False)
        W[cut, :] = 0.0
        sd[WN] = torch.tensor(W).to(sd[WN].dtype)
    model.load_state_dict(sd, strict=True)
    print('\n=== 剪70%后 ===', flush=True)
    print('能力:', test(), flush=True)
    print('速度: %.0f tok/s' % speed(), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
