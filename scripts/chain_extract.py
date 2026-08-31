#!/usr/bin/env python3
"""chain_extract.py — R1 顶级推理链压缩成短链
从 v5_r1_hard 的 R1 难题生成中, 提取步骤 -> 压缩成 5 步关键短链 (每步<=15字)
输出: /root/chain_data.jsonl [{q, chain}]
"""
import struct, glob, sys, json, re
import numpy as np
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoTokenizer

N_VOCAB = 151643

def load_gen(path):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    return prompt, gen

def decode(tokens, tok):
    return tok.decode([int(t) for t in tokens if 0 <= int(t) < N_VOCAB], skip_special_tokens=True)

def compress_chain(text, max_steps=5, max_len=15):
    """提取步骤行 -> 压缩成 max_steps 步短链 (过滤思考废话)"""
    BAD_PREFIX = ("好的", "嗯", "首先我需要", "我要", "让我", "这里", "那么我", "现在我", "我得先", "这", "很")
    GOOD_PREFIX = ("计算", "代入", "根据", "因此", "所以", "步骤", "求", "设", "令", "得到", "化简", "两边", "利用", "由", "因为", "结果", "答案")
    lines = [l.strip() for l in text.split('\n')]
    steps = []
    # 1) 步骤N 行
    for l in lines:
        m = re.search(r'\*?\s*步骤\s*(\d+)[:：]\s*(.+)', l)
        if m:
            s = m.group(2).strip().replace('*', '').replace('**', '')[:max_len]
            if s and s not in steps and not s.startswith(BAD_PREFIX):
                steps.append(s)
    # 2) 关键动作句 (计算/代入/根据/因此/所以/令/化简/利用...)
    if len(steps) < max_steps:
        sents = [s.strip().replace('*','')[:max_len] for s in re.split(r'[。；\n]', text)]
        for s in sents:
            if s.startswith(GOOD_PREFIX) and s not in steps:
                steps.append(s)
    # 3) 含数值/等号的句 (计算痕迹)
    if len(steps) < max_steps:
        for s in sents:
            if re.search(r'[=＝]|\d', s) and len(s) > 4 and s not in steps and not s.startswith(BAD_PREFIX):
                steps.append(s)
    return steps[:max_steps]

def main():
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen05b')
    prompts = [l.strip() for l in open('/root/v5_prompts_all.txt', encoding='utf-8') if l.strip()]
    files = sorted(glob.glob('/root/v5_r1_hard/p*.bin'))
    rows = []
    for q, f in zip(prompts, files):
        _, gen = load_gen(f)
        text = decode(gen, tok)
        chain = compress_chain(text)
        if len(chain) >= 3:
            rows.append({"q": q[:60], "chain": chain})
    with open('/root/chain_data.jsonl', 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[chain] {len(rows)} rows", flush=True)
    for r in rows[:3]:
        print(f"  Q: {r['q'][:30]}", flush=True)
        print(f"  CHAIN: {' | '.join(r['chain'])}", flush=True)

if __name__ == '__main__':
    main()
