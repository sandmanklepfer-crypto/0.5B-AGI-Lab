#!/usr/bin/env python3
"""A方案训练: 迭代精化 SFT (粗稿->精稿 两阶段, CE only)
格式: <|im_start|>user\n{p}<|im_end|>\n<|draft|>{d}<|im_end|>\n<|refine|>{f}<|im_end|>
输出: /root/autodl-tmp/distill_3b_refine
"""
import json, random, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/autodl-tmp/qwen3b'
DATA = '/root/refine_data.jsonl'
OUT = '/root/autodl-tmp/distill_3b_refine'
EPOCHS = 2
LR = 1e-5
BATCH = 4
MAX_SEQ = 600

def build(tok, p, d, f):
    head = f'<|im_start|>user\n{p}<|im_end|>\n'
    draft_seg = f'<|draft|>{d}<|im_end|>\n'
    refine_seg = f'<|refine|>{f}<|im_end|>'
    full = head + draft_seg + refine_seg
    enc = tok(full, add_special_tokens=False, truncation=True, max_length=MAX_SEQ)
    ids = enc['input_ids']
    n_head = len(tok(head, add_special_tokens=False)['input_ids'])
    labels = ids.copy()
    for i in range(n_head):
        labels[i] = -100
    return ids, labels

def main():
    random.seed(42); torch.manual_seed(42)
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().train()
    rows = [json.loads(l) for l in open(DATA, encoding='utf-8') if l.strip()]
    samples = []
    for r in rows:
        ids, labels = build(tok, r['prompt'], r['draft'], r['final'])
        samples.append((ids, labels))
    print(f'[data] {len(samples)} samples', flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    import torch.nn.functional as F
    for ep in range(EPOCHS):
        random.shuffle(samples)
        tot = 0.0; n = 0
        for i in range(0, len(samples), BATCH):
            batch = samples[i:i+BATCH]
            maxlen = max(len(x[0]) for x in batch)
            ids = torch.full((len(batch), maxlen), tok.pad_token_id, dtype=torch.long).cuda()
            labels = torch.full((len(batch), maxlen), -100, dtype=torch.long).cuda()
            for bi, (x, y) in enumerate(batch):
                ids[bi, :len(x)] = torch.tensor(x, dtype=torch.long)
                labels[bi, :len(y)] = torch.tensor(y, dtype=torch.long)
            out = model(input_ids=ids, labels=labels)
            loss = out.loss
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            tot += loss.item(); n += 1
            if n % 10 == 0:
                print(f'[ep{ep} step{n}] loss={loss.item():.4f}', flush=True)
        print(f'[ep{ep}] avg={tot/max(n,1):.4f}', flush=True)
    import os
    os.makedirs(OUT, exist_ok=True)
    model.save_pretrained(OUT, safe_serialization=True)
    tok.save_pretrained(OUT)
    print(f'[save] {OUT}', flush=True)
    print('REFINE_TRAIN_DONE', flush=True)

if __name__ == '__main__':
    main()
