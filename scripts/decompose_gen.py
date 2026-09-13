#!/usr/bin/env python3
"""decompose_gen.py — 断层补偿: 把难题拆成子步骤让 R1 重新生成
输出 /root/decomp_prompts.txt -> teacher_dump -> /root/v5_r1_decomp
"""
import os

def main():
    prompts = [l.strip() for l in open('/root/v5_prompts_all.txt', encoding='utf-8') if l.strip()]
    out = []
    for q in prompts:
        out.append(
            f"请把下面的问题分解成3-5个循序渐进的子步骤，然后逐步解答每一个子步骤，最后给出完整答案。\n"
            f"要求：步骤之间逻辑衔接清楚，每一步只做一件小事。\n\n问题：{q}")
    with open('/root/decomp_prompts.txt', 'w', encoding='utf-8') as f:
        f.write("\n".join(out) + "\n")
    print(f"[decomp] {len(out)} prompts -> /root/decomp_prompts.txt", flush=True)

if __name__ == '__main__':
    main()
