#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''hanzi_num.py — 给汉语套数字, 用数字拽着汉语走, 能不能提速?'''
import time, random
from collections import Counter, defaultdict
t0 = time.time()

L = []; chars = Counter(); by_len = defaultdict(Counter)
suf = defaultdict(Counter); suf2 = defaultdict(Counter)
head = Counter(); tail = Counter()
CJK = lambda c: '\u4e00' <= c <= '\u9fff'
STEP = 3
with open('/workspace/jieba-0.42.1/jieba/dict.txt', encoding='utf-8', errors='ignore') as f:
    for i, line in enumerate(f):
        if i % STEP:
            continue
        p = line.split()
        if len(p) < 3:
            continue
        w = p[0]
        if not (2 <= len(w) <= 4):
            continue
        ok = True
        for c in w:
            if not CJK(c):
                ok = False; break
        if not ok:
            continue
        try:
            fr = int(p[1])
        except ValueError:
            continue
        pos = p[2]
        L.append((w, fr, pos))
        for c in w:
            chars[c] += 1
        by_len[len(w)][pos] += 1
        suf[w[-1]][pos] += 1
        suf2[w[-2:]][pos] += 1
        head[w[0]] += 1; tail[w[-1]] += 1

N = len(L)
print("=" * 88)
print("给汉语套一层数字, 用数字拽着汉语走 —— 能不能提速?")
print("=" * 88)
print(f"  真实数据: {N:,} 个中文词 (jieba 词典抽样 1/{STEP}),  用到 {len(chars):,} 个不同汉字")
print(f"  每个字平均被用在 {sum(chars.values())/len(chars):.1f} 个词里")
print()
print("=" * 88)
print("三种「套数字」的方式")
print("=" * 88)
print()
print(f"  {'方式':<28}{'词变成什么':<30}{'里面有什么'}")
print("  " + "-" * 86)
print(f"  {'1 编号型 (随便给号)':<28}{'0,1,2,...,N-1':<30}{'零结构'}")
print(f"  {'2 统计型 (数出来的)':<28}{'(词频, 字数)':<30}{'统计结构'}")
print(f"  {'3 结构型 (拆开编码)':<28}{'(字1,字2,...,后缀)':<30}{'★ 代数结构(能生成)'}")
print()

guess2 = [by_len[len(w)].most_common(1)[0][0] for w, _, _ in L]
acc2 = sum(1 for (w, _, pos), g in zip(L, guess2) if pos == g) / N
guess3 = [suf[w[-1]].most_common(1)[0][0] for w, _, _ in L]
acc3 = sum(1 for (w, _, pos), g in zip(L, guess3) if pos == g) / N
guess4 = [suf2[w[-2:]].most_common(1)[0][0] for w, _, _ in L]
acc4 = sum(1 for (w, _, pos), g in zip(L, guess4) if pos == g) / N

print("=" * 88)
print("真实任务: 判断词性 (名/动/形/...)  —— 存储 vs 准确率")
print("=" * 88)
print()
print(f"  {'方式':<30}{'要存多少条':<16}{'压缩':<12}{'准确率'}")
print("  " + "-" * 78)
print(f"  {'1 编号型 (查表)':<30}{N:<16,}{'1.0x':<12}{'1.000'}")
print(f"  {'2 统计型 (按字数)':<30}{len(by_len):<16,}{f'{N/len(by_len):.0f}x':<12}{acc2:.3f}")
print(f"  {'3 结构型 (末字)':<30}{len(suf):<16,}{f'{N/len(suf):.0f}x':<12}{acc3:.3f}")
print(f"  {'3+ 结构型 (末两字)':<30}{len(suf2):<16,}{f'{N/len(suf2):.0f}x':<12}{acc4:.3f}")
print()

print("=" * 88)
print("★ 用数字能不能「算」出像词的东西? (生成 vs 检索)")
print("=" * 88)
print()
print("  汉字的两个数字: 「爱当开头」/「爱当结尾」")
for c, cnt in tail.most_common(4):
    print(f"     「{c}」结尾 {cnt:,} 次, 开头 {head[c]:,} 次")
print()
random.seed(0)
H = [c for c, _ in head.most_common(400)]
T = [c for c, _ in tail.most_common(400)]
gen = set()
for _ in range(3000):
    gen.add(random.choice(H) + random.choice(T))
real2 = set(w for w, _, _ in L if len(w) == 2)
hit = len(gen & real2)
print(f"  用两个字池拼了 {len(gen):,} 个二字组合, 其中 {hit:,} 个是真词")
print(f"     像词率 = {hit/len(gen):.1%}")
print()

print("=" * 88)
print("结论")
print("=" * 88)
print(f"""
  ★ 套数字【本身不提速】—— 提速来自数字里【有没有可生成的结构】

    方式1 编号型: 只换名字     -> 一条不少存 (1.0x, 准确 1.000)
    方式2 统计型: 数出来的     -> 压 {N/len(by_len):.0f} 倍,  准确率掉到 {acc2:.3f}
    方式3 结构型: 拆后缀数字    -> 压 {N/len(suf2):.0f} 倍,  准确率还有 {acc4:.3f}

  ★ 汉语的红利: 词不是原子, 是【字的组合】
     {len(chars):,} 个不同的字 -> 拼出 {N:,} 个词 (放大 {N/len(chars):.1f} 倍)
     所以数字要挂在【字】上, 不挂在【词】上 —— 这就是压缩的来源

  ★ 而且结构【可算术化】: 用「开头/结尾偏好」拼组合, 像词率 {hit/len(gen):.1%}
     说明汉语的构词结构, 能被写成数字运算

  ★ 一句话: 检索 {N:,} 条词性  ->  用 {len(suf2):,} 条后缀规则算
     词表越大, 差距越大 (规则数不随词数增长)
""")
print(f"用时 {time.time()-t0:.2f}s")
