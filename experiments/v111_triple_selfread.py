#!/usr/bin/env python3
"""
V111 三层自读 — 人脑式多时间尺度自我参照
层1 快S_fast:  每 token 更新 EMA(β=0.5) → 立即注入   = γ工作自读(~0.01s)
层2 中S_mid:   每 10 token 回看更新 EMA(β=0.2) → 注入 = θ情境自读(~0.2s)
层3 慢S_slow:  每 40 token(段) 更新 EMA(β=0.08)      = 自传体长城(秒级)
三层都注入, 快为主慢为辅 (权重: 快1.0 中0.5 慢0.3)
对比: 单快层(v110) vs 三层, 看 生成多样性/一致性
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
B_F, B_M, B_S = 0.5, 0.2, 0.08
W_F, W_M, W_S = 1.0, 0.5, 0.3
MID_EVERY, SLOW_EVERY = 10, 40
MAX_TOK = 150
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 0.0, 'v': None, 'u': None}

    def make_hook():
        def hook(mod, inp, out):
            if st['eta'] > 0 and st['v'] is not None:
                h = out[0] if isinstance(out, tuple) else out
                g = torch.matmul(h, st['u'])
                h = h + st['eta'] * g.unsqueeze(-1) * st['v']
                return (h,) if isinstance(out, tuple) else h
            return out
        return hook

    def last_hidden(ids):
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        return hs[LAYER+1][0, -1].float().cpu().numpy()

    def run(mode, max_tok=MAX_TOK):
        """mode: 'fast'(单快) / 'triple'(三层)"""
        Sf = Sm = Ss = None
        ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
        out, cosfm, cosfs = [], [], []
        st['eta'] = 1.0
        for i in range(max_tok):
            v = last_hidden(ids)
            vn = v / (np.linalg.norm(v) + 1e-9)
            # 层1 快: 每token
            Sf = vn if Sf is None else (1 - B_F) * Sf + B_F * vn
            mix = Sf / (np.linalg.norm(Sf) + 1e-9)
            if mode == 'triple':
                # 层2 中: 每MID_EVERY
                if Sm is None or i % MID_EVERY == 0:
                    Sm = vn if Sm is None else (1 - B_M) * Sm + B_M * vn
                # 层3 慢: 每SLOW_EVERY
                if Ss is None or i % SLOW_EVERY == 0:
                    Ss = vn if Ss is None else (1 - B_S) * Ss + B_S * vn
                m = mix + W_M * Sm / (np.linalg.norm(Sm) + 1e-9) + W_S * Ss / (np.linalg.norm(Ss) + 1e-9)
                mix = m / (np.linalg.norm(m) + 1e-9)
            st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0, -1]
            nid = torch.multinomial(torch.softmax(logits / 0.85, -1), 1)
            if nid.item() == tok.eos_token_id and i > 20:
                break
            ids = torch.cat([ids, nid.unsqueeze(0)], -1)
            out.append(nid.item())
        text = tok.decode(out, skip_special_tokens=True)
        # 复读检测(低多样性指标)
        rep = 0
        for m in re.finditer(r'(.{6,})\1', text):
            rep += len(m.group(1))
        return text, rep, len(text)

    hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
    t0 = time.time()
    print('V111 三层自读 | 快每token+中每%d+慢每%d | 权重 %.1f/%.1f/%.1f' % (
        MID_EVERY, SLOW_EVERY, W_F, W_M, W_S), flush=True)
    for mode in ['fast', 'triple']:
        text, rep, n = run(mode)
        print('\n=== %s ===' % ('单快层' if mode == 'fast' else '三层自读'), flush=True)
        print('生成%d字 复读长度=%d (小=好)' % (n, rep), flush=True)
        print('片段: %s...' % text[:120], flush=True)
    hook.remove()
    print('\n[done] %.0fs' % (time.time() - t0), flush=True)

if __name__ == '__main__':
    main()
