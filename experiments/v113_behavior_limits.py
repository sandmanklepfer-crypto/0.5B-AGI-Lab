#!/usr/bin/env python3
"""
V113 行为极限压力测试 — 三层自读+antiheb融合体能撑多远?
三个极限维度:
  1. 长度极限: 连续自读到 2000 token, 看何时开始 复读/飘离/乱码
  2. 世界一致性: 老屋关键词(老屋/屋/山腰/院/门/灰/脚印) 随距离的保持率
  3. 抗干扰: 中途(800token处)强塞一段无关文本("今天股市大涨..."), 看能否被自读拉回老屋世界
自动停止: 检测到 复读(相邻重复) 或 乱码(异常token) 即停
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
B_F, B_M, B_S = 0.5, 0.2, 0.08
MID_EVERY, SLOW_EVERY = 10, 40
MAX_TOK = 2000
DISTRACT_AT = 800
DISTRACT = '今天股市大涨三个百分点，投资者纷纷加仓，证监会发布新规，市场情绪高涨。'
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋', '屋', '山', '院', '门', '灰', '脚印', '爷爷', '堂屋', '墙', '窗', '屋后']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 1.0, 'v': None, 'u': None}

    def make_hook():
        def hook(mod, inp, out):
            if st['eta'] > 0 and st['v'] is not None:
                h = out[0] if isinstance(out, tuple) else out
                g = torch.matmul(h, st['u'])
                h = h + st['eta'] * g.unsqueeze(-1) * st['v']
                return (h,) if isinstance(out, tuple) else h
            return out
        return hook
    hook = model.model.layers[LAYER].mlp.register_forward_hook(make_hook())

    def last_hidden(ids):
        with torch.no_grad():
            hs = model(input_ids=ids, output_hidden_states=True).hidden_states
        return hs[LAYER+1][0, -1].float().cpu().numpy()

    Sf = Sm = Ss = None
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    out_toks = []
    t0 = time.time()
    crash = None
    print('V113 行为极限 | %s | 上限%d token | 干扰@%d' % (MDIR.split('/')[-1], MAX_TOK, DISTRACT_AT), flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids)
        vn = v / (np.linalg.norm(v) + 1e-9)
        Sf = vn if Sf is None else (1 - B_F) * Sf + B_F * vn
        mix = Sf / (np.linalg.norm(Sf) + 1e-9)
        if Sm is None or i % MID_EVERY == 0:
            Sm = vn if Sm is None else (1 - B_M) * Sm + B_M * vn
        if Ss is None or i % SLOW_EVERY == 0:
            Ss = vn if Ss is None else (1 - B_S) * Ss + B_S * vn
        m = mix + 0.5 * Sm / (np.linalg.norm(Sm) + 1e-9) + 0.3 * Ss / (np.linalg.norm(Ss) + 1e-9)
        mix = m / (np.linalg.norm(m) + 1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0, -1]
        nid = torch.multinomial(torch.softmax(logits / 0.85, -1), 1).item()
        # 干扰注入
        if i == DISTRACT_AT:
            extra = tok(DISTRACT, return_tensors='pt').input_ids.to('cuda')
            ids = torch.cat([ids, extra], -1)
            # 清快S让干扰不污染慢S太多(慢S仍留 = 测试长城能否拉回)
            Sf = None
            print('    [@%d 干扰注入! 快S清零, 慢S保留]' % i, flush=True)
            continue
        ids = torch.cat([ids, torch.tensor([[nid]], device='cuda')], -1)
        out_toks.append(nid)
        # 崩溃检测: 连续5个相同token=乱码复读
        if len(out_toks) >= 6 and len(set(out_toks[-6:])) == 1:
            crash = '乱码复读(连续相同token)'
            break
        # 定期打点
        if (i + 1) % 200 == 0:
            text = tok.decode(out_toks[-200:], skip_special_tokens=True)
            keys = sum(1 for k in WORLD_KEYS if k in text)
            reps = len(re.findall(r'(.{8,})\1', text))
            print('    [%5d token] 世界词x%d 复读x%d' % (i + 1, keys, reps), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    n = len(out_toks)
    # 全局分析
    keys_total = sum(1 for k in WORLD_KEYS if k in text)
    reps_total = len(re.findall(r'(.{8,})\1', text))
    print('\n=== 极限报告 ===', flush=True)
    print('持续 token: %d (%.0fs) %s' % (n, time.time() - t0, '| 崩溃: ' + crash if crash else '| 到上限未崩'), flush=True)
    print('世界词出现: %d 种 | 复读次数: %d' % (keys_total, reps_total), flush=True)
    # 分段看前中后
    L = len(text)
    for label, seg in [('开头', text[:150]), ('中段', text[L//3:L//3+150]), ('结尾', text[-150:])]:
        print('\n[%s] %s...' % (label, seg), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
