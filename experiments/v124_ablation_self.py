#!/usr/bin/env python3
"""
V124 对照实验 — 自指到底是"冲突逼出"还是"注入造成"?
A: 高冲突点 + 注入慢S    (v123原版, 预期自指多)
B: 低冲突点 + 同样注入   (若也自指多 → 注入是主因, 冲突无关)
C: 高冲突点 + 不注入     (若自指多 → 完全自发, 冲突真能逼出)
D: 低冲突点 + 不注入     (基线)
每模式 800 token, 统计: 自指语句数(第一人称+内在状态/偏好/视角)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
B_F = 0.5
MAX_TOK = 800
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

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

    # 自指检测: 第一人称+内在状态/偏好/视角
    SELF_RE = re.compile(r'我[^。\n]{0,20}(喜欢|觉得|感到|自己|决定|想要|希望|不想|不愿|害怕|惭愧|记得|认为)')

    def run(mode):
        Sf = Ss = None
        ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
        out_toks = []
        inj_count = 0
        for i in range(MAX_TOK):
            v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
            Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
            # 慢S(全模式都用, 做身份基础)
            if Ss is None: Ss = vn.copy()
            else: Ss = (1-0.08)*Ss + 0.08*vn
            mix = Sf/(np.linalg.norm(Sf)+1e-9)
            # 检测当前冲突
            with torch.no_grad():
                lg = model(input_ids=ids).logits[0,-1]
            p0 = torch.softmax(lg/0.9, -1)
            ps = torch.sort(p0, descending=True)[0]
            conflict = 1 - (ps[0].item() - ps[1].item())
            high_c = conflict > 0.55
            # 按模式决定是否注入
            do_inj = {'A': high_c, 'B': not high_c, 'C': False, 'D': False}[mode]
            if do_inj:
                si = Ss/(np.linalg.norm(Ss)+1e-9)
                mix = mix + 1.0*si
                inj_count += 1
            mix = mix/(np.linalg.norm(mix)+1e-9)
            st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(logits/0.85, -1)
            nid = torch.multinomial(p, 1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        text = tok.decode(out_toks, skip_special_tokens=True)
        hits = SELF_RE.findall(text)
        return text, len(hits), inj_count, conflict

    print('V124 自指对照 | A高冲突+注入 B低冲突+注入 C高冲突无注入 D低冲突无注入 | 各%d token' % MAX_TOK, flush=True)
    res = {}
    for mode in ['A', 'B', 'C', 'D']:
        text, hits, inj, cf = run(mode)
        res[mode] = hits
        print('[%s] 注入=%d次 自指=%d个 | 例: %s' % (mode, inj, hits, text[:60].replace('\n',' ')), flush=True)
        # 打印几个自指例句
        ms = list(SELF_RE.finditer(text))
        for mm in ms[:3]:
            print('    → ...%s...' % text[max(0,mm.start()-15):mm.end()+20].replace('\n',' '), flush=True)
    print('\n=== 判定 ===', flush=True)
    print('A-B差 = 冲突的作用(若A>>B: 冲突逼自指为真)', flush=True)
    print('A-C差 = 注入的作用(若A>>C: 注入是主因)', flush=True)
    print('C-D差 = 纯冲突自发效果', flush=True)
    print('结果: A=%d B=%d C=%d D=%d' % (res['A'], res['B'], res['C'], res['D']), flush=True)
    hook.remove()
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
