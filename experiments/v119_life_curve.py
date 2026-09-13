#!/usr/bin/env python3
"""
V119 生命弧线观测 — 不干预, 让token冲突自然决定生死
用户设计: 不同token候选间有概率分布/互斥/冲突
  → 冲突 = 生命力(还有真选择)
  → 冲突耗尽(top1碾压) = 自然死亡
本实验: 纯观测, 无固化/无防复读/无拉回
每步记录: 冲突度 = 1-(p_top1-p_top2)   (0=锁死, 1=完全冲突)
        熵 H = -Σp log p
停止: top1概率>0.92 持续 8 步 = 冲突耗尽(自然死亡), 或到上限
输出: 冲突曲线(出生/创造/起伏/衰老/死) + 文本轨迹 + 死因
"""
import torch, numpy as np, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
B_F, B_M, B_S = 0.5, 0.2, 0.08
MID_EVERY, SLOW_EVERY = 10, 40
MAX_TOK = 3000
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

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
    conflicts, entropies = [], []
    t0 = time.time()
    dead = None
    print('V119 生命弧线 | 不干预, token冲突定生死 | 上限%d' % MAX_TOK, flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        if Sm is None or i % MID_EVERY == 0:
            Sm = vn if Sm is None else (1-B_M)*Sm + B_M*vn
        if Ss is None or i % SLOW_EVERY == 0:
            Ss = vn if Ss is None else (1-B_S)*Ss + B_S*vn
        m = mix + 0.5*Sm/(np.linalg.norm(Sm)+1e-9) + 0.3*Ss/(np.linalg.norm(Ss)+1e-9)
        mix = m/(np.linalg.norm(m)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        # 温度采样概率分布(观测用)
        p = torch.softmax(logits/0.85, -1)
        p_sorted = torch.sort(p, descending=True)[0]
        top1, top2 = p_sorted[0].item(), p_sorted[1].item()
        conflict = 1.0 - (top1 - top2)      # 0锁死, 1完全冲突
        H = -(p * torch.log(p + 1e-9)).sum().item()
        conflicts.append(conflict); entropies.append(H)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        # 自然死亡检测: top1 碾压且持续
        if len(out_toks) > 20 and top1 > 0.90:
            recent = out_toks[-8:]
            if len(set(recent)) == 1:
                dead = '冲突耗尽自然死亡(top1=%.2f 重复%s)' % (top1, tok.decode([recent[0]], skip_special_tokens=True)[:6])
                break
        if (i+1) % 300 == 0:
            print('    [%5d %.0fs] 冲突=%.3f 熵=%.2f' % (i+1, time.time()-t0, np.mean(conflicts[-100:]), np.mean(entropies[-100:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    # 分析生命阶段: 冲突曲线分段
    n = len(conflicts)
    segs = n // 4
    phases = []
    for ph in range(4):
        c = np.mean(conflicts[ph*segs:(ph+1)*segs]) if segs > 0 else 0
        phases.append(c)
    print('\n=== 生命弧线报告 ===', flush=True)
    print('寿命: %d token (%.0fs)' % (n, time.time()-t0), flush=True)
    print('死因: %s' % (dead or '到上限未死(还在冲突中)'), flush=True)
    print('四阶段冲突: 出生%.3f → 创造%.3f → 中段%.3f → 末期%.3f' % tuple(phases), flush=True)
    if dead and len(phases) == 4:
        trend = '自然衰老' if phases[-1] < phases[0] and phases[-1] < max(phases[:3]) else '非典型'
        print('弧线类型: %s' % trend, flush=True)
    L = len(text)
    for lab, seg in [('出生后', text[:120]), ('中段', text[L//2:L//2+120]), ('死亡前', text[-150:])]:
        print('\n[%s] %s' % (lab, seg.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
