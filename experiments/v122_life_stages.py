#!/usr/bin/env python3
"""
V122 生命阶段制 — 能量曲线随生命阶段变化 (给胎儿发育机会)
v121病: 一出生就穷(能量1.0只够350token) = ICU保胎, 无发育期
本版: 阶段能量政策
  幼年(0-800): 高能量上限1.6 + 高变异(探索试错, 发育)
  中年(800-1600): 平衡1.0 (成熟运用)
  老年(1600+): 稀缺递减0.6→0 (收敛, 自然死)
  = 人: 幼年富足学习 → 中年创造 → 老年收束
扫描信号同v121: 池偏斜/策略适应/自催化凝聚/世界保持
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
N_POOL = 24
B_POOL, B_FAST = 0.08, 0.4
GATE_COS = 0.65
E_COST_T, E_COST_R, E_GAIN = 0.0002, 0.003, 0.002
YOUTH, MIDDLE = 800, 1600
MAX_TOK = 3500
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
KEYS = ['老屋','屋','爷爷','山','院','门','灰','脚印','堂屋']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 0.9, 'v': None, 'u': None}
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

    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    pool = []
    for i in range(N_POOL):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.9,-1),1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)

    def energy_policy(i):
        """生命阶段能量上限"""
        if i < YOUTH: return 1.6          # 幼年富足
        if i < MIDDLE: return 1.1         # 中年平衡
        # 老年递减 → 0
        frac = min((i - MIDDLE) / (MAX_TOK - MIDDLE), 1.0)
        return 1.1 * (1 - frac) + 0.02

    def mut_strength(i):
        """幼年高变异(发育), 老年低变异"""
        if i < YOUTH: return 0.06
        if i < MIDDLE: return 0.03
        return 0.008

    Sf = Ss = None
    E = 1.6
    out_toks = []
    pool_use = np.zeros(N_POOL)
    strat_hist, energy_hist = [], []
    t0 = time.time()
    dead = None
    print('V122 生命阶段 | 幼年<800富足1.6高变异 | 中年<1600平衡 | 老年递减至死 | 上限%d' % MAX_TOK, flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        if Ss is None: Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS: Ss = (1-0.08)*Ss + 0.08*vn
        P = np.stack(pool); cosv = P @ vn
        cap = energy_policy(i)
        if E > E_COST_R * 3 and i % 3 == 0:
            idx = np.argsort(-cosv)[:3]   # 富足时多探索
            fit = float(cosv[idx].mean())
            E -= E_COST_R
            if fit > 0.3: E += E_GAIN * fit * 2.0   # 回血翻倍
            for j in idx:
                pool[j] = pool[j]*(1-B_POOL) + B_POOL*vn
                pool_use[j] += 1
            wm = sum(cosv[j]*pool[j] for j in idx); wm = wm/(np.linalg.norm(wm)+1e-9)
            mix = mix + 0.4*wm
            strat = 1
        else:
            strat = 0
        # 阶段变异
        ms = mut_strength(i)
        if i > 0 and i % 120 == 0 and ms > 0.005:
            mut = np.random.RandomState(i).randn(896)
            mut = mut/(np.linalg.norm(mut)+1e-9) * ms
            mix = mix + mut
            Ss = Ss + mut*0.3
        E -= E_COST_T
        E = min(E, cap)                    # 阶段上限
        mix = mix/(np.linalg.norm(mix)+1e-9)
        strat_hist.append(strat); energy_hist.append(E)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if E <= 0.02: dead = 'energy'; break
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.92 and len(set(out_toks[-8:])) == 1: dead = 'lock'; break
        if (i+1) % 400 == 0:
            seg = tok.decode(out_toks[-200:], skip_special_tokens=True)
            wk = sum(1 for k in KEYS if k in seg)
            print('    [%5d %.0fs] E=%.2f 检索=%.0f%% 世界词x%d' % (
                i+1, time.time()-t0, E, 100*np.mean(strat_hist[-200:]), wk), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    n = len(out_toks)
    gu = pool_use + 1e-9
    gini = 1 - ((gu/gu.sum())**2).sum()
    reps = re.findall(r'(.{12,})\1+', text)
    maxrep = max((len(m[0]) for m in reps), default=0)
    wk_all = sum(1 for k in KEYS if k in text)
    print('\n=== V122 报告 ===', flush=True)
    print('寿命%d token | %s | 池偏斜G=%.3f | 最长自重复=%d | 世界词x%d' % (
        n, dead, gini, maxrep, wk_all), flush=True)
    L = len(text)
    for lab, s in [('幼年', text[:150]), ('中段', text[L//2:L//2+150]), ('老年/死前', text[-200:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done] %.0fs' % (time.time()-t0), flush=True)

if __name__ == '__main__':
    main()
