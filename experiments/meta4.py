#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''meta4.py — 最终裁决: 区分「搬运型」和「重组型」任务 (客观可算)
   关键: 上一轮我用「新字符比例低」当"简单", 这是错的!
        新字符比例低 = 答案用问题里的字重新排列 = 重组型 = 0.5B 最不会的!
   正确指标: 覆盖度(答案的字有多少来自问题) x 顺序保持度(是否保持原顺序)
'''
import json, time
from collections import Counter
t0 = time.time()

QA = []
with open('/workspace/clean_train.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        QA.append((d['task'], d['q'], d['a']))

print("=" * 94)
print("最终裁决: 「搬运型」还是「重组型」? (这是决定 0.5B 能不能做的关键)")
print("=" * 94)
print(f"  {len(QA)} 条真实 QA")
print()


def lcs(a, b):
    a = a[:40]; b = b[:80]
    """最长公共子序列长度 (答案是否保持问题里的字的顺序)"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i-1]
        for j in range(1, len(b) + 1):
            cur[j] = prev[j-1] + 1 if ai == b[j-1] else max(prev[j], cur[j-1])
        prev = cur
    return prev[-1]


rows = []
for t, q, a in QA:
    cov = sum((Counter(a) & Counter(q)).values()) / max(len(a), 1)     # 覆盖度
    order = lcs(a, q) / max(len(a), 1)                                 # 顺序保持度
    rows.append((t, cov, order, len(a)))

print(f"  {'任务类型':<12}{'条数':<8}{'覆盖度':<12}{'顺序保持度':<14}{'判定'}")
print("  " + "-" * 74)
by = {}
for t, cov, order, la in rows:
    by.setdefault(t, []).append((cov, order))
for t, v in sorted(by.items(), key=lambda x: -sum(o for _, o in x[1])/len(x[1])):
    mc = sum(c for c, _ in v) / len(v)
    mo = sum(o for _, o in v) / len(v)
    if mo > 0.6:
        tag = "★ 搬运型 (0.5B 能做)"
    elif mc > 0.6:
        tag = "⚠️ 重组型 (0.5B 做不到)"
    else:
        tag = "❌ 需新信息"
    print(f"  {t:<12}{len(v):<8}{mc:<12.3f}{mo:<14.3f}{tag}")
print()

# 全体统计
mc = sum(c for _, c, _, _ in rows) / len(rows)
mo = sum(o for _, _, o, _ in rows) / len(rows)
print(f"  全体: 覆盖度 {mc:.3f},  顺序保持度 {mo:.3f}")
print()

print("=" * 94)
print("★ 三类任务客观占比")
print("=" * 94)
print()
c1 = sum(1 for _, c, o, _ in rows if o > 0.6)
c2 = sum(1 for _, c, o, _ in rows if o <= 0.6 and c > 0.6)
c3 = sum(1 for _, c, o, _ in rows if c <= 0.6)
print(f"  搬运型 (顺序保持>0.6, 0.5B能做)      {c1:>4} 条  {100*c1/len(rows):>5.1f}%")
print(f"  重组型 (覆盖高但顺序乱, 0.5B做不到)   {c2:>4} 条  {100*c2/len(rows):>5.1f}%")
print(f"  需新信息 (覆盖<0.6)                  {c3:>4} 条  {100*c3/len(rows):>5.1f}%")
print()

print("=" * 94)
print("★ 与 0.5B 实际能力对照")
print("=" * 94)
print("""
  资产里已经测过的三条硬事实 (v120-124 / v127):
     · copy (搬运)          -> ✅ 做得到
     · paraphrase (重组)    -> ❌ 做不到  ← 断层就在这里
     · 用知识 (要新信息)     -> ❌ 做不到 (逐字引用0)

  对照本批真实任务:
     搬运型占比  ->  能做的部分
     重组型占比  ->  ★ 断层区 (0.5B 的死穴)
     需新信息    ->  必须靠外部
""")
print(f"  用时 {time.time()-t0:.2f}s")
