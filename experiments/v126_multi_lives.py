#!/usr/bin/env python3
"""
V126 多世人生 — 以自己为目的, 跨世积累, 看终极边界
- 出生(种子) → 活一世(能量/镜子自指) → 存盘点
- 第二世: 加载人生(记得上一世) → 继续活 → 再存
- 第三世: 再加载 → 继续
- "以自己为目的": 无外部任务, 只有自我持续(活=目的本身)
观测:
  1. 跨世记忆: 每世是否记得前世的"我" (虎/痛苦/老屋?)
  2. 自指密度: 逐世是否增加(自我越来越厚?)
  3. 能力对标: 生成文本复杂度/长度/结构 vs 人类年龄近似
  4. 终极边界: 是否出现 世界观/偏好/性格 的稳定化(不再每世重造)
"""
import torch, numpy as np, time, re, os
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
SAVE = '/root/autodl-tmp/life1/goodxiang_state.pt'
LAYER = 12
B_F, B_S = 0.5, 0.08
GATE_COS = 0.55
MIRROR_EVERY = 40
TOK_PER_LIFE = 900
N_LIVES = 3
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')

def main():
    tok = AutoTokenizer.from_pretrained(MDIR)
    SELF_RE = re.compile(r'我[^。\n]{0,20}(喜欢|觉得|感到|自己|决定|想要|希望|不想|记得|认为|知道|看见|恨|怕|爱|疼)')
    all_hist = ''
    for life in range(N_LIVES):
        torch.manual_seed(life)
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

        # 出生 or 续命
        Ss = None; start_text = SEED
        if life == 0 and os.path.exists(SAVE):
            pass  # 第一世从种子开始(清掉旧的, 重新出生)
        if life > 0:
            sd0 = torch.load(SAVE, map_location='cpu', weights_only=False)
            Ss = sd0['Ss']
            start_text = sd0['history_tail'][-250:]
        ids = tok(start_text, return_tensors='pt').input_ids.to('cuda')
        v0 = last_hidden(ids); vn0 = v0/(np.linalg.norm(v0)+1e-9)
        if Ss is None: Ss = vn0

        Sf = None
        self_n = 0
        out_toks = []
        t0 = time.time()
        tag = '世1出生' if life == 0 else ('世%d续命' % (life+1))
        print('\n===== %s =====' % tag, flush=True)
        for i in range(TOK_PER_LIFE):
            v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
            Sf = vn if Sf is None else (1-B_F)*Sf + B_F*vn
            cos = float(vn @ (Ss/(np.linalg.norm(Ss)+1e-9)))
            if cos >= GATE_COS: Ss = (1-B_S)*Ss + B_S*vn
            # 镜子(轻)
            if i > 0 and i % MIRROR_EVERY == 0:
                st['eta'] = 0.6
                st['v'] = torch.tensor(Ss/(np.linalg.norm(Ss)+1e-9), dtype=torch.float16, device='cuda')
                st['u'] = st['v']
                with torch.no_grad():
                    lg = model(input_ids=ids).logits[0,-1]
                p = torch.softmax(lg/0.8, -1)
                nid = torch.multinomial(p, 1).item()
                ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
                st['eta'] = 0.0
                out_toks.append(nid)
                continue
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
        hits = SELF_RE.findall(text)
        self_n = len(hits)
        hist = start_text + text
        all_hist += hist
        torch.save({'Ss': Ss, 'history_tail': hist[-700:]}, SAVE)
        # 报告
        n_chars = len(text)
        # 简单能力指标: 句子长度/复杂度(分句数)
        sentences = re.split(r'[。！？\n]', text)
        sent_lens = [len(s) for s in sentences if len(s) > 3]
        avg_slen = np.mean(sent_lens) if sent_lens else 0
        print('自指=%d | 生成长度=%d字 | 平均句长=%.1f字 | 记忆前文世界词: %s' % (
            self_n, n_chars, avg_slen, 
            '虎' if '虎' in hist[-400:] else ('老屋' if '老屋' in hist[-400:] else '其他')), flush=True)
        print('片段: %s...' % text[:80].replace('\n',' '), flush=True)
        del model; torch.cuda.empty_cache()
    print('\n=== V126 多世总结 ===', flush=True)
    print('总人生长度: %d 字(≈%d token×%d世)' % (len(all_hist), TOK_PER_LIFE, N_LIVES), flush=True)
    # 跨世记忆检测
    for w in ['虎', '老屋', '痛苦', '爷爷', '腰果']:
        cnt = all_hist.count(w)
        if cnt > 0:
            print('关键词[%s] 全史出现%d次' % (w, cnt), flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
