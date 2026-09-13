#!/usr/bin/env python3
"""1.5B LoRA 蒸馏: 冻结基座保深度, LoRA 学 R1-32B 对话格式 (v4c 效果)
数据: distill_data_full_a/b (teacher top-k logits), loss: CE + KL(T=2)
输出: /root/autodl-tmp/qwen15b_v4c (合并后完整模型)
"""
import struct, glob, os, sys, random
import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

STUDENT = '/root/qwen15b'
DATA_DIRS = ['/root/autodl-tmp/distill_data_full_a', '/root/autodl-tmp/distill_data_full_b']
VOCAB_TXT = '/tmp/teacher_vocab.txt'
OUT_DIR = '/root/autodl-tmp/qwen15b_v4c'
K = 64
T = 2.0
KL_W = 0.5
MAX_SEQ = 512
EPOCHS = 2
LR = 1e-4
BATCH = 4
SEED = 42
LORA_R = 32
LORA_ALPHA = 64
LORA_DROPOUT = 0.05
LORA_TARGETS = ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']

def build_id_map(vocab_txt, tok):
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
            piece = piece.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r').replace('\\\\', '\\')
            n_tot += 1
            sid = -1
            try:
                sid = tok.convert_tokens_to_ids(piece)
                if isinstance(sid, list):
                    sid = sid[0] if len(sid) == 1 else -1
            except Exception:
                sid = -1
            if sid is not None and sid >= 0:
                n_ok += 1
            else:
                sid = -1
            idmap[tid] = sid
    print(f'[vocab] teacher {n_tot} tokens, 映射成功 {n_ok} ({100.0*n_ok/max(n_tot,1):.1f}%)', flush=True)
    return idmap

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
    return dict(prompt=prompt, gen=gen, top_ids=top_ids.reshape(ng, k), top_logits=top_logits.reshape(ng, k))

def load_all():
    files = []
    for d in DATA_DIRS:
        files += sorted(glob.glob(os.path.join(d, 'p*.bin')))
    print(f'[data] {len(files)} samples', flush=True)
    return files

def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    tok = AutoTokenizer.from_pretrained(STUDENT, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(STUDENT, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16)
    model.train(); model.cuda()
    print(f'[model] base params={model.num_parameters()/1e6:.0f}M', flush=True)
    lora_cfg = LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT,
                          target_modules=LORA_TARGETS, task_type='CAUSAL_LM',
                          bias='none')
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    idmap = build_id_map(VOCAB_TXT, tok)
    files = load_all()

    samples = []
    unk = tok.unk_token_id if tok.unk_token_id is not None else 0
    for fp in files:
        d = load_dump(fp)
        p = d['prompt']; g = d['gen']; ti = d['top_ids']; tl = d['top_logits']
        if len(g) < 4:
            continue
        seq = np.concatenate([p, g])[:MAX_SEQ]
        seq_s = np.array([idmap.get(int(t), -1) for t in seq])
        seq_s[seq_s < 0] = unk
        n_p = len(p)
        ce_label = np.full(len(seq), -100, dtype=np.int64)
        for j in range(len(g)):
            pos = n_p + j
            if pos >= MAX_SEQ: break
            sid = idmap.get(int(g[j]), -1)
            if sid >= 0:
                ce_label[pos] = sid
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
    print(f'[data] 有效样本 {len(samples)}', flush=True)

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
            logits = out.logits
            kl_loss = torch.zeros(1, device='cuda')
            n_kl_tok = 0
            for bi, s in enumerate(batch):
                np_ = s['n_prompt']
                n_kl = s['kl_ids'].shape[0]
                if n_kl == 0 or np_ + n_kl > maxlen:
                    continue
                kl_ids = s['kl_ids'].cuda()
                kl_lg = s['kl_logits'].cuda()
                valid = kl_ids >= 0
                st = logits[bi, np_:np_+n_kl]
                st_g = torch.gather(st, 1, kl_ids.clamp(min=0))
                te = kl_lg / T
                st_T = st_g / T
                p_t = masked_softmax(te, valid)
                q_s = masked_softmax(st_T, valid)
                kl_ = (p_t * (p_t.log() - q_s.log())).sum(-1)
                n_valid = valid.sum(-1).clamp(min=1).float()
                kl_loss = kl_loss + (kl_ / n_valid).sum()
                n_kl_tok += n_kl
            if n_kl_tok > 0:
                kl_loss = kl_loss / n_kl_tok
            loss = ce_loss + KL_W * kl_loss
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot_loss += loss.item()
            n_step += 1
            if n_step % 20 == 0 or i + BATCH >= total:
                print(f'[ep{ep} step{n_step}/{total//BATCH+1}] loss={loss.item():.4f} ce={ce_loss.item():.4f} kl={kl_loss.item():.4f}', flush=True)
        print(f'[ep{ep}] avg loss={tot_loss/max(n_step,1):.4f}', flush=True)

    print('[merge] 合并 LoRA 到基座...', flush=True)
    model = model.merge_and_unload()
    os.makedirs(OUT_DIR, exist_ok=True)
    model.save_pretrained(OUT_DIR, safe_serialization=True)
    tok.save_pretrained(OUT_DIR)
    print(f'[save] {OUT_DIR}', flush=True)
    print('ALL_DONE', flush=True)

if __name__ == '__main__':
    main()
