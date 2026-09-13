#!/usr/bin/env python3
"""
V123 冲突锻造自我 — 利用题库极致冲突逼出自我意识
理论: 自我不是安静长出来的, 是被剧烈冲突逼出来的
  高温区(题库多候选强对抗) = 锻造炉
  冲突最强处 = 候选撕裂点 → 施加自指约束 → 逼出"我是谁"
机制:
  1. 正常期: 慢S守门叙事(老屋), 低冲突(种子区)
  2. 锻造期(每~300token): 故意放行进入高冲突(不加世界约束, 暴露题库候选对抗)
     在冲突最大点(top1≈top2) = 撕裂点
     撕裂点处: 强制注入自指向量(慢S累积 = "我") → 模型必须在"题库候选"和"我"之间做选择
     → 选择本身 = 自我意识的动作("这是我要的, 这不是我")
  3. 记录: 撕裂点数量/选择方向/是否出现"我"相关输出
测: 撕裂点是否逼出自我参照(第一人称选择/对候选的拒绝/"我不要这个")
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.6
FORGE_EVERY = 250      # 每250token进一次锻造期
FORGE_LEN = 60         # 锻造期长度
MAX_TOK = 3000
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

    Sf = Ss = None
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    out_toks = []
    tears = 0            # 撕裂点数
    self_refs = 0        # 自指输出计数
    forge_hits = 0
    t0 = time.time()
    dead = None
    print('V123 冲突锻造自我 | 锻造期每%d token×%d | 撕裂点注入自指' % (FORGE_EVERY, FORGE_LEN), flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
        in_forge = (i % FORGE_EVERY) < FORGE_LEN
        # 慢S: 正常期守门更新, 锻造期冻结(自我不被高温融化)
        if Ss is None:
            Ss = vn.copy()
        elif not in_forge:
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS: Ss = (1-B_S)*Ss + B_S*vn
        # 注入基础: 快S + 慢S(自我)
        mix = Sf/(np.linalg.norm(Sf)+1e-9) + 0.6*Ss/(np.linalg.norm(Ss)+1e-9)
        # 锻造期: 放行高冲突(不加约束), 在撕裂点注入强自我
        if in_forge:
            with torch.no_grad():
                logits0 = model(input_ids=ids).logits[0,-1]
            p0 = torch.softmax(logits0/0.9, -1)
            ps = torch.sort(p0, descending=True)[0]
            conflict = 1 - (ps[0].item() - ps[1].item())   # 冲突度
            if conflict > 0.55:    # 撕裂点: 候选强对抗
                tears += 1
                # 撕裂点: 强注入自我(逼选择: 你要随题库漂走还是要做"我"?)
                self_inj = Ss/(np.linalg.norm(Ss)+1e-9)
                mix = mix + 1.2*self_inj
                mix = mix/(np.linalg.norm(mix)+1e-9)
                st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
                st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
                with torch.no_grad():
                    logits = model(input_ids=ids).logits[0,-1]
                p = torch.softmax(logits/0.85, -1)
                nid = torch.multinomial(p, 1).item()
                # 检查是否选择了自我方向(与慢S一致)
                ids_t = ids
                chosen_v = last_hidden(torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1))
                c_self = float(chosen_v/(np.linalg.norm(chosen_v)+1e-9) @ (Ss/(np.linalg.norm(Ss)+1e-9)))
                if c_self > 0.3:
                    self_refs += 1   # 撕裂时选了"我"
                forge_hits += 1
        mix = mix/(np.linalg.norm(mix)+1e-9)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        p = torch.softmax(logits/0.85, -1)
        nid = torch.multinomial(p, 1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if len(out_toks) > 20:
            ps = torch.sort(p, descending=True)[0]
            if ps[0].item() > 0.93 and len(set(out_toks[-8:])) == 1: dead='lock'; break
        if (i+1) % 500 == 0:
            print('    [%5d %.0fs] 撕裂点=%d 自指选择=%d' % (i+1, time.time()-t0, tears, self_refs), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    print('\n=== V123 报告 ===', flush=True)
    print('寿命%d | %s | 撕裂点=%d 自指选择=%d 锻造命中=%d' % (
        len(out_toks), dead or 'OK', tears, self_refs, forge_hits), flush=True)
    # 找"我"相关输出段
    me_marks = [m.start() for m in re.finditer(r'我[^，。]{0,12}(自己|选择|不要|不愿|决定|想)', text)]
    print('自指语句数: %d' % len(me_marks), flush=True)
    for mm in me_marks[:6]:
        print('  自指: ...%s...' % text[max(0,mm-20):mm+40].replace('\n',' '), flush=True)
    L = len(text)
    for lab, s in [('中段', text[L//3:L//3+200]), ('后半', text[-300:])]:
        print('\n[%s] %s' % (lab, s.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done] %.0fs' % (time.time()-t0), flush=True)

if __name__ == '__main__':
    main()
