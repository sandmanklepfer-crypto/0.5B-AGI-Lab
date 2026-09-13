#!/usr/bin/env python3
"""
V112 三层自读 装在"大融合模型" antiheb_05b 上
antiheb_05b = qwen25_base_raw + 层12 anti-Hebbian活机制 + (层20 知识/推理分块可后接)
本脚本: 三层自读(快每token/中每10/慢每40) 在 antiheb_05b 上跑
对比: base_raw vs antiheb_05b, 同种子同参数
看: 融合体(活机制底子) 上自读是否更好(更稳/更少跑偏/内容更活)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

LAYER = 12
B_F, B_M, B_S = 0.5, 0.2, 0.08
W_F, W_M, W_S = 1.0, 0.5, 0.3
MID_EVERY, SLOW_EVERY = 10, 40
MAX_TOK = 150
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    st = {'eta': 0.0, 'v': None, 'u': None}
    for mdir, label in [('/root/autodl-tmp/qwen25_base_raw', 'base_raw'),
                        ('/root/autodl-tmp/life1/antiheb_05b', 'antiheb融合体')]:
        print('\n' + '=' * 60, flush=True)
        print('模型: %s' % label, flush=True)
        model = AutoModelForCausalLM.from_pretrained(mdir, torch_dtype=torch.float16).to('cuda').eval()

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

        def run():
            Sf = Sm = Ss = None
            ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
            out = []
            st['eta'] = 1.0
            for i in range(MAX_TOK):
                v = last_hidden(ids)
                vn = v / (np.linalg.norm(v) + 1e-9)
                Sf = vn if Sf is None else (1 - B_F) * Sf + B_F * vn
                mix = Sf / (np.linalg.norm(Sf) + 1e-9)
                if Sm is None or i % MID_EVERY == 0:
                    Sm = vn if Sm is None else (1 - B_M) * Sm + B_M * vn
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
            return tok.decode(out, skip_special_tokens=True)

        hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
        t0 = time.time()
        text = run()
        hook.remove()
        rep = sum(len(m.group(1)) for m in re.finditer(r'(.{6,})\1', text))
        print('生成%d字 复读=%d | %.0fs' % (len(text), rep, time.time() - t0), flush=True)
        print('片段: %s...' % text[:130], flush=True)
        del model
        torch.cuda.empty_cache()

if __name__ == '__main__':
    main()
