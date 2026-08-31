#!/usr/bin/env python3
"""3B中间体 -> 0.5B 桥接蒸馏数据 (A版 teacher: distill_3b_refine 粗->精行为)
输出: /root/bridge_data.jsonl {prompt, teacher_out}
teacher 输出带粗->精格式: <|draft|>...<|refine|>...
"""
import json, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/autodl-tmp/distill_3b_refine'
SRC = '/root/autodl-tmp/distill_prompts.txt'
OUT = '/root/bridge_data.jsonl'
N = 100

def gen(tok, model, text, max_new=280):
    ids = tok(text, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=True,
                             temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()

def main():
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    prompts = [l.strip() for l in open(SRC, encoding='utf-8') if l.strip()][:N]
    rows = []
    for i, p in enumerate(prompts):
        try:
            out = gen(tok, model, p)
            if len(out) < 15:
                continue
            rows.append({'prompt': p, 'teacher_out': out})
            print(f'[{len(rows)}] {p[:20]}... {len(out)}字', flush=True)
        except Exception as e:
            print('ERR', i, e, flush=True)
        if len(rows) >= N:
            break
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('BRIDGE_DATA_DONE', len(rows))

if __name__ == '__main__':
    main()
