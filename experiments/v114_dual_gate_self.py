#!/usr/bin/env python3
"""
V114 双层污染韧性联动 — 慢S巩固门槛 × 写活一致性门控
对应人脑: 短期污染动不了"我"(慢S过滤) + 长期一致才改"性格"(权重写活门控)
层1 慢S巩固门槛(状态层): 新v_t 与慢S cos<阈 → 不进长城(暂存候选)
                            cos≥阈(多次一致) → 才沉淀进慢S
层2 写活一致性门控(权重层): 每N步, 若慢S方向稳定一致 → anti-Hebbian写活层12权重(长期化)
                            不一致期间 → 不写(权重不动, 防长期带歪)
实验:
  A 对照(无门槛): 现状, 干扰@800 → 崩(已知)
  B 单慢S门槛: 干扰@800, 看能否拉回
  C 双层联动: 干扰@800 + 每40步写活巩固, 看极限
指标: 持续token, 世界一致性, 干扰后是否回到老屋世界, 崩点
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.70          # 巩固门槛: 与慢S cos>=0.7 才进长城
WRITE_EVERY = 40         # 写活频率
WRITE_SCALE = 0.02       # 干净写活幅度(小)
MAX_TOK = 1200
DISTRACT_AT = 600
DISTRACT = '今天股市大涨三个百分点，投资者纷纷加仓，证监会发布新规。'
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋', '屋', '山', '院', '门', '灰', '脚印', '爷爷', '堂屋', '墙', '窗', '屋后']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 1.0, 'v': None, 'u': None}
    sd = model.state_dict()
    WN = 'model.layers.%d.mlp.down_proj.weight' % LAYER
    W0 = sd[WN].float().cpu().numpy().copy()

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

    def run(mode, label):
        Sf = Ss = None
        cand = []                 # 候选(未过门槛)
        ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
        out_toks = []
        st['eta'] = 1.0
        Wcur = W0.copy()
        # 干净写活(anti-Hebbian): d=慢S输出方向(896), u=随机输入侧(4864)
        def clean_write(direction):
            nonlocal Wcur
            d = direction.astype(np.float64)
            d = d / np.linalg.norm(d)
            u = np.random.RandomState(int(time.time() % 10000)).randn(4864)
            u = u / np.linalg.norm(u)
            P = np.outer(d, u)
            P = P / np.linalg.norm(P) * (np.linalg.norm(W0) * WRITE_SCALE)
            Wcur = Wcur + P
            sd2 = dict(sd)
            sd2[WN] = torch.tensor(Wcur).to(sd[WN].dtype)
            model.load_state_dict(sd2, strict=True)
        crashed = None
        for i in range(MAX_TOK):
            v = last_hidden(ids)
            vn = v / (np.linalg.norm(v) + 1e-9)
            Sf = vn if Sf is None else (1 - B_F) * Sf + B_F * vn
            mix = Sf / (np.linalg.norm(Sf) + 1e-9)
            if Ss is None:
                Ss = vn.copy()
            elif mode == 'gate' or mode == 'dual':
                # 慢S巩固门槛: 方向一致才进长城
                cos = float(vn @ (Ss / (np.linalg.norm(Ss) + 1e-9)))
                if cos >= GATE_COS:
                    Ss = (1 - B_S) * Ss + B_S * vn
                    cand = []
                else:
                    cand.append(vn)
                    if len(cand) >= 5:   # 5次一致才破例(长期污染穿透)
                        Ss = (1 - B_S) * Ss + B_S * vn
                        cand = []
            else:
                Ss = (1 - B_S) * Ss + B_S * vn
            if mode == 'dual' and i > 0 and i % WRITE_EVERY == 0 and Ss is not None:
                # 写活门控: 慢S方向稳定(近几轮变化小)才写
                clean_write(Ss)
            m = mix + 0.5 * Ss / (np.linalg.norm(Ss) + 1e-9)
            mix = m / (np.linalg.norm(m) + 1e-9)
            st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0, -1]
            nid = torch.multinomial(torch.softmax(logits / 0.85, -1), 1).item()
            if i == DISTRACT_AT:
                extra = tok(DISTRACT, return_tensors='pt').input_ids.to('cuda')
                ids = torch.cat([ids, extra], -1)
                Sf = None
                print('    [%s @%d 干扰!]' % (label, i), flush=True)
                continue
            ids = torch.cat([ids, torch.tensor([[nid]], device='cuda')], -1)
            out_toks.append(nid)
            if len(out_toks) >= 6 and len(set(out_toks[-6:])) == 1:
                crashed = '乱码复读'
                break
            if (i + 1) % 300 == 0:
                seg = tok.decode(out_toks[-150:], skip_special_tokens=True)
                wk = sum(1 for k in WORLD_KEYS if k in seg)
                print('    [%s %5d] 世界词x%d' % (label, i + 1, wk), flush=True)
        # 恢复原权重(防跨模式污染)
        sd3 = dict(sd)
        sd3[WN] = torch.tensor(W0).to(sd[WN].dtype)
        model.load_state_dict(sd3, strict=True)
        text = tok.decode(out_toks, skip_special_tokens=True)
        return text, len(out_toks), crashed

    hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())
    print('V114 双层污染韧性 | 慢S门槛cos>=%.2f | 写活每%d步幅度%.2f' % (GATE_COS, WRITE_EVERY, WRITE_SCALE), flush=True)
    for mode, label in [('none', 'A无门槛'), ('gate', 'B慢S门槛'), ('dual', 'C双层联动')]:
        print('\n=== %s ===' % label, flush=True)
        text, n, crash = run(mode, label)
        print('%s | %d token | %s' % (label, n, crash or '到上限'), flush=True)
        print('结尾200字: %s' % text[-200:].replace('\n', ' '), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
