#!/usr/bin/env python3
"""B方案数据v2: 复用A的粗稿, 只生成 检查+修正 (2轮), 60条
输入: /root/refine_data.jsonl (prompt+draft)  输出: /root/revise_data.jsonl
"""
import json, torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = '/root/autodl-tmp/qwen3b'
SRC = '/root/refine_data.jsonl'
OUT = '/root/revise_data.jsonl'
N = 60

def gen(tok, model, text, max_new, sys_p=None):
    t = (sys_p + '\n' + text) if sys_p else text
    ids = tok(t, return_tensors='pt').to('cuda')
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=True,
                             temperature=0.7, top_p=0.9, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=True).strip()

def main():
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    rows_src = [json.loads(l) for l in open(SRC, encoding='utf-8')][:N]
    rows = []
    for i, r in enumerate(rows_src):
        p, draft = r['prompt'], r['draft']
        try:
            revise = gen(tok, model, draft, 60, '请检查上面的回答，找出错误和不足：')
            final = gen(tok, model, revise, 220, '请基于检查结果，给出完整修正后的最终回答：')
            if len(revise) < 5 or len(final) < 10:
                continue
            rows.append({'prompt': p, 'draft': draft, 'revise': revise, 'final': final})
            print(f'[{len(rows)}] {p[:18]}... r{len(revise)} f{len(final)}', flush=True)
        except Exception as e:
            print('ERR', i, e, flush=True)
        if len(rows) >= N:
            break
    with open(OUT, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('REVISE_DATA_DONE', len(rows))

if __name__ == '__main__':
    main()
