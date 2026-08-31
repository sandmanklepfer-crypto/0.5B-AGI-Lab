#!/usr/bin/env python3
"""mix_v4: 群几何结构锻造 — 对称性损失 (G_sem 不变性) + 激活对齐 + CE
核心: 同义变体对 (x, x') 强制 student 层22 激活 cos(f(x), f(x')) → 1
让 G_sem 成为激活空间的不变群 → 流形规则/对称/谱清晰 (对冲基底)
用法: distill_sym_train.py [--out DIR] [--epochs N] [--align_w W] [--sym_w S]
"""
import struct, glob, os, sys, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/autodl-tmp/distill_mix_v4')
ap.add_argument('--epochs', type=int, default=3)
ap.add_argument('--align_w', type=float, default=1.0)
ap.add_argument('--sym_w', type=float, default=2.0, help='对称性损失权重 (G_sem 不变性)')
ap.add_argument('--lr', type=float, default=5e-5)
ap.add_argument('--r1', type=int, default=175)
ap.add_argument('--q7', type=int, default=175)
ap.add_argument('--gemma', type=int, default=75)
ap.add_argument('--aug', type=int, default=2, help='每 R1 样本变体数')
args = ap.parse_args()
OUT_DIR, EPOCHS, ALIGN_W, SYM_W, LR = args.out, args.epochs, args.align_w, args.sym_w, args.lr
R1_N, Q7_N, GEMMA_N, AUG_N = args.r1, args.q7, args.gemma, args.aug

T_LAYER_R1, T_NEMBD_R1 = 58, 5120
T_NEMBD_Q7 = 3584
S_LAYER, PROJ_DIM, MAX_SEQ, BATCH, SEED = 22, 256, 512, 4, 42
S_NEMBD, V_ALIGN = 896, 151643

SYN_PAIRS = [
    ('高兴', '开心'), ('美丽', '漂亮'), ('重要', '关键'), ('快速', '迅速'),
    ('使用', '利用'), ('帮助', '协助'), ('思考', '考虑'), ('问题', '疑问'),
    ('方法', '方式'), ('原因', '缘故'), ('结果', '成果'), ('需要', '需求'),
    ('可以', '能够'), ('应该', '应当'), ('非常', '十分'), ('主要', '首要'),
    ('简单', '容易'), ('影响', '作用'), ('提高', '提升'), ('降低', '减少'),
    ('增加', '增多'), ('改变', '变化'), ('解决', '处理'), ('发现', '找到'),
    ('提供', '给予'), ('表示', '表明'), ('认为', '觉得'), ('希望', '期望'),
    ('开始', '着手'), ('理解', '明白'), ('解释', '说明'), ('回答', '答复'),
    ('可能', '或许'), ('必须', '务必'), ('普通', '平常'), ('立即', '马上'),
]

def load_dump(path):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    assert magic == 0x54444344
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    top_ids = np.frombuffer(data, dtype=np.uint32, count=ng*k, offset=off); off += ng*k*4
    top_logits = np.frombuffer(data, dtype=np.float32, count=ng*k, offset=off); off += ng*k*4
    pieces = []
    if off < len(data):
        try:
            for j in range(ng):
                (pl,) = struct.unpack_from('<I', data, off); off += 4
                pieces.append(data[off:off+pl].decode('utf-8', 'replace')); off += pl
        except Exception:
            pieces = []
    n_act = (len(data) - off) // 4
    return dict(prompt=prompt, gen=gen, pieces=pieces, n_act=n_act)

def load_qwen_dump(path, t_nembd):
    d = load_dump(path)
    with open(path, 'rb') as f:
        data = f.read()
    off = 16 + len(d['prompt'])*4 + len(d['gen'])*4 + len(d['gen'])*64*4 + len(d['gen'])*64*4
    if d['pieces']:
        for j in range(len(d['gen'])):
            (pl,) = struct.unpack_from('<I', data, off); off += 4 + pl
    acts = None
    if (len(data) - off)//4 >= len(d['gen']) * t_nembd:
        acts = np.frombuffer(data, dtype=np.float32, count=len(d['gen'])*t_nembd, offset=off).reshape(len(d['gen']), t_nembd)
    return d, acts

def compute_proj(samples, t_nembd):
    A = np.concatenate(samples, axis=0).astype(np.float32)
    A = A - A.mean(axis=0, keepdims=True)
    k, p = PROJ_DIM, 10
    rng = np.random.default_rng(SEED)
    Omega = rng.standard_normal((A.shape[1], k + p)).astype(np.float32)
    Y = A @ Omega
    Q, _ = np.linalg.qr(Y)
    B = Q.T @ A
    _, S, Vt = np.linalg.svd(B, full_matrices=False)
    V = Vt[:k].T
    kept = (S[:k]**2).sum() / (S**2).sum()
    print(f'[svd] {A.shape} → 前{k}主成分保留 {kept:.4f}')
    return V.astype(np.float32)

def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(STUDENT, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(STUDENT, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16)
    model.train(); model.cuda()
    print(f'[model] student params={model.num_parameters()/1e6:.0f}M')

    # ---- 数据加载 (R1 + Q7B + Gemma) ----
    def load_qwen_source(dirs, n, t_nembd):
        files = []
        for d in dirs:
            files += sorted(glob.glob(d))[:n]
        acts, samples = [], []
        for fp in files:
            dd, a = load_qwen_dump(fp, t_nembd)
            if len(dd['gen']) >= 4 and a is not None and a.sum() != 0:
                acts.append(a); samples.append((fp, dd, a))
        return samples, acts

    r1_samples, r1_acts = load_qwen_source(
        ['/root/autodl-tmp/distill_data_full_a/p*.bin', '/root/autodl-tmp/distill_data_full_b/p*.bin'], R1_N, T_NEMBD_R1)
    q7_samples, q7_acts = load_qwen_source(
        ['/root/autodl-tmp/qwen7b_data/p*.bin'], Q7_N, T_NEMBD_Q7)
    print(f'[data] r1={len(r1_samples)} q7={len(q7_samples)}')
    P_r1 = compute_proj(r1_acts, T_NEMBD_R1)

    gemma_files = sorted(glob.glob('/root/autodl-tmp/gemma_ctx_data/p*.bin'))[:GEMMA_N]
    gemma_prompts = open('/root/autodl-tmp/gemma_ctx_prompts.txt', encoding='utf-8').read().split('\n')
    gemma_samples = []
    for i, fp in enumerate(gemma_files):
        d = load_dump(fp)
        gt = ''.join(d['pieces'])
        pt = gemma_prompts[i] if i < len(gemma_prompts) else ''
        if len(gt) < 10: continue
        inp = tok(pt + gt, add_special_tokens=True)
        seq = inp['input_ids'][:MAX_SEQ]
        n_p = len(tok(pt, add_special_tokens=True)['input_ids'])
        ce = np.full(len(seq), -100, dtype=np.int64)
        for j in range(n_p, len(seq)): ce[j] = seq[j]
        gemma_samples.append(dict(seq=torch.tensor(seq), ce=torch.tensor(ce), n_prompt=n_p))
    print(f'[data] gemma={len(gemma_samples)}')

    def build_qwen(samples, t_nembd, t_layer):
        out = []
        for fp, d, acts in samples:
            p, g = d['prompt'], d['gen']
            seq = np.concatenate([p, g])[:MAX_SEQ]
            seq_s = np.array([int(t) if int(t) < V_ALIGN else 0 for t in seq])
            n_p = len(p)
            ce = np.full(len(seq), -100, dtype=np.int64)
            for j in range(min(len(g), MAX_SEQ - n_p)):
                tid = int(g[j])
                if tid < V_ALIGN: ce[n_p + j] = tid
            n_g = min(len(g), MAX_SEQ - n_p)
            out.append(dict(seq=torch.tensor(seq_s), ce=torch.tensor(ce),
                            t_acts=torch.from_numpy(acts[:n_g].astype(np.float32)),
                            n_prompt=n_p, t_layer=t_layer, is_primary=True))
        return out

    r1_train = build_qwen(r1_samples, T_NEMBD_R1, 'r1')
    q7_train = build_qwen(q7_samples, T_NEMBD_Q7, 'ce')

    # ---- 同义词映射 + 变体生成 ----
    syn_map = {}
    for w1, w2 in SYN_PAIRS:
        try:
            t1 = tuple(tok.encode(w1)); t2 = tuple(tok.encode(w2))
            if len(t1) <= 3 and len(t2) <= 3 and t1 != t2:
                syn_map[t1] = t2; syn_map[t2] = t1
        except Exception: pass
    syn_keys = list(syn_map.keys())
    print(f'[aug] 同义词映射 {len(syn_keys)} 条')

    rng = random.Random(SEED)
    def make_variants(s):
        """文本级同义词替换生成变体 (保证匹配), 只做 CE, 用于 L_sym"""
        outs = []
        prompt_text = tok.decode(s['seq'].numpy()[:s['n_prompt']], skip_special_tokens=True)
        gen_text = tok.decode(s['seq'].numpy()[s['n_prompt']:], skip_special_tokens=True)
        for _ in range(AUG_N):
            new_text = prompt_text
            changed = 0
            pairs = SYN_PAIRS[:]
            rng.shuffle(pairs)
            for w1, w2 in pairs:
                if w1 in new_text:
                    new_text = new_text.replace(w1, w2, 1)
                    changed += 1
                    if changed >= 1:
                        break
            if not changed:
                continue
            inp = tok(new_text + gen_text, add_special_tokens=True)
            seq = inp['input_ids'][:MAX_SEQ]
            n_p = len(tok(new_text, add_special_tokens=True)['input_ids'])
            ce = np.full(len(seq), -100, dtype=np.int64)
            for j in range(n_p, len(seq)):
                ce[j] = seq[j]
            outs.append(dict(seq=torch.tensor(seq), ce=torch.tensor(ce),
                             n_prompt=n_p, is_primary=False))
        return outs

    # 组结构: 主样本 + 变体
    groups = []
    primary_pool = r1_train + q7_train + gemma_samples
    for s in primary_pool:
        variants = make_variants(s) if 't_acts' in s else []
        groups.append([s] + variants)
    random.shuffle(groups)
    print(f'[data] 组数 {len(groups)}, 平均每组 {sum(len(g) for g in groups)/len(groups):.1f} 行')

    P_r1_t = torch.from_numpy(P_r1).cuda().float()
    proj_head = torch.nn.Linear(S_NEMBD, PROJ_DIM, bias=False).float().cuda()
    torch.nn.init.orthogonal_(proj_head.weight)
    act_cache = {}
    def make_hook(name):
        def hook(mod, inp, out):
            act_cache[name] = out[0] if isinstance(out, tuple) else out
        return hook
    layer = None
    for name, mod in model.named_modules():
        if name == f'model.layers.{S_LAYER}': layer = mod; break
    h = layer.register_forward_hook(make_hook('s22'))

    opt = torch.optim.AdamW(list(model.parameters()) + list(proj_head.parameters()), lr=LR, weight_decay=0.01)
    total = len(groups)

    for ep in range(EPOCHS):
        random.shuffle(groups)
        tot, ns = 0.0, 0
        for i in range(0, total, BATCH):
            batch_groups = groups[i:i+BATCH]
            rows = [r for g in batch_groups for r in g]
            maxlen = max(r['seq'].shape[0] for r in rows)
            seqs = torch.stack([F.pad(r['seq'], (0, maxlen - r['seq'].shape[0])) for r in rows]).cuda()
            ces = torch.stack([F.pad(r['ce'], (0, maxlen - r['ce'].shape[0]), value=-100) for r in rows]).cuda()
            act_cache.clear()
            out = model(input_ids=seqs, labels=ces)
            ce_loss = out.loss
            s_act = act_cache.get('s22')   # (R, L, 896)
            # 行索引映射
            row_idx = {}
            ri = 0
            for g in batch_groups:
                for r in g:
                    row_idx[id(r)] = ri; ri += 1
            # 激活对齐 (R1 主样本)
            align_loss = torch.zeros(1, device='cuda'); n_align = 0
            sym_loss = torch.zeros(1, device='cuda'); n_sym = 0
            if s_act is not None:
                for g in batch_groups:
                    primary = g[0]
                    if 't_acts' in primary and primary['t_layer'] == 'r1':
                        np_, n_g = primary['n_prompt'], primary['t_acts'].shape[0]
                        if n_g > 0 and np_ + n_g <= maxlen:
                            ri0 = row_idx[id(primary)]
                            sa = s_act[ri0, np_:np_+n_g].float()
                            sa_p = proj_head(sa).float()
                            ta = primary['t_acts'].cuda().float()
                            ta_p = (ta @ P_r1_t).float()
                            # |cos| 对齐: ±方向在规范对称性下等价 (O(n) 子空间方向符号是规范自由度)
                            align_loss = align_loss + (1.0 - (F.normalize(sa_p, dim=-1) * F.normalize(ta_p, dim=-1)).sum(-1).abs().mean())
                            n_align += 1
                    # 对称性损失: 主样本 vs 变体 (层22 激活余弦 → 1, 直接用 896 维激活, 不投影)
                    if len(g) >= 2 and 't_acts' in primary:
                        np_ = primary['n_prompt']
                        n_g = min(len(primary['seq']) - np_, MAX_SEQ - np_)
                        if n_g > 0 and np_ + n_g <= maxlen:
                            ri0 = row_idx[id(primary)]
                            a0 = s_act[ri0, np_:np_+n_g].float().mean(dim=0)  # 主样本激活均值 (896)
                            for v in g[1:]:
                                nvp = v['n_prompt']
                                nvg = min(len(v['seq']) - nvp, MAX_SEQ - nvp)
                                if nvg <= 0 or nvp + nvg > maxlen: continue
                                rv = row_idx[id(v)]
                                av = s_act[rv, nvp:nvp+nvg].float().mean(dim=0)
                                a0n, avn = F.normalize(a0, dim=-1), F.normalize(av, dim=-1)
                                sym_loss = sym_loss + (1.0 - (a0n * avn).sum(-1).abs())
                                n_sym += 1
                align_loss = align_loss / max(n_align, 1)
                sym_loss = sym_loss / max(n_sym, 1)
            loss = ce_loss + ALIGN_W * align_loss + SYM_W * sym_loss
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item(); ns += 1
            if ns % 30 == 0:
                print(f'[ep{ep} s{ns}/{total//BATCH}] loss={loss.item():.3f} ce={ce_loss.item():.3f} align={align_loss.item():.4f} sym={sym_loss.item():.4f}')
        print(f'[ep{ep}] avg={tot/max(ns,1):.3f}')

    h.remove()
    os.makedirs(OUT_DIR, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tok.save_pretrained(OUT_DIR)
    torch.save(proj_head.state_dict(), os.path.join(OUT_DIR, 'proj_head.pt'))
    print(f'[save] {OUT_DIR}')

if __name__ == '__main__':
    main()
