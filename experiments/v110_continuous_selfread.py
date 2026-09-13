#!/usr/bin/env python3
"""
V110 连续自读 — 每token都在读自己 (人脑式持续自指)
V08b: 慢S 每段(64token)才更新一次 = 世界线长城(保留, 慢时间尺度)
V110 新增: 快S 每生成1个token就更新并立即注入下一步 = 毫秒级自读
双时间尺度:
  快S_fast: EMA(β_f≈0.5) 每token → 注入层12 → 影响下一个token
           = "我此刻正在想什么"的持续自我参照
  慢S_slow: EMA(β_s≈0.1) 每token更新但变化慢 → 长程自我/世界线长城
验证: 逐token自读 vs 原版段级自读, 看生成质量/复读率/状态多样性
"""
import torch, numpy as np, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
B_F, B_S, ETA_F, ETA_S = 0.5, 0.08, 0.6, 1.2
SEEDS = [
    '爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，',
    '渔村的黄昏总是先落在灯塔上。老周提着最后一桶鱼油爬上石阶，潮水正在退去，露出大片湿漉漉的礁石，远处有船鸣了一声长笛。他把灯芯拨亮，光柱扫过海面时，',
]
MAX_TOK = 120

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    state = {'Sf': None, 'Ss': None, 'eta': 0.0, 'v': None, 'u': None}
    hook_handle = None

    def make_hook():
        def hook(mod, inp, out):
            if state['eta'] > 0 and state['v'] is not None:
                h = out[0] if isinstance(out, tuple) else out
                g = torch.matmul(h, state['u'])
                h = h + state['eta'] * g.unsqueeze(-1) * state['v']
                return (h,) if isinstance(out, tuple) else h
            return out
        return hook

    def hidden_of_last(ids):
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        return hs[LAYER+1][0, -1].float().cpu().numpy()

    def read_self_and_inject(v_norm):
        """读自己: 更新双慢状态并设注入"""
        if state['Sf'] is None:
            state['Sf'] = v_norm.copy()
            state['Ss'] = v_norm.copy()
        else:
            state['Sf'] = (1 - B_F) * state['Sf'] + B_F * v_norm
            state['Ss'] = (1 - B_S) * state['Ss'] + B_S * v_norm
        Sf_n = state['Sf'] / (np.linalg.norm(state['Sf']) + 1e-9)
        Ss_n = state['Ss'] / (np.linalg.norm(state['Ss']) + 1e-9)
        # 快S: 此刻自读注入; 慢S: 长城注入 (合并到v/u)
        v_mix = Sf_n + 0.5 * Ss_n
        v_mix = v_mix / (np.linalg.norm(v_mix) + 1e-9)
        state['v'] = torch.tensor(v_mix, dtype=torch.float16, device='cuda')
        state['u'] = torch.tensor(v_mix, dtype=torch.float16, device='cuda')
        return float(Sf_n @ Ss_n)   # 快慢一致性

    def gen_continuous(seed, max_tok=MAX_TOK):
        """逐token自读生成"""
        state['Sf'] = state['Ss'] = None
        state['eta'] = ETA_F
        ids = tok(seed, return_tensors='pt').input_ids.to('cuda')
        out = []
        cosfs = []
        for i in range(max_tok):
            v = hidden_of_last(ids)
            vn = v / (np.linalg.norm(v) + 1e-9)
            c = read_self_and_inject(vn)
            cosfs.append(c)
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0, -1]
            nid = torch.multinomial(torch.softmax(logits / 0.85, -1), 1)
            if nid.item() == tok.eos_token_id and i > 10:
                break
            ids = torch.cat([ids, nid.unsqueeze(0)], -1)
            out.append(nid.item())
            if (i + 1) % 30 == 0:
                print('    tok%d 快慢一致=%.3f' % (i + 1, c), flush=True)
        return tok.decode(out, skip_special_tokens=True), cosfs

    print('V110 连续自读 | 快S每token注入 β_f=%.2f + 慢S长城 β_s=%.2f' % (B_F, B_S), flush=True)
    hook_handle = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
    t0 = time.time()
    for name, seed in enumerate(SEEDS):
        print('\n=== 种子%d ===' % (name + 1), flush=True)
        text, cosfs = gen_continuous(seed)
        print('生成 %d 字 | 快慢一致性均值=%.3f' % (len(text), float(np.mean(cosfs)) if cosfs else 0), flush=True)
        print('片段: %s...' % text[:80], flush=True)
    hook_handle.remove()
    print('[done] %.0fs' % (time.time() - t0), flush=True)

if __name__ == '__main__':
    main()
