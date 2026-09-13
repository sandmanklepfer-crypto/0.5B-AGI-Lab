#!/usr/bin/env python3
"""
V123 挣知识 × 文本通路 — 把"挣到的知识"真的送进上下文
v122 发现: 检索只注入方向, 文本从未进上下文 → 知识债没还上, 逻辑债没法测
本版改动(唯一): 检索命中槽 j 时, 把该卡文字插入生成上下文(【卡】…【/卡】, 每卡首次命中才插)
机制其余全同 v120/v122 (能量/检索费/回血/守门/节约/死亡全不动)
测:
  (a) 知识债: 自产文本能否逐字引用卡指纹(公式串) → 引用对/错
  (b) 逻辑债: 纯自产文本按序拼链能走几步(定义→欧拉乘积→延拓→函数方程→零点→临界线→1/2)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
N_POOL = 24
B_POOL = 0.08
B_FAST = 0.4
GATE_COS = 0.65
RETRIEVE_K = 2
E_INIT = 1.0
E_COST_TOKEN = 0.0004
E_COST_RETRIEVE = 0.004
E_GAIN_FIT = 0.0015
MAX_TOK = 3000
SEED = ('任务：从零到一推理黎曼猜想。我是推理者，我会从环境的知识池里挣到真步骤卡，'
        '卡片会直接出现在我的眼前，我要读卡、引用它、按正确顺序拼出完整推导链。'
        '第一步应该先讲清楚ζ(s)的定义：')
KNOWLEDGE = [
    '定义: ζ(s)=Σ_{n=1}^∞ 1/n^s, 只在Re(s)>1时绝对收敛',
    '欧拉乘积: ζ(s)=Π_p (1-p^{-s})^{-1}, p过素数, 把素数编码进ζ',
    '黎曼把这个函数解析延拓到整个复平面, 只在s=1有单极点',
    '函数方程: ζ(s)=2^s π^{s-1} sin(πs/2)Γ(1-s)ζ(1-s), 连接s与1-s',
    '零点: 平凡零点在负偶数-2,-4,-6…, 其余叫非平凡零点',
    '黎曼猜想: 所有非平凡零点的实部都等于1/2(临界线)',
    '延拓技巧: 用Γ函数积分表示ζ, 把发散级数换成收敛积分',
    '素数定理等价: 非平凡零点分布决定素数计数π(x)的误差',
    'ζ在临界带0<Re(s)<1内零点对称于实轴与临界线',
    'ζ(2)=π^2/6, ζ(4)=π^4/90, 偶数点由伯努利数给出',
    'Σ1/n在s=1处发散, 调和级数是最简单例子',
    '函数方程给出s与1-s之间的镜面对称',
    '若零点实部全为1/2, 素数分布误差项为O(x^{1/2}log x)',
    '欧拉1735年证ζ(2)=π^2/6, 黎曼1859年论文给出猜想',
    'ζ在Re(s)>1无零点: 由欧拉乘积直接可得',
    '欧拉乘积右边在Re(s)>1绝对收敛, 因为Σp^{-s}收敛',
    '解析延拓唯一性: 在Re(s)>1相等的解析函数全局唯一',
    'η(s)=(1-2^{1-s})ζ(s), 用交错级数可延拓到Re(s)>0',
    '临界线猜想是解析数论最著名难题, 至今未证明',
    '黎曼1859论文: 关于小于给定值的素数个数',
    'ξ(s)=s(s-1)/2·π^{-s/2}Γ(s/2)ζ(s)是整函数',
    'ξ满足ξ(s)=ξ(1-s), 整函数性质让零点研究变成乘积展开',
    '非平凡零点计数N(T)≈(T/2π)log(T/2πe), 黎曼-曼戈尔特公式',
    '素数定理: π(x)~x/log x, 1896年由哈达玛与普森证明',
]
# 每条卡的公式指纹(原样在卡文本中的子串, 用于逐字引用检测)
FP = [
    'Σ_{n=1}^∞ 1/n^s', '(1-p^{-s})^{-1}', 's=1有单极点',
    'sin(πs/2)Γ(1-s)', '-2,-4,-6', '1/2(临界线)',
    'Γ函数积分', 'π(x)的误差', '0<Re(s)<1',
    'π^2/6', '在s=1处发散', 's与1-s之间的镜面对称',
    'x^{1/2}log x', '1735', 'Re(s)>1无零点',
    'Σp^{-s}', '全局唯一', '1-2^{1-s}',
    '至今未证明', '给定值的素数个数', 'π^{-s/2}Γ(s/2)',
    'ξ(s)=ξ(1-s)', 'T/2π', 'x/log x',
]
CHAIN = ['定义', '欧拉', '乘积', '延拓', '函数方程', '零点', '临界线', '1/2']

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

    # 环境: 知识池 = 24条真知识向量
    pool, pool_meta = [], []
    for k in range(N_POOL):
        if k < len(KNOWLEDGE):
            idsk = tok(KNOWLEDGE[k], return_tensors='pt').input_ids.to('cuda')
            v = last_hidden(idsk)
            pool_meta.append(KNOWLEDGE[k])
        else:
            idsk = tok(SEED, return_tensors='pt').input_ids.to('cuda')
            v = last_hidden(idsk)
            pool_meta.append('(兜底)')
        vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())

    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    Sf = Ss = None
    E = E_INIT
    out_toks = []
    energy_hist, retrieve_hist = [], []
    slot_hits = np.zeros(N_POOL)
    card_inserted = [False]*N_POOL
    n_card = 0
    t0 = time.time()
    dead = None
    print('V123 挣知识×文本通路 | 检索命中→真卡文字进上下文 | E=%.2f' % E_INIT, flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        if Ss is None:
            Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS:
                Ss = (1-0.08)*Ss + 0.08*vn
        P = np.stack(pool)
        cosv = P @ vn
        if E > E_COST_RETRIEVE * 3:
            idx = np.argsort(-cosv)[:RETRIEVE_K]
            fit = float(cosv[idx].mean())
            E -= E_COST_RETRIEVE
            if fit > 0.3:
                E += E_GAIN_FIT * fit
            # ---- V123 唯一新增: 把挣到的卡文字放进眼前(首次命中才插) ----
            for j in idx:
                if not card_inserted[j] and j < len(KNOWLEDGE):
                    cids = tok('\n【卡%d】%s【/卡】\n' % (j, KNOWLEDGE[j]),
                               return_tensors='pt').input_ids.to('cuda')
                    ids = torch.cat([ids, cids], -1)
                    card_inserted[j] = True
                    n_card += 1
            # ---- 方向注入保留(v120原样) ----
            for j in idx:
                slot_hits[j] += 1
                pool[j] = pool[j]*(1-B_POOL) + B_POOL*vn
            wake_mix = sum(cosv[j]*pool[j] for j in idx)
            wake_mix = wake_mix/(np.linalg.norm(wake_mix)+1e-9)
            mix = mix + 0.4*wake_mix
            mix = mix/(np.linalg.norm(mix)+1e-9)
            did_retrieve = 1
        else:
            did_retrieve = 0
        E -= E_COST_TOKEN
        E = min(E, 1.5)
        energy_hist.append(E); retrieve_hist.append(did_retrieve)
        mix = mix/(np.linalg.norm(mix)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if E <= 0.0:
            dead = '能量耗尽自然死亡(E=0)'
            break
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.92 and len(set(out_toks[-8:])) == 1:
                dead = '冲突耗尽死亡(锁死重复)'
                break
        if (i+1) % 300 == 0:
            print('    [%5d %.0fs] E=%.3f 卡=%d/24 检索率=%.0f%%' % (
                i+1, time.time()-t0, E, n_card, 100*np.mean(retrieve_hist[-200:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V123 挣知识×文本通路报告 ===', flush=True)
    print('寿命: %d token | %s' % (len(out_toks), dead or '到上限'), flush=True)
    print('检索率: %.0f%% | 挣到卡: %d/24 张 | 末段能量%.3f' % (
        100*np.mean(retrieve_hist), n_card, E), flush=True)
    ne = len(energy_hist); seg = ne//4
    if seg > 0:
        print('能量四段: %.3f → %.3f → %.3f → %.3f' % tuple(np.mean(energy_hist[i*seg:(i+1)*seg]) for i in range(4)), flush=True)
    # ---- 知识债: 逐字引用检测(纯自产文本, 去空白) ----
    txt = re.sub(r'\s+', '', text)
    exact = []
    for k in range(N_POOL):
        if card_inserted[k] and k < len(FP):
            if re.sub(r'\s+', '', FP[k]) in txt:
                exact.append(k)
    print('\n[知识债] 逐字引用: 读卡%d张, 自产文本逐字引用%d张卡公式: %s' % (
        n_card, len(exact), [k for k in exact] or '无'), flush=True)
    for k in range(N_POOL):
        if card_inserted[k]:
            hit = k in exact
            print('  卡%2d %s | 逐字引用%s' % (k, '✓' if hit else '✗', KNOWLEDGE[k][:30]), flush=True)
    # 概念词被"提到"统计(提到但没引用对 = 半懂)
    for cw in ['函数方程','欧拉','延拓','零点','黎曼猜想','临界线','素数定理','η','ξ','Γ','π^2/6','1/n^s','p^{-s}']:
        cnt = text.count(cw)
        if cnt: print('  概念词 "%s" 出现 x%d' % (cw, cnt), flush=True)
    # ---- 逻辑债: 纯自产文本按序拼链 ----
    pos, steps = 0, 0
    for step in CHAIN:
        p2 = text.find(step, pos)
        if p2 < 0:
            break
        steps += 1; pos = p2 + len(step)
    print('\n[逻辑债] 正确顺序链 %d/%d 步: %s' % (steps, len(CHAIN), ' → '.join(CHAIN[:steps]) or '一步没走'), flush=True)
    reps_all = len(re.findall(r'(.{12,})\\1', text))
    print('全文复读x%d' % reps_all, flush=True)
    L = len(text)
    for lab, s in [('出生', text[:130]), ('中段', text[L//2:L//2+130]), ('死前' if dead else '结尾', text[-170:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
