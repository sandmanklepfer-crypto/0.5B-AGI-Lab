#!/usr/bin/env python3
"""B方案训练: 多轮自修正 SFT (草稿->检查->终稿, CE only)
输出: /root/autodl-tmp/distill_3b_revise
"""
import json, random, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/autodl-tmp/qwen3b'
DATA = '/root/revise_data.jsonl'
OUT = '/root/autodl-tmp/distill_3b_revise'
EPOCHS = 2
LR = 1e-5
BATCH = 4
MAX_SEQ = 700

def build(tok, p, d, r, f):
    segs = [
        f'<|im_start|>user\n{p}<|im_end|>\n',
        f'<|im_start|>assistant\n{d}<|im_end|>\n',
        f'<|im_start|>user\n请检查上面的回答，找出错误和不足。<|im_end|>\n',
        f'<|im_start|>assistant\n{r}<|im_end|>\n',
        f'<|im_start|>user\n请基于检查结果，给出完整修正后的最终回答。<|im_end|>\n',
        f'<|im_start|>assistant\n{f}<|im_end|>',
    ]
    full = ''.join(segs)
    enc = tok(full, add_special_tokens=False, truncation=True, max_length=MAX_SEQ)
    ids = enc['input_ids']
    n_head = len(tok(segs[0], add_special_tokens=False)['input_ids'])
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
        ids, labels = build(tok, r['prompt'], r['draft'], r['revise'], r['final'])
        samples.append((ids, labels))
    print(f'[data] {len(samples)} samples', flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
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
    print('REVISE_TRAIN_DONE', flush=True)

if __name__ == '__main__':
    main()
