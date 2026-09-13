#!/usr/bin/env python3
"""C-Eval 20 题子集评估 (5科目×4题): 蒸馏版 vs 0.5B原版
用法: eval_ceval.py <model_path> <tag>
"""
import sys, re
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

SUBS = ['computer_network', 'chinese_language_and_literature', 'college_physics', 'law', 'college_economics']
Q_PER = 4

def load_items():
    items = []
    for sub in SUBS:
        df = pd.read_parquet(f'/tmp/{sub}.parquet')
        for _, row in df.head(Q_PER).iterrows():
            items.append({'sub': sub, 'q': row['question'],
                          'opts': [str(row[c]) for c in 'ABCD'], 'ans': str(row['answer'])})
    return items

def make_prompt(it):
    opts = it['opts']
    letters = 'ABCD'
    s = f"题目：{it['q']}\n"
    for i, o in enumerate(opts):
        if i < 4:
            s += f"{letters[i]}. {o}\n"
    s += "请直接回答答案字母(A/B/C/D)："
    return s

def main():
    model_path, tag = sys.argv[1], sys.argv[2]
    tok = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(model_path, trust_remote_code=True,
                                                 torch_dtype=torch.bfloat16).cuda().eval()
    items = load_items()
    correct = 0
    print(f'=== {tag} C-Eval 20题子集 ===')
    for i, it in enumerate(items):
        p = make_prompt(it)
        inputs = tok(p, return_tensors='pt').to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=6, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        ans_text = tok.decode(out[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
        m = re.search(r'[ABCD]', ans_text)
        pred = m.group(0) if m else '?'
        ans_letter = it['ans']
        ok = pred == ans_letter
        correct += ok
        print(f'[{i+1:02d}] {it["sub"]:32s} 预测={pred} 答案={ans_letter} {"✅" if ok else "❌"}')
    print(f'\n=== {tag}: {correct}/{len(items)} = {100.0*correct/len(items):.0f}% ===')

if __name__ == '__main__':
    main()
