#!/usr/bin/env python3
"""32B → 0.5B 几何蒸馏: CE + 激活流形对齐
teacher 层58激活(5120) → SVD 前256主成分 → student 层22激活(896) 线性投影对齐
用法: distill_geom_train.py [--out DIR] [--epochs N] [--align_w W] [--limit N]
"""
import struct, glob, os, sys, random, argparse
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
DATA_DIRS = ['/root/autodl-tmp/distill_data_full_a', '/root/autodl-tmp/distill_data_full_b']
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='/root/autodl-tmp/distill_geom_out')
ap.add_argument('--epochs', type=int, default=4)
ap.add_argument('--align_w', type=float, default=1.0)
ap.add_argument('--limit', type=int, default=0, help='只用前 N 个样本 (0=全部)')
ap.add_argument('--lr', type=float, default=5e-5)
args = ap.parse_args()
OUT_DIR = args.out
EPOCHS = args.epochs
ALIGN_W = args.align_w
DATA_LIMIT = args.limit
LR = args.lr
T_LAYER = 58          # teacher 敏感层
S_LAYER = 22          # student 对应层 (58/64*24 ≈ 21.75)
PROJ_DIM = 256        # SVD 投影维度
MAX_SEQ = 512
BATCH = 4
SEED = 42
T_NEMBD = 5120        # teacher 32B n_embd
S_NEMBD = 896         # student 0.5B n_embd

# ---------- 数据解析 ----------
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
    # pieces 段
    if off < len(data):
        for j in range(ng):
            (pl,) = struct.unpack_from('<I', data, off); off += 4 + pl
    # 激活段: ng * T_NEMBD
    n_act = (len(data) - off) // 4
    acts = None
    if n_act >= ng * T_NEMBD:
        acts = np.frombuffer(data, dtype=np.float32, count=ng*T_NEMBD, offset=off).reshape(ng, T_NEMBD)
    return dict(prompt=prompt, gen=gen, acts=acts)

# ---------- SVD 子空间 ----------
def compute_proj(samples):
    """所有样本激活 → randomized SVD → 投影矩阵 P (T_NEMBD × PROJ_DIM)"""
    rows = []
    for s in samples:
        if s['acts'] is not None:
            rows.append(s['acts'])
    if not rows:
        return None
    A = np.concatenate(rows, axis=0)   # (N, 5120)
    A = A.astype(np.float32)
    A = A - A.mean(axis=0, keepdims=True)
    print(f'[svd] 激活矩阵 {A.shape}')
    # randomized SVD (Halko): 快 10 倍, 适用于大矩阵
    k = PROJ_DIM
    p = 10
    rng = np.random.default_rng(SEED)
    Omega = rng.standard_normal((A.shape[1], k + p)).astype(np.float32)
    Y = A @ Omega
    Q, _ = np.linalg.qr(Y)
    B = Q.T @ A
    U, S, Vt = np.linalg.svd(B, full_matrices=False)
    V = Vt[:k].T   # (5120, 256)
    ev = (S**2).sum()
    kept = (S[:k]**2).sum() / ev
    print(f'[svd] 前{k}主成分保留能量 {kept:.4f} (共{S.shape[0]}个奇异值)')
    return V.astype(np.float32)

# ---------- 训练 ----------
def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(STUDENT, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(STUDENT, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16)
    model.train(); model.cuda()
    n_vocab_s = model.config.vocab_size
    print(f'[model] student vocab={n_vocab_s} params={model.num_parameters()/1e6:.0f}M')

    files = []
    for d in DATA_DIRS:
        files += sorted(glob.glob(os.path.join(d, 'p*.bin')))
    if DATA_LIMIT > 0:
        files = files[:DATA_LIMIT]
    print(f'[data] {len(files)} files (limit={DATA_LIMIT})')
    samples = []
    for fp in files:
        d = load_dump(fp)
        if len(d['gen']) < 4 or d['acts'] is None:
            continue
        samples.append(d)
    print(f'[data] {len(samples)} samples with activations')
    P = compute_proj(samples)   # (5120, 256)
    if P is None:
        print('无激活数据, 退出'); return
    P_t = torch.from_numpy(P).cuda().float()
    # student 层22 线性投影头 (896 → 256), 独立 float32 计算对齐
    proj_head = torch.nn.Linear(S_NEMBD, PROJ_DIM, bias=False).float().cuda()
    torch.nn.init.orthogonal_(proj_head.weight)

    # hooks: 抓 student 层 S_LAYER 的输出激活
    act_cache = {}
    def make_hook(name):
        def hook(mod, inp, out):
            act_cache[name] = out[0] if isinstance(out, tuple) else out
        return hook
    layer_22 = None
    for name, mod in model.named_modules():
        if name == f'model.layers.{S_LAYER}':
            layer_22 = mod
            break
    if layer_22 is None:
        print(f'找不到层 {S_LAYER}, 退出'); return
    h = layer_22.register_forward_hook(make_hook('s22'))

    # 序列构建 (id 直连: teacher id < 151643 直接用)
    unk = 0
    V_ALIGN = 151643
    all_samples = []
    for d in samples:
        p = d['prompt']; g = d['gen']; acts = d['acts']
        seq = np.concatenate([p, g])[:MAX_SEQ]
        seq_s = np.array([int(t) if int(t) < V_ALIGN else unk for t in seq])
        n_p = len(p)
        ce = np.full(len(seq), -100, dtype=np.int64)
        for j in range(min(len(g), MAX_SEQ - n_p)):
            tid = int(g[j])
            if tid < V_ALIGN:
                ce[n_p + j] = tid
        n_g = min(len(g), MAX_SEQ - n_p)
        t_acts = acts[:n_g] if n_g else np.zeros((0, T_NEMBD))
        all_samples.append(dict(seq=torch.tensor(seq_s), ce=torch.tensor(ce),
                                t_acts=torch.from_numpy(t_acts.astype(np.float32)),
                                n_prompt=n_p))
    print(f'[data] 训练样本 {len(all_samples)}')

    opt = torch.optim.AdamW(list(model.parameters()) + list(proj_head.parameters()),
                            lr=LR, weight_decay=0.01)
    total = len(all_samples)
    for ep in range(EPOCHS):
        random.shuffle(all_samples)
        tot = 0.0; ns = 0
        for i in range(0, total, BATCH):
            batch = all_samples[i:i+BATCH]
            maxlen = max(s['seq'].shape[0] for s in batch)
            seqs = torch.stack([F.pad(s['seq'], (0, maxlen - s['seq'].shape[0])) for s in batch]).cuda()
            ces = torch.stack([F.pad(s['ce'], (0, maxlen - s['ce'].shape[0]), value=-100) for s in batch]).cuda()
            act_cache.clear()
            out = model(input_ids=seqs, labels=ces)
            ce_loss = out.loss
            # 激活对齐: student s22 激活 → proj_head → vs teacher P@a
            s_act = act_cache.get('s22')           # (B, L, 896)
            align_loss = torch.zeros(1, device='cuda')
            n_tok = 0
            if s_act is not None:
                for bi, s in enumerate(batch):
                    np_ = s['n_prompt']
                    n_g = s['t_acts'].shape[0]
                    if n_g == 0 or np_ + n_g > maxlen:
                        continue
                    sa = s_act[bi, np_:np_+n_g].float()          # (n_g, 896)
                    sa_p = proj_head(sa).float()                  # (n_g, 256)
                    ta = s['t_acts'].cuda().float()               # (n_g, 5120)
                    ta_p = (ta @ P_t).float()                      # (n_g, 256)
                    # 归一化 (余弦式对齐, 防 scale 学习)
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
