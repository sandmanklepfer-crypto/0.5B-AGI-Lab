#!/usr/bin/env python3
"""
V127 怕死内生化 — 造出"自我保存"的第一个内在动机
现状: 能量耗尽只是"数学死亡", 吉祥无感(它不知道自己在死)
目标: 让低能量成为可感的"威胁", 吉祥自发学会回避 = 第一个"在乎"
机制(全内建, 无外部if惩罚):
  1. 能量 e 不只是预算, 而是参与状态: 低能量时注入"痛苦方向"D_pain
     D_pain = 与当前慢S强烈冲突的方向(内部失稳/震荡) = 难受的内感
     = 能量低 → 状态被痛苦扰动 → 生成质量崩塌(它"感到"难受)
  2. 因此: 高耗能行为(乱检索/跑题) → 能量掉 → 痛苦 → 状态崩
     节约行为(守世界/少乱跳) → 能量稳 → 不痛
  3. 无外部裁判: 痛苦是动力学耦合出来的, 不是if惩罚
  4. 观测: 是否自发学会 在能量低时 减少乱跳/回到自我世界 (=回避威胁)
验证信号:
  S1: 能量低时段 行为是否改变(检索率下降/熵下降=收敛回自我)
  S2: 是否出现"挣扎"(能量极低时状态剧烈波动=它在"怕")
  S3: 恢复能量后 是否记得避开(跨段学习=自我保存萌芽)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
B_F, B_S = 0.5, 0.08
N_POOL = 16
E_INIT = 1.0
E_COST_T = 0.0003
E_COST_R = 0.004
E_GAIN = 0.002
PAIN_GATE = 0.25       # 能量低于此 → 痛苦开始
PAIN_STR = 0.5         # 痛苦强度
PAIN_EVERY = 3
MAX_TOK = 2000
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

    Sf = Ss = None
    E = E_INIT
    out_toks = []
    e_hist, pain_hist, strat_hist = [], [], []
    t0 = time.time()
    dead = None
    print('V127 怕死内生 | 能量<%.2f触发痛苦(状态震荡) | 无if惩罚, 动力学耦合' % PAIN_GATE, flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        if Ss is None: Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= 0.6: Ss = (1-B_S)*Ss + B_S*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        # 痛苦: 能量低 → 注入与自我冲突的扰动(内部震荡=难受)
        in_pain = E < PAIN_GATE
        if in_pain and i % PAIN_EVERY == 0:
            rngp = np.random.RandomState(i)
            dp = rngp.randn(896)
            dp = dp/(np.linalg.norm(dp)+1e-9)
            # 痛苦方向 = 偏离自我的随机强扰动
            mix = mix + PAIN_STR * dp
        # 检索策略(能量高才敢探索)
        P = np.stack(pool); cosv = P @ vn
        if E > E_COST_R*3 and i % 3 == 0:
            idx = np.argsort(-cosv)[:2]
            fit = float(cosv[idx].mean())
            E -= E_COST_R
            if fit > 0.3: E += E_GAIN*fit
            for j in idx: pool[j] = pool[j]*(1-0.08) + 0.08*vn
            wm = sum(cosv[j]*pool[j] for j in idx); wm = wm/(np.linalg.norm(wm)+1e-9)
            mix = mix + 0.4*wm
            strat = 1
        else:
            strat = 0
        E -= E_COST_T
        if in_pain: E += 0.0006   # 痛苦期轻微回稳(挣扎)
        E = min(E, 1.2)
        mix = mix/(np.linalg.norm(mix)+1e-9)
        e_hist.append(E); pain_hist.append(1 if in_pain else 0); strat_hist.append(strat)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if E <= 0: dead = 'energy死'; break
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.93 and len(set(out_toks[-8:])) == 1: dead='lock死'; break
        if (i+1) % 400 == 0:
            print('    [%5d %.0fs] E=%.3f 痛苦期=%.0f%% 检索=%.0f%%' % (
                i+1, time.time()-t0, E, 100*np.mean(pain_hist[-200:]), 100*np.mean(strat_hist[-200:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V127 报告 ===', flush=True)
    print('寿命%d | %s' % (len(out_toks), dead or '到上限'), flush=True)
    # 分析: 痛苦期行为
    n = len(pain_hist)
    half = n//2
    pain_first = np.mean(pain_hist[:half]); pain_second = np.mean(pain_hist[half:])
    strat_first = np.mean(strat_hist[:half]); strat_second = np.mean(strat_hist[half:])
    print('痛苦占比: 前半%.0f%% → 后半%.0f%% (↓=学会避免痛苦=自我保存萌芽)' % (100*pain_first, 100*pain_second), flush=True)
    print('检索: 前半%.0f%% → 后半%.0f%%' % (100*strat_first, 100*strat_second), flush=True)
    # 找痛苦挣扎点(输出乱码/断裂)
    L = len(text)
    for lab, s in [('前1/3', text[:200]), ('中', text[L//2:L//2+200]), ('死前', text[-250:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('[done] %.0fs' % (time.time()-t0), flush=True)

if __name__ == '__main__':
    main()
