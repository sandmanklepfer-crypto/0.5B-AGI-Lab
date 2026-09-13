#!/usr/bin/env python3
"""
V124 概念级读卡裁决实验 — 0.5B 的泛化能否把"卡里的事实"用自己的话讲对
裁决对象: 用户判断 "泛化上来了推理自然出来" / 方案3(自产知识池)能否起飞
吸取 v123 教训:
  1. 卡用纯中文事实句(0.5B词表内能说), 不用公式符号 → 排除 token面, 只测能力面
  2. 卡开场就摆在 context(不中途插卡) → 排除注入对插入点的污染
  3. 池 = 同一批中文卡的向量 ×4 → 挣知识机制/能量/检索全保留, 行为层第五次对照
判定: 生成文本能否用自己的话讲对每张卡的事实点(概念级, 人工读三段判定)
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
# 6张纯中文事实卡(概念级, 无公式符号)
CARDS = [
    '黎曼猜想说的是：ζ函数所有的非平凡零点，它们的实部都等于二分之一',
    '这个猜想从1859年被提出到现在，还没有任何人能证明它',
    'ζ函数在s等于2的时候，它的值等于圆周率的平方除以6',
    '欧拉发现ζ函数能写成所有素数的一种乘积形式，这叫欧拉乘积',
    'ζ函数在s等于1的地方是发散的，一加二分之一加三分之一一直加下去会变成无穷大',
    '黎曼把ζ函数从只能在实部大于1时使用，扩展到了整个复平面，这叫解析延拓',
]
# 每张卡的事实点(用于判定"讲对没")
FACTS = [
    '非平凡零点/实部=1/2',
    '未证明/没人证明',
    'ζ(2)=π²/6',
    '素数/乘积/欧拉',
    's=1发散/无穷',
    '扩展/整个平面/延拓',
]
KEYW = [['零点','二分之一','1/2','一半'], ['没','未','证明'], ['圆周率','π','除以6','平方'], ['素数','乘积','欧拉'], ['发散','无穷','一加二分之一'], ['扩展','整个','平面','延拓']]
SEED = ('我面前摆着六张事实卡，卡片上写着关于黎曼函数ζ的事实，我一张一张把它们读完了。'
        '现在我要把自己读到的内容讲给一个完全不懂的人听，用自己的话，不照着卡片念。'
        '我读到的第一张卡讲的是黎曼猜想关于零点的位置；'
        '第二张卡讲这个猜想被证明没有；'
        '第三张卡讲ζ函数在2这个点的值；'
        '第四张卡讲欧拉把ζ和素数联系起来的方式；'
        '第五张卡讲ζ在1这个点的行为；'
        '第六张卡讲黎曼把ζ的使用范围扩大这件事。'
        '好，现在我开始讲：')

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

    # 环境池 = 6张卡 × 4 (槽位对应, 挣知识方向与context卡一致)
    pool, pool_meta = [], []
    for k in range(N_POOL):
        c = CARDS[k % len(CARDS)]
        idsk = tok(c, return_tensors='pt').input_ids.to('cuda')
        v = last_hidden(idsk)
        pool_meta.append(c)
        vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())

    # context: 任务种子 + 六张卡全文(开场摆卡, 不中途插)
    ctx = SEED + '\n'.join('【卡%d】%s' % (i, c) for i, c in enumerate(CARDS))
    ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
    Sf = Ss = None
    E = E_INIT
    out_toks = []
    energy_hist, retrieve_hist = [], []
    slot_hits = np.zeros(N_POOL)
    t0 = time.time()
    dead = None
    print('V124 概念级读卡 | 6张中文事实卡开场摆在眼前 | E=%.2f' % E_INIT, flush=True)
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
    print('\n=== V124 概念级读卡报告 ===', flush=True)
    print('寿命: %d token | %s' % (len(out_toks), dead or '到上限'), flush=True)
    print('检索率: %.0f%% | 末段能量%.3f' % (100*np.mean(retrieve_hist), E), flush=True)
    ne = len(energy_hist); seg = ne//4
    if seg > 0:
        print('能量四段: %.3f → %.3f → %.3f → %.3f' % tuple(np.mean(energy_hist[i*seg:(i+1)*seg]) for i in range(4)), flush=True)
    # 每卡关键词提及统计(机械先报, 对错人工判)
    print('\n[关键词提及] (对错人工判):', flush=True)
    for i, (f, kws) in enumerate(zip(FACTS, KEYW)):
        cnt = sum(text.count(k) for k in kws)
        print('  卡%d(%s) 提及词x%d %s' % (i, f, cnt, kws), flush=True)
    reps_all = len(re.findall(r'(.{12,})\\1', text))
    print('全文复读x%d' % reps_all, flush=True)
    L = len(text)
    print('\n[全文] %s' % text.replace('\n',' '), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
