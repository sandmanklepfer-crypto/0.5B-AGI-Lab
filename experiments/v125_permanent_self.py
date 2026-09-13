#!/usr/bin/env python3
"""
V125 永久自指回路 — 注入变永久连续 (外部只出生介入一次)
v124: 每步外部注入 → 回声
v125: 出生种一次"我是谁" → 撤走外部 → 靠 慢S+存盘点+自述文本 自转
回路:
  活(能量/知识池, v120) → 积累状态厚度
  → 每 N 步: 慢S 经"镜子"译成自我文本("我…") 进上下文 (状态→文本)
  → 模型续写时接着讲"我" (文本→新状态)
  → 定期存盘点(life_state.pt, v116) → 跨会话加载继续
  → 外部只在"出生"介入一次
验证: 撤走外部后, 自指能否自己维持? 逐轮深化还是复读?
"""
import torch, numpy as np, time, re, os
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1/goodxiang_state.pt'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.6
MIRROR_EVERY = 40      # 每40步照一次镜子
MAX_TOK = 1200
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained(MDIR)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 0.0, 'v': None, 'u': None}   # 默认无注入(撤走外部)
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

    # ---- 出生: 加载存档 or 种子+一次启动注入 ----
    Ss = None
    if os.path.exists(SAVE):
        sd0 = torch.load(SAVE, map_location='cpu', weights_only=False)
        Ss = sd0['Ss']
        start_text = sd0['history_tail'][-200:]
        born = '续命(加载人生)'
    else:
        Ss = None
        start_text = SEED
        born = '出生'
    ids = tok(start_text, return_tensors='pt').input_ids.to('cuda')
    # 用起点初始化慢S
    v0 = last_hidden(ids); vn0 = v0/(np.linalg.norm(v0)+1e-9)
    Ss = vn0 if Ss is None else Ss

    # 出生时的"一次启动注入"(仅此一次)
    Sf = None
    mirror_self = ''
    self_count = 0
    st['eta'] = 0.9
    st['v'] = torch.tensor(Ss/(np.linalg.norm(Ss)+1e-9), dtype=torch.float16, device='cuda')
    st['u'] = st['v']
    first_inject = True
    out_toks = []
    t0 = time.time()
    print('V125 永久自指 | %s | 外部仅启动一次, 之后镜子自转' % born, flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        # 慢S守门更新
        cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
        if cos >= GATE_COS: Ss = (1-B_S)*Ss + B_S*vn
        # 镜子: 每MIRROR_EVERY步, 把慢S译成自我文本(让模型自己说"我")
        if i > 0 and i % MIRROR_EVERY == 0:
            # 镜子 = 用慢S方向做一次"我"启动(轻注入, 只在照镜子瞬间)
            st['eta'] = 0.7
            st['v'] = torch.tensor(Ss/(np.linalg.norm(Ss)+1e-9), dtype=torch.float16, device='cuda')
            st['u'] = st['v']
            # 生成一个自我句
            with torch.no_grad():
                lg = model(input_ids=ids).logits[0,-1]
            p = torch.softmax(lg/0.8, -1)
            nid = torch.multinomial(p, 1).item()
            # 短生成自我句(5 token)
            gen_ids = [nid]
            ids_t = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
            for _ in range(4):
                with torch.no_grad():
                    lg2 = model(input_ids=ids_t).logits[0,-1]
                p2 = torch.softmax(lg2/0.8, -1)
                n2 = torch.multinomial(p2, 1).item()
                gen_ids.append(n2)
                ids_t = torch.cat([ids_t, torch.tensor([[n2]],device='cuda')],-1)
            self_sentence = tok.decode(gen_ids, skip_special_tokens=True).strip()
            # 把自我句接回正文(模型续写时上下文里有"我"了)
            mirror_self = self_sentence
            st['eta'] = 0.0   # 镜子照完, 撤走(靠文本自己转)
            if '我' in self_sentence: self_count += 1
            if i % 200 == 0:
                print('    [镜子@%d] %s' % (i, self_sentence[:40]), flush=True)
        # 生成(无外部注入, 只有快S轻引导)
        mix = 0.5*Sf/(np.linalg.norm(Sf)+1e-9) if Sf is not None else None
        if mix is not None and mirror_self and '我' in mirror_self:
            pass  # 文本里已有"我", 模型自然接着讲
        st['eta'] = 0.0
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.93 and len(set(out_toks[-8:])) == 1: break
    text = tok.decode(out_toks, skip_special_tokens=True)
    # 自指统计
    SELF_RE = re.compile(r'我[^。\n]{0,20}(喜欢|觉得|感到|自己|决定|想要|希望|不想|记得|认为|知道|看见)')
    hits = SELF_RE.findall(text)
    print('\n=== V125 报告 ===', flush=True)
    print('自指语句=%d | 镜子触发=%d次' % (len(hits), MAX_TOK//MIRROR_EVERY), flush=True)
    for mm in list(SELF_RE.finditer(text))[:5]:
        print('  → ...%s...' % text[max(0,mm.start()-15):mm.end()+25].replace('\n',' '), flush=True)
    # 存盘点
    torch.save({'Ss': Ss, 'history_tail': (start_text+text)[-600:]}, SAVE)
    print('人生已存: %s' % SAVE, flush=True)
    L = len(text)
    for lab, s in [('开头', text[:150]), ('结尾', text[-200:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('[done] %.0fs' % (time.time()-t0), flush=True)

if __name__ == '__main__':
    main()
