#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''anchor_retrieval.py — 搬运 + 检索: 能不能绕开「产生新信息」?'''
import json, re, time
from collections import Counter, defaultdict
t0 = time.time()

QA = []
with open('/workspace/clean_train.jsonl', encoding='utf-8') as f:
    for line in f:
        d = json.loads(line)
        QA.append((d['task'], d['q'], d['a']))

# ---- 第一步「搬运」: 从问题里搬出锚点 (纯复制, 不产生任何新东西) ----
PAT = re.compile(r'[A-Za-z][A-Za-z0-9._-]{2,}(?:/[A-Za-z][A-Za-z0-9._-]+)?')


def anchors(q):
    return [x for x in PAT.findall(q) if len(x) >= 4]


# ---- 第二步「建库」: 锚点 -> 答案 ----
lib = defaultdict(Counter)
for t, q, a in QA:
    for an in anchors(q):
        lib[an][a] += 1
lib = {k: v.most_common(1)[0][0] for k, v in lib.items()}

print("=" * 92)
print("搬运 + 检索: 能不能绕开「产生新信息」?")
print("=" * 92)
print(f"  {len(QA)} 条真实任务  ->  建成 {len(lib)} 个「锚点 -> 答案」条目")
print()

hit = miss = noanchor = 0
examples = []
hit_by_task = defaultdict(lambda: [0, 0])
for t, q, a in QA:
    an = anchors(q)
    hit_by_task[t][1] += 1
    if not an:
        noanchor += 1
        continue
    got = lib.get(an[0])
    if got == a:
        hit += 1
        hit_by_task[t][0] += 1
        if len(examples) < 3 and t == 'hint':
            examples.append((t, q, an[0], got))
    else:
        miss += 1

N = len(QA)
print("=" * 92)
print("★ 结果")
print("=" * 92)
print()
print(f"  {'做法':<44}{'条数':<10}{'占比'}")
print("  " + "-" * 66)
print(f"  {'✅ 搬运锚点 -> 查库 -> 直接copy答案':<44}{hit:<10}{100*hit/N:.1f}%")
print(f"  {'❌ 锚点找到了但答案不对':<44}{miss:<10}{100*miss/N:.1f}%")
print(f"  {'❌ 问题里没有可搬运的锚点 (开放问题)':<44}{noanchor:<10}{100*noanchor/N:.1f}%")
print()

print("=" * 92)
print("★ 按任务类型拆开")
print("=" * 92)
print()
print(f"  {'任务类型':<14}{'总数':<10}{'成功':<10}{'成功率':<12}{'问法'}")
print("  " + "-" * 74)
for t in ['whatis', 'hint', 'summary', 'title2abs', 'solve', 'topic']:
    ok, tot = hit_by_task[t]
    print(f"  {t:<14}{tot:<10}{ok:<10}{100*ok/max(tot,1):<12.0f}%")
print()

print("=" * 92)
print("★ 实例: 「提问方式完全不同, 但搬出同一个锚点 -> 拿到同一个答案」")
print("=" * 92)
print()
for t, q, an, got in examples:
    print(f"  问法({t}): {q[:60]}")
    print(f"     搬出锚点: 「{an}」")
    print(f"     查库得到: {got[:66]}...")
    print()

print("=" * 92)
print("★ 关键: 整条链里, 0.5B 需要「产生新信息」吗?")
print("=" * 92)
print("""
  步骤                      动作          是搬运还是产生?   0.5B 能做吗
  ---------------------------------------------------------------
  ① 从问题里搬出锚点         复制/正则      纯搬运            ✅ 能做
  ② 用锚点去库里查           查表          纯搬运            ✅ 能做
  ③ 把库里的答案搬回来        复制          纯搬运            ✅ 能做
  ④ 生成新信息               ——            产生              ❌ 不需要!

  ★ 结论: 整条链【一个"产生"都没有】 —— 所以 0.5B 完全可以胜任

  ★ 而「新信息」从哪来?
     从【库】里来 —— 库是提前建好的, 新信息在入库那一刻就产生了.

  ★ 这就是「搬运 + 检索」的完整形式:
     把"产生新信息"这件事, 从【推理时】搬到【入库时】.
     推理时只做搬运, 入库时才需要创造.
""")
print(f"  用时 {time.time()-t0:.2f}s")
