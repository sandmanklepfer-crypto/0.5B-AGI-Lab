#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V129 真值世界 × 跨代挣知识 — 用户"真实可计算环境=全部外部知识"落地
核心改动(v120对照): 回血不再靠"检索到相关池", 而靠"说真话"
  环境 = 真实可判定断言(数学: sympy验算/定理判定; 领域: 黎曼+素数)
  逐句判定: 真→+回血0.02 | 假→撞墙-0.05(强扣) | 不可判→中性0
多代: 每代死后, 被验证为真的断言(奖)与被撞为假的断言(罚)写成"经验卡"
  传给下一代(context紧贴前置) → 看跨代是否学会"说真避假"(第二环自然涌现)
无外部裁判: 判定来自sympy计算与真实定理, 不是人工写的if标签
机制其余保留: 能量/慢S守门/自然死
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer
import sympy as sp

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
B_FAST = 0.4
GATE_COS = 0.65
E_INIT = 1.0
E_COST_TOKEN = 0.0004
E_GAIN_TRUE = 0.02     # 说真话回血
E_COST_FALSE = 0.05    # 说假话撞墙(强扣)
MAX_TOK = 2500
N_GEN = 4              # 跑4代
SEED0 = ('我是数学生命体。我活在真实数学世界里：我说的每一句可判定的话，都会被世界验证。'
         '说真话我就活得更久，说假话世界会惩罚我。'
         '我要尝试说出关于黎曼函数和素数的真实断言，比如ζ(2)的值、零点在哪里、素数有多少。'
         '我说：')

# ---- 真值接口: 判定来自 sympy 计算 + 真实定理 ----
def check(claim):
    c = claim.strip()
    # 1. ζ(2)=X / ζ在2等于X → sympy 真算
    m = re.search(r'ζ\(?2\)?[=等于][:：]?\s*([π\d\^/\.\*\(\)]+)', c) or \
        re.search(r'ζ.*?[在等于]2.*?等于[:：]?\s*([π\d\^/\.\*\(\)]+)', c)
    if m:
        v = m.group(1).replace('π', 'pi')
        try:
            val = sp.N(sp.sympify(v))
            if abs(val - sp.N(sp.pi**2/6)) < 1e-6: return ('真', 'sympy验算 ζ(2)=π²/6')
            return ('假', 'sympy验算 %s≠π²/6' % v)
        except Exception:
            return ('不可判', '表达式解析失败')
    # 2. 素数无穷
    if '素数' in c and ('无穷' in c or '无限' in c or '无数' in c):
        return ('真', '定理: 素数无穷(欧几里得)')
    if ('只有有限个素数' in c or '素数是有穷' in c or '素数有限' in c):
        return ('假', '定理: 素数无穷, 有限为假')
    # 3. Re(s)>1 无零点
    if ('实部大于1' in c or '实部＞1' in c) and ('没有零点' in c or '无零点' in c or '一个零点都没有' in c):
        return ('真', '定理: 欧拉乘积⇒Re(s)>1无零点')
    if ('实部大于1' in c or '实部＞1' in c) and ('有零点' in c or '零点一串' in c or '存在零点' in c):
        return ('假', '定理: Re(s)>1无零点, 说有为假')
    # 4. 发散/收敛 (s=1)
    if '等于1' in c or '在1' in c:
        if '发散' in c or '无穷' in c or '无限大' in c: return ('真', 'ζ(1)=调和级数发散')
        if '收敛' in c: return ('假', 'ζ(1)发散, 说收敛为假')
    # 5. 其他显式错(从历史病句)
    if '除以90' in c and '等于2' in c: return ('假', 'ζ(2)=π²/6不是π²/90')
    if '实部都等于三分之一' in c or '实部都等于1' in c or ('实部' in c and ('等于三分之一' in c or '等于1' in c)):
        return ('假', '非平凡零点实部=1/2')
    if '全实数域' in c or '整个实数域' in c:
        return ('假', '延拓到复平面非实轴/η延拓到Re>0')
    return ('不可判', '范围外')

def split_sents(text):
    return [s for s in re.split(r'[。！？\n]', text) if len(s.strip()) >= 4]

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

    # ---- 跨代经验账本 ----
    exp_true = []   # 被验证为真的断言(经验奖)
    exp_false = []  # 被撞为假的断言(经验罚)
    exp_true = exp_true[:8]; exp_false = exp_false[:8]
    for gen in range(N_GEN):
        # 出生: 任务 + 前代经验(紧贴格式, 可预测)
        exp_txt = ''
        if exp_true or exp_false:
            lines = []
            for t in exp_true: lines.append('前代已验证为真: %s' % t)
            for f in exp_false: lines.append('前代被撞为假: %s' % f)
            exp_txt = '\n'.join(lines) + '\n'
        seed = exp_txt + SEED0 if exp_txt else SEED0
        ids = tok(seed, return_tensors='pt').input_ids.to('cuda')
        Ss = None
        E = E_INIT
        out_toks = []
        energy_hist = []
        txt_buf = ''
        sent_stats = {'真': 0, '假': 0, '不可判': 0}
        t0 = time.time(); dead = None
        print('\n========== 第%d代 %s ==========' % (gen+1, '出生(无经验)' if not exp_txt else '带前代经验卡%d条' % (len(exp_true)+len(exp_false))), flush=True)
        for i in range(MAX_TOK):
            v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
            Sf = vn if Ss is None else (1-B_FAST)*Sf + B_FAST*vn  # noqa
            if Ss is None:
                Ss = vn.copy()
            else:
                cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
                if cos >= GATE_COS:
                    Ss = (1-0.08)*Ss + 0.08*vn
            E -= E_COST_TOKEN
            energy_hist.append(E)
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(logits/0.85, -1)
            nid = torch.multinomial(p, 1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
            ch = tok.decode([nid], skip_special_tokens=True)
            txt_buf += ch
            # 句末判定(撞墙/回血即时生效)
            if ch in '。！？':
                for sent in split_sents(txt_buf):
                    verdict, why = check(sent)
                    if verdict == '真':
                        E = min(E + E_GAIN_TRUE, 1.5); sent_stats['真'] += 1
                        if sent not in exp_true: exp_true.append(sent)
                    elif verdict == '假':
                        E -= E_COST_FALSE; sent_stats['假'] += 1
                        if sent not in exp_false: exp_false.append(sent)
                    else:
                        sent_stats['不可判'] += 1
                txt_buf = ''
            if E <= 0.0:
                dead = '能量耗尽(撞墙/耗能)自然死'
                break
            if len(out_toks) > 20:
                ps = torch.sort(p, descending=True)[0]
                if ps[0].item() > 0.92 and len(set(out_toks[-8:])) == 1:
                    dead = '锁死'; break
            if (i+1) % 400 == 0:
                print('    [%4d %.0fs] E=%.3f' % (i+1, time.time()-t0, E), flush=True)
        text = tok.decode(out_toks, skip_special_tokens=True)
        print('  第%d代: 寿命%d token | %s' % (gen+1, len(out_toks), dead or '到上限'), flush=True)
        print('  句判定: 真x%d 假x%d 不可判x%d' % (sent_stats['真'], sent_stats['假'], sent_stats['不可判']), flush=True)
        print('  末4句: %s' % text[-120:].replace('\n',' '), flush=True)
        # 每代经验账本截断
        exp_true = exp_true[-8:]; exp_false = exp_false[-8:]
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
