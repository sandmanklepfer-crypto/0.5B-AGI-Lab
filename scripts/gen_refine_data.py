#!/usr/bin/env python3
"""A方案: 粗稿-精稿数据生成 (3B基座自举: 一句话粗稿 vs 详细精稿)
输出: /root/refine_data.jsonl {prompt, draft, final}
"""
import json, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/autodl-tmp/qwen3b'
SRC = '/root/autodl-tmp/distill_prompts.txt'
OUT = '/root/refine_data.jsonl'
N = 120

def gen(tok, model, text, max_new, sys_p):
    t = sys_p + '\n' + text
    ids = tok(t, return_tensors='pt').to('cuda')
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
            draft = gen(tok, model, p, 50, '请用一句话简要回答，只给核心要点。')
            final = gen(tok, model, p, 260, '请详细完整地回答这个问题，包含清晰的推理步骤和完整结构，最后给出明确结论。')
            if len(draft) < 5 or len(final) < len(draft):
                continue
            rows.append({'prompt': p, 'draft': draft, 'final': final})
            print(f'[{len(rows)}] {p[:24]}... draft{len(draft)} final{len(final)}', flush=True)
        except Exception as e:
            print('ERR', i, e, flush=True)
        if len(rows) >= N:
            break
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('REFINE_DATA_DONE', len(rows))

if __name__ == '__main__':
    main()
