#!/usr/bin/env python3
"""3B中间体 -> 0.5B 桥接蒸馏 (v4c 同款: 0.5B 基座全参 SFT, CE only)
数据: /root/bridge_data.jsonl {prompt, teacher_out}  (teacher=distill_3b_refine 粗->精)
输出: /root/autodl-tmp/distill_05b_bridge
"""
import json, random, torch, os
from transformers import AutoModelForCausalLM, AutoTokenizer

STUDENT = '/root/autodl-tmp/qwen05b'
DATA_FILES = ['/root/refine_data.jsonl', '/root/bridge_agent.jsonl']
OUT = '/root/autodl-tmp/distill_05b_bridge'
EPOCHS = 3
LR = 1e-5
BATCH = 8
MAX_SEQ = 600

def build(tok, p, out):
    full = f'<|im_start|>user\n{p}<|im_end|>\n<|im_start|>assistant\n{out}<|im_end|>'
    enc = tok(full, add_special_tokens=False, truncation=True, max_length=MAX_SEQ)
    ids = enc['input_ids']
    n_head = len(tok(f'<|im_start|>user\n{p}<|im_end|>\n', add_special_tokens=False)['input_ids'])
    labels = ids.copy()
    for i in range(n_head):
        labels[i] = -100
    return ids, labels

def main():
    random.seed(42); torch.manual_seed(42)
    tok = AutoTokenizer.from_pretrained(STUDENT, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(STUDENT, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().train()
    rows = []
    for fp in DATA_FILES:
        for line in open(fp, encoding='utf-8'):
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    samples = []
    for r in rows:
        out = f'<|draft|>{r["draft"]}<|end|>\n<|refine|>{r["final"]}<|end|>'
        ids, labels = build(tok, r['prompt'], out)
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
            if n % 20 == 0:
                print(f'[ep{ep} step{n}] loss={loss.item():.4f}', flush=True)
        print(f'[ep{ep}] avg={tot/max(n,1):.4f}', flush=True)
    os.makedirs(OUT, exist_ok=True)
    model.save_pretrained(OUT, safe_serialization=True)
    tok.save_pretrained(OUT)
    print(f'[save] {OUT}', flush=True)
    print('BRIDGE_TRAIN_DONE', flush=True)

if __name__ == '__main__':
    main()
