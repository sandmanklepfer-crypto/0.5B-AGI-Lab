#!/usr/bin/env python3
# V115 长跑测试: 三层自读+双层污染韧性(C模式) 撑3000 token
# C模式=慢S门槛 + 写活巩固 + 干扰@1500, 看世界保持能否到3000
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.70
WRITE_EVERY = 40
WRITE_SCALE = 0.015
MAX_TOK = 3000
DISTRACT_AT = 1500
DISTRACT = '今天股市大涨，投资者加仓，证监会发布新规，市场情绪高涨，科技股领涨。'
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋','屋','山','院','门','灰','脚印','爷爷','堂屋','墙','窗','屋后','井','楼梯','灯']

def main():
    torch.manual_seed(0)
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

    Sf = Ss = None; cand = []
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    out_toks = []; Wcur = W0.copy()
    def clean_write(direction):
        nonlocal Wcur
        d = direction.astype(np.float64); d = d/np.linalg.norm(d)
        u = np.random.RandomState(int(time.time()*1000)%99999).randn(4864); u = u/np.linalg.norm(u)
        P = np.outer(d, u); P = P/np.linalg.norm(P)*(np.linalg.norm(W0)*WRITE_SCALE)
        Wcur = Wcur + P
        sd2 = dict(sd); sd2[WN] = torch.tensor(Wcur).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)
    t0 = time.time()
    crashed = None
    print('V115 长跑3000 | C模式(慢S门槛+写活巩固) | 干扰@1500', flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        mix = Sf/(np.linalg.norm(Sf)+1e-9)
        if Ss is None: Ss = vn.copy()
        else:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS: Ss = (1-B_S)*Ss + B_S*vn; cand=[]
            else:
                cand.append(vn)
                if len(cand)>=5: Ss = (1-B_S)*Ss+B_S*vn; cand=[]
        if i>0 and i % WRITE_EVERY == 0 and Ss is not None: clean_write(Ss)
        mm = mix + 0.5*Ss/(np.linalg.norm(Ss)+1e-9); mix = mm/(np.linalg.norm(mm)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad(): logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.85,-1),1).item()
        if i == DISTRACT_AT:
            extra = tok(DISTRACT, return_tensors='pt').input_ids.to('cuda')
            ids = torch.cat([ids, extra], -1); Sf = None
            print('    [@%d 干扰注入!]' % i, flush=True); continue
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if len(out_toks)>=6 and len(set(out_toks[-6:]))==1: crashed='乱码复读'; break
        if (i+1) % 500 == 0:
            seg = tok.decode(out_toks[-300:], skip_special_tokens=True)
            wk = sum(1 for k in WORLD_KEYS if k in seg)
            reps = len(re.findall(r'(.{10,})\1', seg))
            print('    [%5d token %.0fs] 世界词x%d 复读x%d' % (i+1, time.time()-t0, wk, reps), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== 3000长跑报告 ===', flush=True)
    print('持续 %d token (%.0fs) | %s' % (len(out_toks), time.time()-t0, crashed or '到3000上限'), flush=True)
    L = len(text)
    for lab, seg in [('500-800', text[500:900]), ('1500-1900', text[1500:1900]), ('结尾', text[-250:])]:
        print('\n[%s] %s' % (lab, seg.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
