#!/usr/bin/env python3
"""32B teacher → 0.5B student 全参蒸馏训练
数据: teacher_dump 输出 (magic 0x54444344; prompt/gen tokens + top-k logits)
loss: CE(teacher tokens) + λ·KL(teacher top-k softmax(T) || student top-k softmax(T))
"""
import struct, glob, os, sys, random
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
DATA_DIRS = ['/root/autodl-tmp/distill_data_a', '/root/autodl-tmp/distill_data_b']
VOCAB_TXT = '/tmp/teacher_vocab.txt'
OUT_DIR = '/root/autodl-tmp/distill_out'
K = 64
T = 2.0
KL_W = 1.0
MAX_SEQ = 512
EPOCHS = 3
LR = 5e-5
BATCH = 6
SEED = 42

# ---------- teacher vocab 映射 ----------
def build_id_map(vocab_txt, tok):
    """teacher_id -> student_id (或 -1). 基于 piece 文本匹配."""
    idmap = {}
    n_ok = 0; n_tot = 0
    with open(vocab_txt, 'r', errors='replace') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line.strip():
                continue
            parts = line.split('\t', 2)
            if len(parts) < 3:
                continue
            try:
                tid = int(parts[0])
            except ValueError:
                continue
            special, piece = parts[1], parts[2]
            # 反转义
            piece = piece.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace('\\\\', '\\')
            n_tot += 1
            sid = -1
            try:
                sid = tok.convert_tokens_to_ids(piece)
                if sid is None or (isinstance(sid, list) and len(sid) != 1):
                    sid = -1
                elif isinstance(sid, list):
                    sid = sid[0]
            except Exception:
                sid = -1
            if sid is not None and sid >= 0:
                n_ok += 1
            else:
                sid = -1
            idmap[tid] = sid
    print(f'[vocab] teacher {n_tot} tokens, 映射成功 {n_ok} ({100.0*n_ok/max(n_tot,1):.1f}%)')
    return idmap

# ---------- 数据解析 ----------
def load_dump(path):
    """返回 dict: prompt(ndarray), gen, top_ids(ng,K), top_logits(ng,K), has_piece"""
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    assert magic == 0x54444344, f'bad magic {path}'
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    top_ids = np.frombuffer(data, dtype=np.uint32, count=ng*k, offset=off); off += ng*k*4
    top_logits = np.frombuffer(data, dtype=np.float32, count=ng*k, offset=off); off += ng*k*4
    # 可选 piece 段
    pieces = []
    if off < len(data):
        try:
            for j in range(ng):
                (pl,) = struct.unpack_from('<I', data, off); off += 4
                pieces.append(data[off:off+pl].decode('utf-8', 'replace')); off += pl
        except Exception:
            pieces = []
    return dict(prompt=prompt, gen=gen, top_ids=top_ids.reshape(ng, k),
                top_logits=top_logits.reshape(ng, k), pieces=pieces)

def load_all():
    files = []
    for d in DATA_DIRS:
        files += sorted(glob.glob(os.path.join(d, 'p*.bin')))
    print(f'[data] {len(files)} samples')
    return files

# ---------- 训练 ----------
def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(STUDENT, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(STUDENT, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16)
    model.train()
    model.cuda()
    n_vocab_s = model.config.vocab_size
    print(f'[model] student vocab={n_vocab_s} params={model.num_parameters()/1e6:.0f}M')
    idmap = build_id_map(VOCAB_TXT, tok)
    files = load_all()

    # 预处理所有样本为张量列表
    samples = []
    unk = tok.unk_token_id if tok.unk_token_id is not None else 0
    for fp in files:
        d = load_dump(fp)
        p = d['prompt']; g = d['gen']; ti = d['top_ids']; tl = d['top_logits']
        if len(g) < 4:
            continue
        # 序列: prompt + gen (映射到 student vocab, 无效替换 unk)
        seq = np.concatenate([p, g])[:MAX_SEQ]
        seq_s = np.array([idmap.get(int(t), -1) for t in seq])
        seq_s[seq_s < 0] = unk
        n_p = len(p)
        # CE 标签: gen 部分 (只保留映射成功的)
        ce_label = np.full(len(seq), -100, dtype=np.int64)
        for j in range(len(g)):
            pos = n_p + j
            if pos >= MAX_SEQ: break
            sid = idmap.get(int(g[j]), -1)
            if sid >= 0:
                ce_label[pos] = sid
        # KL 目标: teacher top-k (映射到 student id)
        n_kl = min(len(g), MAX_SEQ - n_p)
        kl_ids = np.full((n_kl, K), -1, dtype=np.int64)
        kl_logits = np.zeros((n_kl, K), dtype=np.float32)
        for j in range(n_kl):
            for kk in range(K):
                tid = int(ti[j, kk])
                sid = idmap.get(tid, -1)
                if sid >= 0:
                    kl_ids[j, kk] = sid
                    kl_logits[j, kk] = tl[j, kk]
        samples.append(dict(seq=torch.tensor(seq_s), ce=torch.tensor(ce_label),
                            kl_ids=torch.tensor(kl_ids), kl_logits=torch.tensor(kl_logits),
                            n_prompt=n_p))
    print(f'[data] 有效样本 {len(samples)}')

    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total = len(samples)

    def masked_softmax(x, mask):
        x = x.masked_fill(~mask, -1e9)
        x = x - x.max(dim=-1, keepdim=True).values
        e = torch.exp(x) * mask.float()
        return e / (e.sum(-1, keepdim=True) + 1e-9)

    for ep in range(EPOCHS):
        random.shuffle(samples)
        tot_loss = 0.0; n_step = 0
        for i in range(0, total, BATCH):
            batch = samples[i:i+BATCH]
            maxlen = max(s['seq'].shape[0] for s in batch)
            seqs = torch.stack([F.pad(s['seq'], (0, maxlen - s['seq'].shape[0])) for s in batch]).cuda()
            ces = torch.stack([F.pad(s['ce'], (0, maxlen - s['ce'].shape[0]), value=-100) for s in batch]).cuda()
            out = model(input_ids=seqs, labels=ces)
            ce_loss = out.loss
            logits = out.logits  # (B, L, V)
            # KL loss: 每个样本的 gen 位置, teacher top-k vs student
            kl_loss = torch.zeros(1, device='cuda')
            n_kl_tok = 0
            for bi, s in enumerate(batch):
                np_ = s['n_prompt']
                n_kl = s['kl_ids'].shape[0]
                if n_kl == 0 or np_ + n_kl > maxlen:
                    continue
                kl_ids = s['kl_ids'].cuda()       # (n_kl, K)
                kl_lg = s['kl_logits'].cuda()     # (n_kl, K)
                valid = kl_ids >= 0               # (n_kl, K)
                st = logits[bi, np_:np_+n_kl]     # (n_kl, V)
                st_g = torch.gather(st, 1, kl_ids.clamp(min=0))  # (n_kl, K)
                te = kl_lg / T
                st_T = st_g / T
                p_t = masked_softmax(te, valid)
                q_s = masked_softmax(st_T, valid)
                lp = torch.log(p_t.clamp(min=1e-9))
                lq = torch.log(q_s.clamp(min=1e-9))
                kl_row = (p_t * (lp - lq) * valid.float()).sum(-1)
                row_valid = valid.any(dim=-1)
                if row_valid.any():
                    kl_loss = kl_loss + kl_row[row_valid].mean()
                    n_kl_tok += int(row_valid.sum().item())
            kl_loss = kl_loss / max(n_kl_tok, 1)
            loss = ce_loss + KL_W * kl_loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot_loss += loss.item(); n_step += 1
            if n_step % 20 == 0:
                print(f'[ep{ep} step{n_step}/{total//BATCH}] loss={loss.item():.3f} ce={ce_loss.item():.3f} kl={kl_loss.item():.3f}')
        print(f'[ep{ep}] avg loss={tot_loss/max(n_step,1):.3f}')
    os.makedirs(OUT_DIR, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tok.save_pretrained(OUT_DIR)
    print(f'[save] {OUT_DIR}')

if __name__ == '__main__':
    main()
