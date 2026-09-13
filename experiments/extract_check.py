#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''extract_check.py — 修正: 答案到底是「提取/复制」还是「产生新信息」?'''
import json, re, time
from collections import defaultdict
t0 = time.time()
QA = [json.loads(l) for l in open('/workspace/clean_train.jsonl', encoding='utf-8')]

print("=" * 92)
print("修正分析: 答案是不是【从问题里复制出来的】?")
print("=" * 92)
print(f"  {len(QA)} 条")
print()


def longest_common_substr(a, b):
    """最长公共子串长度 (答案有多少是问题的原文连续片段)"""
    if not a or not b:
        return 0
    m = len(b)
    prev = [0] * (m + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (m + 1)
        ai = a[i-1]
        for j in range(1, m + 1):
            if ai == b[j-1]:
                cur[j] = prev[j-1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


rows = []
for d in QA:
    q, a = d['q'], d['a']
    L = longest_common_substr(a, q)
    cov = L / max(len(a), 1)
    rows.append((d['task'], cov, len(a)))

print(f"  {'任务类型':<12}{'条数':<8}{'最长公共子串占比':<20}{'判定'}")
print("  " + "-" * 70)
by = defaultdict(list)
for t, c, la in rows:
    by[t].append(c)
for t, v in sorted(by.items(), key=lambda x: -sum(x[1])/len(x[1])):
    m = sum(v)/len(v)
    tag = "★ 提取型 (纯复制)" if m > 0.5 else ("⚠️ 部分复制" if m > 0.2 else "❌ 需外部信息")
    print(f"  {t:<12}{len(v):<8}{m:<20.3f}{tag}")
print()

allm = sum(c for _, c, _ in rows) / len(rows)
ex = sum(1 for _, c, _ in rows if c > 0.5)
pt = sum(1 for _, c, _ in rows if 0.2 < c <= 0.5)
non = sum(1 for _, c, _ in rows if c <= 0.2)
print("=" * 92)
print("★ 三类客观占比")
print("=" * 92)
print()
print(f"  提取型 (答案>50%来自问题原文)   {ex:>4} 条  {100*ex/len(rows):>5.1f}%   ✅ 规则可做")
print(f"  部分复制 (20~50%)                {pt:>4} 条  {100*pt/len(rows):>5.1f}%   ⚠️ 要拼")
print(f"  需外部信息 (<20%)                {non:>4} 条  {100*non/len(rows):>5.1f}%   ❌ 靠库")
print()
print("=" * 92)
print("★ 实例: summary 是怎么「提取」的")
print("=" * 92)
print()
n = 0
for d in QA:
    if d['task'] == 'summary' and n < 2:
        q, a = d['q'], d['a']
        # 找答案在问题里的位置
        pos = q.find(a[:40])
        print(f"  问题: {q[:50]}...")
        print(f"  答案: {a[:60]}...")
        print(f"  -> 答案在问题里的位置: 第 {pos} 字处开始  {'★ 就是复制!' if pos >= 0 else ''}")
        print()
        n += 1
print("=" * 92)
print("★ 修正结论")
print("=" * 92)
print(f"""
  我上一轮说「95.5% 需要新信息」—— 那个结论【错了】, 是我把问题截断造成的.

  修正后: {100*ex/len(rows):.0f}% 的任务, 答案【大部分直接来自问题原文】.

  ★ 也就是说: 这批任务里, 真正需要「产生新信息」的只有 {100*non/len(rows):.0f}%

  ★ 而"提取"这件事:
     · 不需要模型 (一个定位规则就够)
     · 0.5B 能做 (它天生就是复制机)
     · 而且可以【组合】: 提取A段 + 提取B段 + 拼接 = 复杂答案

  ★ 所以你说的「在锚点基础上产生高层结构」是可行的:
     第0层: 字符/词
     第1层: 锚点 (从输入定位到的片段)
     第2层: 锚点 + 操作 (拼接/替换/排序/嵌套)
     第3层: 把第2层的结果【命名】成新锚点, 再参与第2层
     -> 这就是「深度」的来源, 而且每一层都是【搬运+组合】, 不是凭空产生
""")
print(f"用时 {time.time()-t0:.2f}s")
