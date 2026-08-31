#!/usr/bin/env python3
"""C方案: 掩码扩散最小原型 (离散扩散/去噪训练, LLaDA风格)
- 正向: 随机掩码 30-70% token (mask_token_id 替换)
- 训练: CE loss 只算被掩码位置 (denoising 目标)
- 输出: /root/autodl-tmp/distill_3b_maskdiff (LoRA: /root/autodl-tmp/lora_3b_maskdiff)
"""
import json, random, math, torch, os
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model

MODEL = '/root/autodl-tmp/qwen3b'
DATA_FILES = ['/root/refine_data.jsonl']
OUT = '/root/autodl-tmp/lora_3b_maskdiff'
EPOCHS = 3
LR = 2e-4
BATCH = 6
MAX_SEQ = 256
MASK_MIN, MASK_MAX = 0.3, 0.7
LORA_R = 32
LORA_TARGETS = ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']

def collect_texts():
    texts = []
    for fp in DATA_FILES:
        for line in open(fp, encoding='utf-8'):
            try:
                r = json.loads(line)
                texts.append(r.get('final', ''))
                texts.append(r.get('prompt', ''))
            except Exception:
                pass
    # 蒸馏数据语料补充
    for line in open('/root/autodl-tmp/distill_prompts.txt', encoding='utf-8'):
        line = line.strip()
        if len(line) >= 20:
            texts.append(line)
    return [t for t in texts if len(t) >= 10]

def main():
    random.seed(42); torch.manual_seed(42)
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    mask_id = tok.pad_token_id if tok.pad_token_id is not None else 151643
    model = AutoModelForCausalLM.from_pretrained(MODEL, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().train()
    lora_cfg = LoraConfig(r=LORA_R, lora_alpha=LORA_R*2, lora_dropout=0.05,
                          target_modules=LORA_TARGETS, task_type='CAUSAL_LM', bias='none')
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()
    texts = collect_texts()
    print(f'[data] {len(texts)} texts', flush=True)
    # 预 tokenize
    encs = []
    for t in texts:
        ids = tok(t, add_special_tokens=False, truncation=True, max_length=MAX_SEQ)['input_ids']
        if len(ids) >= 12:
            encs.append(ids)
    print(f'[data] {len(encs)} 有效样本', flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    for ep in range(EPOCHS):
        random.shuffle(encs)
        tot = 0.0; n = 0
        for i in range(0, len(encs), BATCH):
            batch = encs[i:i+BATCH]
            maxlen = max(len(x) for x in batch)
            ids = torch.full((len(batch), maxlen), tok.pad_token_id, dtype=torch.long).cuda()
            labels = torch.full((len(batch), maxlen), -100, dtype=torch.long).cuda()
            mask = torch.zeros((len(batch), maxlen), dtype=torch.bool).cuda()
            for bi, x in enumerate(batch):
                ids[bi, :len(x)] = torch.tensor(x, dtype=torch.long)
                frac = random.uniform(MASK_MIN, MASK_MAX)
                n_mask = max(1, int(len(x) * frac))
                idx = random.sample(range(len(x)), n_mask)
                for j in idx:
                    labels[bi, j] = x[j]
                    ids[bi, j] = mask_id
                    mask[bi, j] = True
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
    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print(f'[save] {OUT}', flush=True)
    print('MASKDIFF_TRAIN_DONE', flush=True)

if __name__ == '__main__':
    main()
