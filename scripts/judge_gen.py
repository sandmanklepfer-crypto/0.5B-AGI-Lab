#!/usr/bin/env python3
"""judge_gen.py — 裁决器蒸馏数据生成
用 R1-32B 当 judge: 对 (问题, 候选答案[对/错]) 输出 评分+具体批评
候选: 对=从 v5 dump pieces 提取 R1 答案; 错=规则篡改(数字错/步骤跳)
输出: /root/judge_prompts.txt (teacher_dump 吃) -> /root/judge_r1/*.bin
"""
import struct, glob, json, os, random, re, sys
import numpy as np

random.seed(7)

def load_dump_pieces(path):
    with open(path, 'rb') as f:
        data = f.read()
    off = 0
    magic, k, np_, ng = struct.unpack_from('<IIII', data, off); off += 16
    prompt = np.frombuffer(data, dtype=np.int32, count=np_, offset=off); off += np_*4
    gen = np.frombuffer(data, dtype=np.int32, count=ng, offset=off); off += ng*4
    off += ng*k*8
    return prompt, gen

def decode_text(tokens):
    """用 Qwen tokenizer 从 token 序列恢复文本 (R1 同族)"""
    sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen05b')
    return tok.decode([int(t) for t in tokens if 0 <= int(t) < 151643], skip_special_tokens=True)

def make_wrong(prompt_text, right_text):
    """构造错误候选: 改数字 / 跳步骤 / 截断"""
    r = random.random()
    nums = re.findall(r'\d+', right_text)
    if r < 0.5 and nums:
        n0 = nums[0]
        wrong = int(n0) + random.choice([1, 2, -1, 3])
        return right_text.replace(n0, str(wrong), 1)  # 改错第一个数字
    elif r < 0.75 and len(right_text) > 60:
        return right_text[:len(right_text)//2] + "……（后续步骤省略）"  # 跳步骤
    else:
        return "答案是 42。"  # 无关答案

def main():
    # 加载 v5 难题 prompts + R1 答案
    prompts = [l.strip() for l in open('/root/v5_prompts_all.txt', encoding='utf-8') if l.strip()]
    bins = sorted(glob.glob('/root/v5_r1_hard/p*.bin'))
    print(f'prompts={len(prompts)} bins={len(bins)}', flush=True)
    judge_prompts = []
    meta = []
    for i, (q, f) in enumerate(zip(prompts[:40], bins[:40])):
        _, gen = load_dump_pieces(f)
        right = decode_text(gen)[:400]
        if len(right) < 20:
            continue
        wrong = make_wrong(q, right)
        for tag, cand in [("good", right), ("bad", wrong)]:
            judge_prompts.append(
                f"你是严格的评分员。请评价下面的回答，给出0-10分并指出具体问题。\n"
                f"问题：{q}\n回答：{cand}\n评价：")
            meta.append({"q": q, "tag": tag, "cand": cand[:400]})
    with open('/root/judge_prompts.txt', 'w', encoding='utf-8') as f:
        f.write("\n".join(judge_prompts) + "\n")
    json.dump(meta, open('/root/judge_meta.json', 'w'), ensure_ascii=False)
    print(f'judge prompts: {len(judge_prompts)} -> /root/judge_prompts.txt', flush=True)

if __name__ == '__main__':
    main()
