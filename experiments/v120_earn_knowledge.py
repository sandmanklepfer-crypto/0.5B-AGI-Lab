#!/usr/bin/env python3
"""
V120 挣知识架构 — 知识=环境(需主动获取), 推理=核心(带能量), 获取有代价
钱的比喻实现:
  知识池(24) = 环境里分散的"钱" (虚拟, 外部)
  推理核心(权重antiheb+慢S) = "人" (在权重里, 主体)
  检索 = 主动"挣钱": 每步向最相关池发 query, 但消耗能量 E
  能量 = 有限, 每token耗一点, 检索花更多
  节约 = 能量低时少检索(只跟自我世界走), 能量高时才敢探索(乱花会死)
  死亡 = 能量耗尽(冲突/选择耗尽) → 自然死
验证: 是否能自然形成"节约-检索-选择"行为, 而非精神分裂乱跳
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
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋','屋','山','院','门','灰','脚印','爷爷','堂屋','墙','窗','屋后','井','楼梯','灯']

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

    # 环境: 知识池初始化(分散)
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
    energy_hist, retrieve_hist = [], []
    t0 = time.time()
    dead = None
    print('V120 挣知识 | 能量E=%.2f 检索耗%.4f/次 回血%.4f | 知识=环境, 推理=主体' % (
        E_INIT, E_COST_RETRIEVE, E_GAIN_FIT), flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        # 快S
        Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        # 慢S守门(自我世界, 防污染): cos门槛
        if Ss is None:
            Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS:
                Ss = (1-0.08)*Ss + 0.08*vn
        # 检索决策: 能量够才检索(节约), 能量高多检索(探索)
        P = np.stack(pool)
        cosv = P @ vn
        if E > E_COST_RETRIEVE * 3:      # 有能量才敢花钱
            idx = np.argsort(-cosv)[:RETRIEVE_K]
            fit = float(cosv[idx].mean())
            E -= E_COST_RETRIEVE
            if fit > 0.3:
                E += E_GAIN_FIT * fit    # 挣到钱回血
            for j in idx:
                pool[j] = pool[j]*(1-B_POOL) + B_POOL*vn
            wake_mix = sum(cosv[j]*pool[j] for j in idx)
            wake_mix = wake_mix/(np.linalg.norm(wake_mix)+1e-9)
            mix = mix + 0.4*wake_mix
            mix = mix/(np.linalg.norm(mix)+1e-9)
            did_retrieve = 1
        else:
            did_retrieve = 0            # 能量低 → 节约, 只跟自我走
        E -= E_COST_TOKEN
        E = min(E, 1.5)                  # 能量上限(不能无限囤)
        energy_hist.append(E); retrieve_hist.append(did_retrieve)
        mix = mix/(np.linalg.norm(mix)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        # 自然死亡: 能量耗尽
        if E <= 0.0:
            dead = '能量耗尽自然死亡(E=0)'
            break
        # 冲突死亡(锁死)
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.92 and len(set(out_toks[-8:])) == 1:
                dead = '冲突耗尽死亡(锁死重复)'
                break
        if (i+1) % 400 == 0:
            print('    [%5d %.0fs] E=%.3f 检索率=%.0f%%' % (
                i+1, time.time()-t0, E, 100*np.mean(retrieve_hist[-200:])), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V120 挣知识报告 ===', flush=True)
    print('寿命: %d token | %s' % (len(out_toks), dead or '到上限'), flush=True)
    print('检索率(总): %.0f%% | 末段能量%.3f' % (100*np.mean(retrieve_hist), E), flush=True)
    # 能量曲线四段
    ne = len(energy_hist); seg = ne//4
    if seg > 0:
        print('能量四段: %.3f → %.3f → %.3f → %.3f' % tuple(np.mean(energy_hist[i*seg:(i+1)*seg]) for i in range(4)), flush=True)
    reps_all = len(re.findall(r'(.{12,})\1', text))
    print('全文复读x%d' % reps_all, flush=True)
    L = len(text)
    for lab, s in [('出生', text[:110]), ('中段', text[L//2:L//2+110]), ('死前' if dead else '结尾', text[-150:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
