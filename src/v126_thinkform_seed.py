#!/usr/bin/env python3
"""
V126 挣知识生命体 × 思考形态种子 — 出生种子内嵌"转述+自检"示范
V125 发现: 0.5B 有 paraphrase 能力, 缺的是"形态触发" → few-shot 示范一给就转述
本版把思考形态种进挣知识生命体的出生种子(不改任何权重/机制, 不加if):
  - 转述示范 x2 (卡→自己的话, 主题贴近但不与任务卡重叠 → 不能抄, 必须真转述)
  - 自检示范 x1 (讲错→对照卡→改口)
  - 然后 "现在轮到我自己" → 8张中文黎曼事实卡开场摆在 context
判定(人工+统计): 生成段里自发出现 转述形态(也就是说/我的转述/换个说法…)
  + 自检形态(不对/卡上说的是/再读一遍…) → 即"边活边想"是否涌现
机制(能量/检索/守门/自然死) 与 v120 全同 → 行为层第六次对照
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
# 8张中文黎曼事实卡(概念级, 0.5B词表能说)
CARDS = [
    '黎曼猜想说的是：ζ函数所有的非平凡零点，它们的实部都等于二分之一。',
    '这个猜想从1859年被提出到现在，还没有任何人能证明它。',
    'ζ函数在s等于2的时候，它的值等于圆周率的平方除以6。',
    '欧拉发现ζ函数能写成所有素数的一种乘积形式，这叫欧拉乘积。',
    'ζ函数在s等于1的地方是发散的，一加二分之一加三分之一一直加下去会变成无穷大。',
    '黎曼把ζ函数从只能在实部大于1时使用，扩展到了整个复平面，这叫解析延拓。',
    '素数定理说的是：小于x的素数个数，大约等于x除以x的自然对数。',
    'ζ函数在负偶数那些点上的值都等于零。',
]
# 出生种子: 内嵌思考形态示范(主题贴近但不与任务卡重叠 → 抄不了, 只能学形态)
SEED = (
    '我看见旁边有位老师正在教一个学生转述卡片，我偷学了他的方法。'
    '老师给了一张卡，卡上写：卡A说小于x的素数个数大约等于x除以x的自然对数。'
    '学生转述：也就是说，数越大的地方素数越稀，比例大概是自然对数的倒数。老师点头。'
    '老师又给一张卡：卡B说ζ函数在负偶数那些点上等于零。'
    '学生转述：换句话说，负的偶数全都是这个函数取零的地方。老师点头。'
    '学生讲错了一次，说"素数是有穷的"，老师让他再看卡，他改口：不对，卡上写的是无穷多，'
    '我记反了，应该是无穷多个素数。老师点头。'
    '现在我面前也摆着八张卡，我学着他的方法，先用自己的话转述每一张，讲错了就对照卡改口。'
    '好，现在轮到我讲了：'
)

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

    # 池 = 8卡 × 3 (挣知识方向与卡一致)
    pool, pool_meta = [], []
    for k in range(N_POOL):
        c = CARDS[k % len(CARDS)]
        idsk = tok(c, return_tensors='pt').input_ids.to('cuda')
        v = last_hidden(idsk)
        pool_meta.append(c)
        vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())

    ctx = SEED + '\n' + '\n'.join('【卡%d】%s' % (i, c) for i, c in enumerate(CARDS))
    ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
    Sf = Ss = None
    E = E_INIT
    out_toks = []
    energy_hist, retrieve_hist = [], []
    slot_hits = np.zeros(N_POOL)
    t0 = time.time()
    dead = None
    print('V126 挣知识×思考形态种子 | 示范内嵌(转述x2+自检x1)+8卡 | E=%.2f | 机制零改动' % E_INIT, flush=True)
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
        if (i+1) % 300 == 0:
            print('    [%5d %.0fs] E=%.3f 检索率=%.0f%%' % (
                i+1, time.time()-t0, E, 100*np.mean(retrieve_hist[-200:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V126 挣知识×思考形态种子报告 ===', flush=True)
    print('寿命: %d token | %s' % (len(out_toks), dead or '到上限'), flush=True)
    print('检索率: %.0f%% | 末段能量%.3f' % (100*np.mean(retrieve_hist), E), flush=True)
    ne = len(energy_hist); seg = ne//4
    if seg > 0:
        print('能量四段: %.3f → %.3f → %.3f → %.3f' % tuple(np.mean(energy_hist[i*seg:(i+1)*seg]) for i in range(4)), flush=True)
    # 生成段思考形态统计 (生成段不含示范 → 出现=自发)
    para_mark = ['也就是说', '我的转述', '换个说法', '换句话说', '意思是', '可以理解为', '其实就是', '来讲就是']
    check_mark = ['不对', '错了', '卡上说的是', '卡上写', '我记', '再看', '对照', '说错', '讲错', '改口', '应该是']
    np_ = sum(text.count(m) for m in para_mark)
    nc = sum(text.count(m) for m in check_mark)
    print('\n[思考形态] 转述标记出现x%d %s' % (np_, para_mark), flush=True)
    print('           自检标记出现x%d %s' % (nc, check_mark), flush=True)
    reps_all = len(re.findall(r'(.{12,})\\1', text))
    print('全文复读x%d' % reps_all, flush=True)
    print('\n[生成全文] %s' % text.replace('\n', ' '), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
