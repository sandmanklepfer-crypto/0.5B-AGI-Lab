#!/usr/bin/env python3
"""
V117 隐状态池 — 虚拟巨大隐状态 (多主题慢S池)
用户构想: 巨大的隐状态, 随上下文/时间增长, 不占显存, 虚拟存在
  → 极致增智慧 + 防复读(发散) + 不影响其他
实现: N个慢S(主题池), 每个896维(虚拟, 只是EMA数组)
  - 每token: 算当前v与各池的cos → 更新最匹配的1-2个池(soft assignment)
  - 池会自组织: 不同主题(马新/老屋/爷爷...)自动分到不同池
  - 生成时注入 = 多池加权混合(不是单慢S) → 发散/防执念
  - 物理开销: N×896 float = 64×896×4B = 229KB(虚拟, 不占显存大头)
指标: 复读率, 世界保持, 池使用分布(是否分化)
"""
import torch, numpy as np, time, re, os
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/qwen25_base_raw'
LAYER = 12
N_POOL = 24              # 池数(虚拟巨大)
B_POOL = 0.06           # 池EMA慢更新
B_FAST = 0.5
TEMP_ASSIGN = 5.0       # 分配温度(高=集中,低=均匀)
WRITE_EVERY = 40
WRITE_SCALE = 0.01
MAX_TOK = 1500
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

    # ---- 池初始化: 前N个token喂入分散初始化 ----
    ids = tok(SEED, return_tensors='pt').input_ids.to('cuda')
    pool = []          # 每个: dict(mean向量)
    use_count = np.zeros(N_POOL)
    def init_pools(ids, n_init=24):
        # 用初始文本+简单续写分散初始化池
        for i in range(n_init):
            v = last_hidden(ids)
            vn = v/(np.linalg.norm(v)+1e-9)
            pool.append(vn.copy())
            use_count[i] = 0
            with torch.no_grad():
                logits = model(input_ids=ids).logits[0,-1]
            nid = torch.multinomial(torch.softmax(logits/0.9,-1),1).item()
            ids = torch.cat([ids, torch.tensor([[nid]],device='cuda')],-1)
        return ids
    ids = init_pools(ids)

    def pool_update(vn):
        """soft分配: 更新最匹配的池(带温度软分配)"""
        P = np.stack(pool)  # (N,896)
        cos = P @ vn        # (N,)
        w = np.exp(TEMP_ASSIGN * cos)
        w = w / (w.sum() + 1e-9)
        for i in range(N_POOL):
            pool[i] = pool[i] * (1 - B_POOL*w[i]) + B_POOL*w[i]*vn
            use_count[i] += w[i]
        # 返回注入方向 = 加权混合(主池主导+次池点缀=发散)
        idx = np.argsort(-cos)[:4]
        mix = sum(cos[i] * pool[i] for i in idx)
        mix = mix / (np.linalg.norm(mix) + 1e-9)
        return mix

    Sf = None
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
    print('V117 隐状态池 | %d池×896维=虚拟%.0fKB | 软分配T=%.1f | 写活每%d步' % (
        N_POOL, N_POOL*896*4/1024, TEMP_ASSIGN, WRITE_EVERY), flush=True)
    for i in range(MAX_TOK):
        v = last_hidden(ids); vn = v/(np.linalg.norm(v)+1e-9)
        Sf = vn if Sf is None else (1-B_FAST)*Sf + B_FAST*vn
        mix_pool = pool_update(vn)          # 池注入(发散/多主题)
        mix = 0.7*Sf/(np.linalg.norm(Sf)+1e-9) + 0.5*mix_pool
        mix = mix/(np.linalg.norm(mix)+1e-9)
        if i>0 and i % WRITE_EVERY == 0:
            clean_write(mix_pool)            # 写池主导方向(多主题轮换, 不锁死)
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
            print('    [%5d %.0fs] 世界词x%d 复读x%d' % (i+1, time.time()-t0, wk, reps), flush=True)
    text = tok.decode(out_toks, skip_special_tokens=True)
    # 池分化度
    active = (use_count > 0.1).sum()
    entropy = -((use_count+1e-9)/use_count.sum()*np.log((use_count+1e-9)/use_count.sum())).sum()
    print('\n=== 隐状态池报告 ===', flush=True)
    print('持续%d token | %s | 池激活=%d/%d 熵=%.2f(max=%.2f)' % (
        len(out_toks), crashed or 'OK', int(active), N_POOL, entropy, np.log(N_POOL)), flush=True)
    reps_all = len(re.findall(r'(.{12,})\1', text))
    print('全文复读x%d (小=好)' % reps_all, flush=True)
    L = len(text)
    for lab, seg in [('中段', text[L//2:L//2+180]), ('结尾', text[-180:])]:
        print('\n[%s] %s' % (lab, seg.replace('\n',' ')), flush=True)
    hook.remove()
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
