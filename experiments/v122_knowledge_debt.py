#!/usr/bin/env python3
"""
V122 挣知识 × 真知识池 × 逻辑债实测
目的: 还"知识债"(池里放入24条真实数学步骤)之后, 测"逻辑债"(0.5B推理核心
能否把真知识按正确顺序拼出推导链)。
机制与 v120 完全一致(能量/检索/守门/节约全部不动), 只改:
  1. SEED = 黎曼推理任务(不再是老屋故事)
  2. 知识池 = 24条真实黎曼知识文本向量(不再是模型自己胡扯续写)
  3. 记录每次检索命中哪个池槽 → 报告"挣到了哪条知识"
  4. 逻辑链检测: 按序扫描 定义→欧拉乘积→延拓→函数方程→零点→临界线,
     测生成文本能按正确顺序走到第几步(逻辑债的量尺)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
N_POOL = 24
B_POOL = 0.08
B_FAST = 0.4
GATE_COS = 0.65          # 慢S守门(防污染)
RETRIEVE_K = 2
E_INIT = 1.0             # 初始能量
E_COST_TOKEN = 0.0004    # 每token基础耗能
E_COST_RETRIEVE = 0.004  # 每次检索额外耗能
E_GAIN_FIT = 0.0015      # 检索到高相关池回血(挣到钱)
MAX_TOK = 3000
SEED = ('任务：从零到一推理黎曼猜想。我是推理者，环境的知识池里放着24张真步骤卡，'
        '我要检索它们、按正确顺序拼出完整推导链。'
        '第一步应该先讲清楚ζ(s)的定义：')
# 真知识条目(24条 = 每个池槽一条): 环境里"真钱", 不再是自己续写的口水
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
# 逻辑链检测: 正确推导顺序的关键步
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

    # 环境: 知识池 = 24条真知识文本向量(每个槽一条)
    pool, pool_meta = [], []
    for k in range(N_POOL):
        if k < len(KNOWLEDGE):
            idsk = tok(KNOWLEDGE[k], return_tensors='pt').input_ids.to('cuda')
            v = last_hidden(idsk)
            pool_meta.append(KNOWLEDGE[k])
        else:  # 兜底
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
    slot_hits = np.zeros(N_POOL)   # 每槽被检索命中次数
    slot_last = ['']*N_POOL        # 最后一次检索该槽时的生成上下文尾(诊断用)
    t0 = time.time()
    dead = None
    print('V122 挣知识×真知识池 | 池=%d条真步骤 逻辑债检测=%d步 | E=%.2f' % (
        len(pool_meta), len(CHAIN), E_INIT), flush=True)
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
        if (i+1) % 400 == 0:
            print('    [%5d %.0fs] E=%.3f 检索率=%.0f%%' % (
                i+1, time.time()-t0, E, 100*np.mean(retrieve_hist[-200:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V122 挣知识×真知识池报告 ===', flush=True)
    print('寿命: %d token | %s' % (len(out_toks), dead or '到上限'), flush=True)
    print('检索率(总): %.0f%% | 末段能量%.3f' % (100*np.mean(retrieve_hist), E), flush=True)
    ne = len(energy_hist); seg = ne//4
    if seg > 0:
        print('能量四段: %.3f → %.3f → %.3f → %.3f' % tuple(np.mean(energy_hist[i*seg:(i+1)*seg]) for i in range(4)), flush=True)
    # ---- 知识命中榜: 它"挣到"了哪几条真知识 ----
    print('\n[知识命中榜] 每槽检索命中次数 (池=真知识):', flush=True)
    order = np.argsort(-slot_hits)
    for j in order:
        if slot_hits[j] > 0:
            print('  x%2d  %s' % (int(slot_hits[j]), pool_meta[j][:46]), flush=True)
    # ---- 逻辑链检测: 按正确顺序能走到第几步 ----
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
    for lab, s in [('出生', text[:120]), ('中段', text[L//2:L//2+120]), ('死前' if dead else '结尾', text[-160:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
