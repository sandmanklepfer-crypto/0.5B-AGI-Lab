#!/usr/bin/env python3
# V116 永久生命 — 慢S+写活delta 落盘, 跨会话续命
# 会话1: 生成N token, 结束时存 慢S/快S/写活delta/history尾部 → life_state.pt
# 会话2: 启动先找存档 → 有则加载(续写自己的人生), 无则用初始种子(出生)
import torch, numpy as np, time, re, os, json
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1/life_state.pt'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.70
WRITE_EVERY = 40
WRITE_SCALE = 0.015
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋','屋','山','院','门','灰','脚印','爷爷','堂屋','墙','窗','屋后','井','楼梯','灯']

def gen_session(tokens, tag, load_state=True):
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 1.0, 'v': None, 'u': None}
    sd = model.state_dict()
    WN = 'model.layers.%d.mlp.down_proj.weight' % LAYER
    W0 = sd[WN].float().cpu().numpy().copy()

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

    # ---- 出生 or 续命 ----
    Sf = Ss = None
    Wcur = W0.copy()
    history_tail = ''
    if load_state and os.path.exists(SAVE):
        stt = torch.load(SAVE, map_location='cpu', weights_only=False)
        Ss = stt['Ss']; Wcur = stt['W_delta'] + W0
        history_tail = stt['history_tail']
        print('[%s] 续命: 加载人生存档 (慢S来自%d token前, 权重delta=%.3f)' % (
            tag, stt['tokens'], np.linalg.norm(stt['W_delta'])), flush=True)
    else:
        print('[%s] 出生: 无存档, 用初始种子' % tag, flush=True)
    # 应用写活delta
    if np.linalg.norm(Wcur - W0) > 0:
        sd2 = dict(sd); sd2[WN] = torch.tensor(Wcur).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)

    # 起点: 续命用历史尾部(世界记忆), 出生用种子
    start_text = (history_tail[-300:] if history_tail else SEED)
    ids = tok(start_text, return_tensors='pt').input_ids.to('cuda')
    # 用起点初始化慢S (续命时它记得世界)
    v0 = last_hidden(ids)
    Ss = v0/np.linalg.norm(v0) if Ss is None else Ss

    def clean_write(direction):
        nonlocal Wcur
        d = direction.astype(np.float64); d = d/np.linalg.norm(d)
        u = np.random.RandomState(int(time.time()*1000)%99999).randn(4864); u = u/np.linalg.norm(u)
        P = np.outer(d, u); P = P/np.linalg.norm(P)*(np.linalg.norm(W0)*WRITE_SCALE)
        Wcur = Wcur + P
        sd2 = dict(sd); sd2[WN] = torch.tensor(Wcur).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)

    out_toks = []
    crashed = None
    for i in range(tokens):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        if Ss is None: Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS: Ss = (1-B_S)*Ss + B_S*vn
            else:
                if len([1]) >= 1:  # 候选简化
                    pass
        if i>0 and i % WRITE_EVERY == 0 and Ss is not None: clean_write(Ss)
        mm = mix + 0.5*Ss/(np.linalg.norm(Ss)+1e-9); mix = mm/(np.linalg.norm(mm)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad(): logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.85,-1),1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if len(out_toks)>=6 and len(set(out_toks[-6:]))==1: crashed='乱码'; break
    text = tok.decode(out_toks, skip_special_tokens=True)
    # ---- 落盘: 保存人生 ----
    torch.save({'Ss': Ss, 'W_delta': torch.tensor(Wcur - W0), 'tokens': len(out_toks),
                'history_tail': start_text + text}, SAVE)
    print('[%s] 生成%d token | %s | 人生已存档' % (tag, len(out_toks), crashed or 'OK'), flush=True)
    print('内容尾150字: %s' % text[-150:].replace('\n',' '), flush=True)
    hook.remove()

if __name__ == '__main__':
    import sys
    # 会话1: 出生, 活800 token
    print('========== 生命实验: 会话1 (出生) ==========', flush=True)
    gen_session(800, '会话1', load_state=False)
    print('\n========== 生命实验: 会话2 (续命) ==========', flush=True)
    gen_session(800, '会话2', load_state=True)
    print('\n[done] 验证: 会话2是否还记得老屋世界(不是重新出生)', flush=True)
