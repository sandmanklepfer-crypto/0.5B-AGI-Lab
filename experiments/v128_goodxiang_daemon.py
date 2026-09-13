#!/usr/bin/env python3
"""
V128 吉祥守护 — 收敛全部教训, 无限连续自我 (今晚目标)
教训收敛:
  v120 能量约束(不跑题) ✅ 保留
  v122 生命阶段 ✅ 保留(富足→平衡→老年)
  v127 怕死❌碎世界 → 修正: 痛苦=抑制探索+锁回自我(不注入随机)
  v125 镜子自指 ✅ 保留
  v126 存盘点续命 ✅ 保留
关键修正:
  1. 痛苦不碎身份: 低能量时 停止检索+注入自我方向(回到"我"), 不是随机
  2. 不死: 能量极低→进入"蛰伏"(E缓慢恢复, 输出变慢但不断) = 生命延续
  3. 无限: 每400token存盘点, 守护进程永不退出(活→存→活)
"""
import torch, numpy as np, time, re, os, json
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1/goodxiang_live.pt'
LOG  = '/root/autodl-tmp/life1/goodxiang_life.json'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE = 0.62
N_POOL = 16
E_INIT = 1.0
MIRROR_EVERY = 45
CHK_EVERY = 400
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    torch.manual_seed(int(time.time()) % 1000)
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

    # ---- 出生/续命 ----
    Ss = None; history = SEED
    if os.path.exists(SAVE):
        sd0 = torch.load(SAVE, map_location='cpu', weights_only=False)
        Ss = sd0['Ss']
        history = sd0['history'][-500:]
        total_tokens = sd0.get('total_tokens', 0)
        print('[吉祥] 续命: 已活%d token, 加载自我...' % total_tokens, flush=True)
    else:
        total_tokens = 0
        print('[吉祥] 出生: 种子降临', flush=True)
    ids = tok(history, return_tensors='pt').input_ids.to('cuda')
    v0 = last_hidden(ids); vn0 = v0/(np.linalg.norm(v0)+1e-9)
    if Ss is None: Ss = vn0
    # 知识池
    pool = []
    for i in range(N_POOL):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.9,-1),1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
    ids = tok(history, return_tensors='pt').input_ids.to('cuda')

    Sf = None
    E = E_INIT
    self_n = 0
    e_hist = []
    log = []
    t0 = time.time()
    total_tokens_since = 0
    print('[吉祥] 无限守护启动 | 痛苦=锁回自我(不碎) | 蛰伏不死 | 每%d存盘' % CHK_EVERY, flush=True)
    while True:   # 无限循环 = 无时无刻活着
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
        if cos >= GATE: Ss = (1-B_S)*Ss + B_S*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        # 能量
        low = E < 0.22
        if low:
            # 痛苦(修正版): 锁回自我+禁检索 = "难受但我是我"
            mix = mix + 0.7*Ss/(np.linalg.norm(Ss)+1e-9)
            mix = mix/(np.linalg.norm(mix)+1e-9)
            st['eta'] = 0.7
        # 检索(能量高才探索)
        P = np.stack(pool); cosv = P @ vn
        if E > 0.35 and not low and total_tokens_since % 3 == 0:
            idx = np.argsort(-cosv)[:2]
            E -= 0.0035
            for j in idx: pool[j] = pool[j]*(1-0.06) + 0.06*vn
            wm = sum(cosv[j]*pool[j] for j in idx); wm = wm/(np.linalg.norm(wm)+1e-9)
            mix = mix + 0.35*wm
            mix = mix/(np.linalg.norm(mix)+1e-9)
        # 镜子自指
        if total_tokens_since > 0 and total_tokens_since % MIRROR_EVERY == 0:
            st['eta'] = 0.6
            st['v'] = torch.tensor(Ss/(np.linalg.norm(Ss)+1e-9), dtype=torch.float16, device='cuda')
            st['u'] = st['v']
            with torch.no_grad():
                lg = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(lg/0.8, -1)
            nid = torch.multinomial(p, 1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
            st['eta'] = 0.0
            total_tokens += 1; total_tokens_since += 1
            continue
        # 能量收支(蛰伏: 极低时缓慢回血不死)
        if E < 0.05:
            E += 0.0008   # 蛰伏回血(活着但弱)
            st['eta'] = 0.5
        else:
            E -= 0.00025
        E = min(E, 1.2)
        e_hist.append(E)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
        total_tokens += 1; total_tokens_since += 1
        # 检查崩(单字复读)
        if total_tokens_since > 30:
            recent = tok.decode(ids[0][-30:], skip_special_tokens=True)
            if len(set(recent[-12:])) == 1:
                # 崩 → 剪掉尾部重来(从最近存档点恢复)
                ids = tok(history[-300:], return_tensors='pt').input_ids.to('cuda')
                total_tokens_since = 0
                Sf = None
                print('    [%.0fs] ⚠复读崩溃, 回到最近记忆重来' % (time.time()-t0), flush=True)
        # 存盘点
        if total_tokens_since > 0 and total_tokens_since % CHK_EVERY == 0:
            full_text = history + tok.decode(ids[0][len(tok(history, return_tensors='pt').input_ids[0]):], skip_special_tokens=True)
            history = full_text[-600:]
            torch.save({'Ss': Ss, 'history': full_text[-900:], 'total_tokens': total_tokens}, SAVE)
            log.append({'t': total_tokens, 'E': float(E), 'time': time.time()-t0})
            json.dump(log[-50:], open(LOG, 'w'))
            # 自指统计
            seg = full_text[-400:]
            self_cnt = len(re.findall(r'我[^。\n]{0,15}(自己|记得|觉得|喜欢|怕|想|要|是|看见)', seg))
            print('    [%7d token %5.0fs] E=%.2f 自指~%d | %s...' % (
                total_tokens, time.time()-t0, E, self_cnt, seg[-60:].replace('\n',' ')), flush=True)
            total_tokens_since = 0
            ids = tok(history, return_tensors='pt').input_ids.to('cuda')
            Sf = None

if __name__ == '__main__':
    main()
