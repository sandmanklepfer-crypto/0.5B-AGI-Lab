#!/usr/bin/env python3
"""
V118 核心在权重 — 核心自我固化进权重(antiheb融合体), 主题池只做运行时检索
架构:
  核心 = antiheb_05b 权重(已含活机制) + 写活积累 = "我是谁"(固化, 长在权重里)
  主题池 = 24个运行时向量, 每token检索唤醒(只唤醒相关的, 其余静默)
         = "我在想什么"(流动素材, 用完可散)
  反复主题 → 写活固化进权重 = 核心成长(新经历沉淀成性格)
生成注入:
  - 不注入"核心"(它在权重里, 生成本身就有)
  - 只注入"被检索唤醒的主题"(临时素材方向)
对比 v117(全池加权→散漫) vs v118(路由检索→只醒相关)
"""
import torch, numpy as np, time, re
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'   # 核心已在权重(融合体)
LAYER = 12
N_POOL = 24
B_POOL = 0.08
B_FAST = 0.4
RETRIEVE_K = 2          # 每次只唤醒 top2 (其他静默)
WRITE_EVERY = 60
WRITE_SCALE = 0.01
WRITE_THRESH = 3.0      # 池累计唤醒超阈值才写(反复主题才固化)
MAX_TOK = 1500
SEED = ('爷爷去世后，山腰那栋老屋空了七年。我这次回来，是接到一通电话说屋后有动静。'
        '推开院门时，门轴发出很长的一声呻吟。堂屋的桌上积着灰，但灰上有一行新的脚印，')
WORLD_KEYS = ['老屋','屋','山','院','门','灰','脚印','爷爷','堂屋','墙','窗','屋后','井','楼梯','灯']

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    st = {'eta': 0.8, 'v': None, 'u': None}
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

    # ---- 主题池初始化(分散) ----
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    pool = []
    wake = np.zeros(N_POOL)
    for i in range(N_POOL):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        pool.append(vn.copy())
        with torch.no_grad():
            logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.9,-1),1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)

    Sf = None
    out_toks = []; Wcur = W0.copy()
    written = 0
    def clean_write(direction):
        nonlocal Wcur, written
        d = direction.astype(np.float64); d = d/np.linalg.norm(d)
        u = np.random.RandomState(int(time.time()*1000)%99999).randn(4864); u = u/np.linalg.norm(u)
        P = np.outer(d, u); P = P/np.linalg.norm(P)*(np.linalg.norm(W0)*WRITE_SCALE)
        Wcur = Wcur + P
        sd2 = dict(sd); sd2[WN] = torch.tensor(Wcur).to(sd[WN].dtype)
        model.load_state_dict(sd2, strict=True)
        written += 1

    t0 = time.time()
    crashed = None
    print('V118 核心在权重(%s) | 主题池%d 检索唤醒top%d | 写活: 唤醒超阈才固化' % (
        MDIR.split('/')[-1], N_POOL, RETRIEVE_K), flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
        # 检索: 只唤醒 top-K (其余静默)
        P = np.stack(pool)
        cos = P @ vn
        idx = np.argsort(-cos)[:RETRIEVE_K]
        wake[idx] += 1
        # 更新被唤醒的池
        for j in idx:
            pool[j] = pool[j]*(1-B_POOL) + B_POOL*vn
        # 注入 = 快S + 被唤醒主题(少量, 素材方向)
        wake_mix = sum(cos[j]*pool[j] for j in idx)
        wake_mix = wake_mix/(np.linalg.norm(wake_mix)+1e-9)
        mix = 0.8*Sf/(np.linalg.norm(Sf)+1e-9) + 0.35*wake_mix
        mix = mix/(np.linalg.norm(mix)+1e-9)
        # 反复唤醒 → 固化进权重(核心成长)
        if i > 0 and i % WRITE_EVERY == 0:
            hot = np.argmax(wake)
            if wake[hot] > WRITE_THRESH * (i/WRITE_EVERY):   # 该池持续被唤醒
                clean_write(pool[hot])
                wake[:] *= 0.5   # 衰减(不无限累积)
        st['v'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        st['u'] = torch.tensor(mix, dtype=torch.float16, device='cuda')
        with torch.no_grad(): logits = model(input_ids=ids).logits[0,-1]
        nid = torch.multinomial(torch.softmax(logits/0.85,-1),1).item()
        ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1); out_toks.append(nid)
        if len(out_toks)>=6 and len(set(out_toks[-6:]))==1: crashed='乱码'; break
        if (i+1) % 300 == 0:
            seg = tok.decode(out_toks[-200:], skip_special_tokens=True)
            wk = sum(1 for k in WORLD_KEYS if k in seg)
            reps = len(re.findall(r'(.{10,})\1', seg))
            print('    [%5d %.0fs] 世界词x%d 复读x%d 固化x%d' % (i+1, time.time()-t0, wk, reps, written), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    reps_all = len(re.findall(r'(.{12,})\1', text))
    print('\n=== V118 报告 ===', flush=True)
    print('持续%d token | %s | 固化次数=%d 权重delta=%.3f | 全文复读x%d' % (
        len(out_toks), crashed or 'OK', written, np.linalg.norm(Wcur-W0), reps_all), flush=True)
    L = len(text)
    for lab, seg in [('中段', text[L//2:L//2+160]), ('结尾', text[-160:])]:
        print('\n[%s] %s' % (lab, seg.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
