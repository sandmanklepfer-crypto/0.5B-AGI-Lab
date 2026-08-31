#!/usr/bin/env python3
"""三 teacher 混合几何蒸馏: R1(结构) + Qwen7B(执行) + Gemma(上下文)
- R1 数据: id直连 CE + 激活对齐(层58, 5120维, SVD 256)
- Qwen7B 数据: id直连 CE + 激活对齐(层24, 3584维, SVD 256)
- Gemma 数据: 跨族, piece文本重建 → student 编码 CE (无激活对齐)
防过拟合: 每源 ~175 条 + 3 epochs + align_w 0.5
用法: distill_mix_train.py [--out DIR] [--epochs N] [--align_w W] [--r1 N] [--q7 N] [--gemma N]
"""
import struct, glob, os, sys, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/autodl-tmp/distill_mix_v1')
ap.add_argument('--epochs', type=int, default=3)
ap.add_argument('--align_w', type=float, default=0.5)
ap.add_argument('--lr', type=float, default=5e-5)
ap.add_argument('--r1', type=int, default=175)
ap.add_argument('--q7', type=int, default=175)
ap.add_argument('--gemma', type=int, default=75)
ap.add_argument('--aug', type=int, default=0, help='每样本语义不变增广变体数 (规范对称结构增强)')
args = ap.parse_args()
OUT_DIR, EPOCHS, ALIGN_W, LR = args.out, args.epochs, args.align_w, args.lr
R1_N, Q7_N, GEMMA_N, AUG_N = args.r1, args.q7, args.gemma, args.aug

# 语义不变变换: 同义词对 (G_sem 的生成元, 中文高频词)
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

T_LAYER_R1, T_NEMBD_R1 = 58, 5120
T_LAYER_Q7, T_NEMBD_Q7 = 24, 3584
S_LAYER, PROJ_DIM, MAX_SEQ, BATCH, SEED = 22, 256, 512, 4, 42
S_NEMBD = 896
V_ALIGN = 151643  # Qwen 族 tokenizer 对齐阈值

# ---------- 数据解析 ----------
def load_dump(path):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    assert magic == 0x54444344, f'bad magic {path}'
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
    n_act = (len(data) - off) // 4
    acts = None
    if n_act >= len(d['gen']) * t_nembd:
        acts = np.frombuffer(data, dtype=np.float32, count=len(d['gen'])*t_nembd, offset=off).reshape(len(d['gen']), t_nembd)
    return d, acts

def compute_proj(samples, t_nembd):
    rows = [s for s in samples if s is not None]
    if not rows:
        return None
    A = np.concatenate(rows, axis=0).astype(np.float32)
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

    # ===== R1 数据 (id直连 + 激活对齐) =====
    r1_files = sorted(glob.glob('/root/autodl-tmp/distill_data_full_a/p*.bin'))[:R1_N]
    r1_files += sorted(glob.glob('/root/autodl-tmp/distill_data_full_b/p*.bin'))[:max(0, R1_N - len(r1_files))]
    r1_acts, r1_samples = [], []
    for fp in r1_files:
        d, acts = load_qwen_dump(fp, T_NEMBD_R1)
        if len(d['gen']) >= 4 and acts is not None and acts.sum() != 0:
            r1_acts.append(acts)
            r1_samples.append((fp, d, acts))
    print(f'[r1] {len(r1_samples)} samples')
    P_r1 = compute_proj(r1_acts, T_NEMBD_R1)

    # ===== Qwen7B 数据 (id直连 + 激活对齐) =====
    q7_files = sorted(glob.glob('/root/autodl-tmp/qwen7b_data/p*.bin'))[:Q7_N]
    q7_acts, q7_samples = [], []
    for fp in q7_files:
        d, acts = load_qwen_dump(fp, T_NEMBD_Q7)
        if len(d['gen']) >= 4 and acts is not None and acts.sum() != 0:
            q7_acts.append(acts)
            q7_samples.append((fp, d, acts))
    print(f'[q7] {len(q7_samples)} samples')
    P_q7 = compute_proj(q7_acts, T_NEMBD_Q7)

    # ===== Gemma 数据 (文本 CE) =====
    gemma_files = sorted(glob.glob('/root/autodl-tmp/gemma_ctx_data/p*.bin'))[:GEMMA_N]
    gemma_prompts = open('/root/autodl-tmp/gemma_ctx_prompts.txt', encoding='utf-8').read().split('\n')
    gemma_samples = []
    for i, fp in enumerate(gemma_files):
        d = load_dump(fp)
        gt = ''.join(d['pieces'])
        pt = gemma_prompts[i] if i < len(gemma_prompts) else ''
        if len(gt) < 10:
            continue
        inp = tok(pt + gt, add_special_tokens=True)
        seq = inp['input_ids'][:MAX_SEQ]
        n_p = len(tok(pt, add_special_tokens=True)['input_ids'])
        ce = np.full(len(seq), -100, dtype=np.int64)
        for j in range(n_p, len(seq)):
            ce[j] = seq[j]
        gemma_samples.append(dict(seq=torch.tensor(seq), ce=torch.tensor(ce), n_prompt=n_p))
    print(f'[gemma] {len(gemma_samples)} samples (text CE)')

    # ===== 构建 Qwen 族训练样本 =====
    def build_qwen_samples(samples, t_nembd, t_layer):
        out = []
        unk = 0
        for fp, d, acts in samples:
            p, g = d['prompt'], d['gen']
            seq = np.concatenate([p, g])[:MAX_SEQ]
            seq_s = np.array([int(t) if int(t) < V_ALIGN else unk for t in seq])
            n_p = len(p)
            ce = np.full(len(seq), -100, dtype=np.int64)
            for j in range(min(len(g), MAX_SEQ - n_p)):
                tid = int(g[j])
                if tid < V_ALIGN:
                    ce[n_p + j] = tid
            n_g = min(len(g), MAX_SEQ - n_p)
            t_acts = acts[:n_g]
            out.append(dict(seq=torch.tensor(seq_s), ce=torch.tensor(ce),
                            t_acts=torch.from_numpy(t_acts.astype(np.float32)),
                            n_prompt=n_p, t_layer=t_layer))
        return out

    # 同义词 token 映射 (G_sem 生成元的 token 级实现)
    syn_map = {}
    for w1, w2 in SYN_PAIRS:
        try:
            t1 = tuple(tok.encode(w1))
            t2 = tuple(tok.encode(w2))
            if len(t1) <= 3 and len(t2) <= 3 and t1 != t2:
                syn_map[t1] = t2
                syn_map[t2] = t1
        except Exception:
            pass
    syn_keys = list(syn_map.keys())
    print(f'[aug] 同义词 token 映射 {len(syn_keys)} 条')

    def augment_seq(seq_s, n_p, rng):
        """对 prompt 部分做 1 处同义词替换, 返回变体序列 (无激活)"""
        if not syn_keys or n_p < 2:
            return None
        # 随机选一个替换位置
        arr = seq_s[:n_p].tolist()
        candidates = []
        for i in range(len(arr)):
            for k, v in syn_map.items():
                if i + len(k) <= len(arr) and tuple(arr[i:i+len(k)]) == k:
                    candidates.append((i, k, v))
                    break
        if not candidates:
            return None
        i, k, v = rng.choice(candidates)
        new_prompt = arr[:i] + list(v) + arr[i+len(k):]
        new_seq = new_prompt + seq_s[n_p:].tolist()
        return torch.tensor(new_seq), len(new_prompt)

    def make_aug_samples(samples, rng):
        aug = []
        for s in samples:
            for _ in range(AUG_N):
                r = augment_seq(s['seq'].numpy(), s['n_prompt'], rng)
                if r is None:
                    continue
                new_seq, new_np = r
                n_g = len(s['seq']) - s['n_prompt']
                ce = np.full(len(new_seq), -100, dtype=np.int64)
                for j in range(n_g):
                    pos = new_np + j
                    if pos < len(new_seq):
                        tid = int(s['ce'][s['n_prompt'] + j])
                        if tid >= 0:
                            ce[pos] = tid
                aug.append(dict(seq=new_seq, ce=torch.tensor(ce),
                                n_prompt=new_np))
        return aug

    r1_train = build_qwen_samples(r1_samples, T_NEMBD_R1, 'r1')
    q7_train = build_qwen_samples(q7_samples, T_NEMBD_Q7, 'ce')  # q7 只做 CE, 不对齐
    all_train = r1_train + q7_train + gemma_samples
    if AUG_N > 0:
        rng = random.Random(SEED)
        aug_s = make_aug_samples(r1_train + q7_train, rng)
        all_train += aug_s
        print(f'[aug] 语义不变增广 +{len(aug_s)} 样本 (G_sem 规范对称增强)')
    random.shuffle(all_train)
    print(f'[data] 总训练样本 {len(all_train)} (r1={len(r1_train)} q7={len(q7_train)} gemma={len(gemma_samples)} aug={len(all_train)-len(r1_train)-len(q7_train)-len(gemma_samples)})')

    P_r1_t = torch.from_numpy(P_r1).cuda().float()
    P_q7_t = torch.from_numpy(P_q7).cuda().float()
    proj_head = torch.nn.Linear(S_NEMBD, PROJ_DIM, bias=False).float().cuda()
    torch.nn.init.orthogonal_(proj_head.weight)

    act_cache = {}
    def make_hook(name):
        def hook(mod, inp, out):
            act_cache[name] = out[0] if isinstance(out, tuple) else out
        return hook
    layer = None
    for name, mod in model.named_modules():
        if name == f'model.layers.{S_LAYER}':
            layer = mod
            break
    if layer is None:
        print('层不存在'); return
    h = layer.register_forward_hook(make_hook('s22'))

    opt = torch.optim.AdamW(list(model.parameters()) + list(proj_head.parameters()), lr=LR, weight_decay=0.01)
    total = len(all_train)

    def masked_softmax(x, mask):
        x = x.masked_fill(~mask, -1e9)
        x = x - x.max(dim=-1, keepdim=True).values
        e = torch.exp(x) * mask.float()
        return e / (e.sum(-1, keepdim=True) + 1e-9)

    for ep in range(EPOCHS):
        random.shuffle(all_train)
        tot = 0.0; ns = 0
        for i in range(0, total, BATCH):
            batch = all_train[i:i+BATCH]
            maxlen = max(s['seq'].shape[0] for s in batch)
            seqs = torch.stack([F.pad(s['seq'], (0, maxlen - s['seq'].shape[0])) for s in batch]).cuda()
            ces = torch.stack([F.pad(s['ce'], (0, maxlen - s['ce'].shape[0]), value=-100) for s in batch]).cuda()
            act_cache.clear()
            out = model(input_ids=seqs, labels=ces)
            ce_loss = out.loss
            align_loss = torch.zeros(1, device='cuda')
            n_tok = 0
            s_act = act_cache.get('s22')
            if s_act is not None:
                for bi, s in enumerate(batch):
                    if 't_acts' not in s or s['t_layer'] != 'r1':
                        continue
                    np_, n_g = s['n_prompt'], s['t_acts'].shape[0]
                    if n_g == 0 or np_ + n_g > maxlen:
                        continue
                    sa = s_act[bi, np_:np_+n_g].float()
                    sa_p = proj_head(sa).float()
                    ta = s['t_acts'].cuda().float()
                    ta_p = (ta @ P_r1_t).float()
                    sa_n = F.normalize(sa_p, dim=-1)
                    ta_n = F.normalize(ta_p, dim=-1)
                    align_loss = align_loss + (1.0 - (sa_n * ta_n).sum(-1)).mean()
                    n_tok += 1
                align_loss = align_loss / max(n_tok, 1)
            loss = ce_loss + ALIGN_W * align_loss
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item(); ns += 1
            if ns % 30 == 0:
                print(f'[ep{ep} s{ns}/{total//BATCH}] loss={loss.item():.3f} ce={ce_loss.item():.3f} align={align_loss.item():.4f}')
        print(f'[ep{ep}] avg={tot/max(ns,1):.3f}')

    h.remove()
    os.makedirs(OUT_DIR, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tok.save_pretrained(OUT_DIR)
    torch.save(proj_head.state_dict(), os.path.join(OUT_DIR, 'proj_head.pt'))
    print(f'[save] {OUT_DIR}')

if __name__ == '__main__':
    main()
