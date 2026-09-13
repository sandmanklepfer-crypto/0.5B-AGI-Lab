#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''library_grow.py — 结构库能不能【自己长大】? (这才是比 GPT 激进的地方)'''
import random, time
from collections import deque, Counter

t0 = time.time()
random.seed(1)

INC = lambda x: x + 1
DEC = lambda x: x - 1
DBL = lambda x: 2 * x
NEG = lambda x: -x
BASE = [("+1", INC), ("-1", DEC), ("x2", DBL), ("neg", NEG)]

# 隐藏的"动机"(motif): 会被反复用到的两个组合
M1 = [DBL, INC]      # 2x+1
M2 = [NEG, INC]      # -x+1


def apply(prog, x):
    for f in prog:
        x = f(x)
    return x


def bfs(x, y, prims, maxd=7):
    q = deque([[]]); n = 0
    while q:
        p = q.popleft(); n += 1
        if p and apply(p, x) == y:
            return p, n
        if len(p) < maxd:
            for _, f in prims:
                q.append(p + [f])
    return None, n


def gen_task():
    steps = []
    for _ in range(3):
        r = random.random()
        if r < 0.5:
            steps += M1
        elif r < 0.8:
            steps += M2
        else:
            steps.append(random.choice([INC, DEC, DBL, NEG]))
    return steps


XS = list(range(1, 9))
print("=" * 88)
print("结构库能不能【自己长大】? —— 这是比 GPT 激进的地方")
print("=" * 88)
print("  初始库: 4 个基本操作 (+1, -1, x2, neg)")
print("  任务: 3 步隐藏程序 (里面藏着反复出现的'动机')")
print("  搜索: 广度优先, 找最短的那个程序")
print()

lib = list(BASE)
solved = []
print(f"  {'阶段':<26}{'库里有几个操作':<16}{'平均搜索节点数':<18}{'说明'}")
print("  " + "-" * 80)

phase_names = ["阶段1: 库是空的(只有4个基本操作)", "阶段2: 自己学出第1个动机",
               "阶段3: 自己学出第2个动机"]
for phase in range(3):
    nodes = []
    for _ in range(15):
        x = random.choice(XS)
        p = gen_task()
        y = apply(p, x)
        prog, n = bfs(x, y, lib)
        nodes.append(n)
        if prog:
            solved.append(prog)
    avg = sum(nodes) / len(nodes)
    print(f"  {phase_names[phase]:<26}{len(lib):<16}{avg:<18.0f}"
          f"{'★ 越用越快' if phase > 0 else '基准'}")
    # ★ 自动抽象: 统计所有解里【相邻的操作对】, 最频繁的那个 → 打包成新操作
    nameof = {id(f): n for n, f in lib}
    pairs = Counter()
    for s in solved:
        for k in range(len(s) - 1):
            pairs[(id(s[k]), id(s[k + 1]))] += 1
    if pairs:
        (i1, i2), cnt = pairs.most_common(1)[0]
        nm1, nm2 = nameof.get(i1, "?"), nameof.get(i2, "?")
        newname = f"({nm1}>{nm2})"
        if cnt >= 5 and not any(n == newname for n, _ in lib):
            f1, f2 = next(f for n, f in lib if id(f) == i1), next(f for n, f in lib if id(f) == i2)

            def newf(x, f1=f1, f2=f2):
                return f2(f1(x))
            lib.append((newname, newf))
            print(f"     ↳ 自动抽象出: 把 [{nm1} + {nm2}] 打包成1个新操作 "
                  f"(在解里出现了 {cnt} 次)  ← 没人告诉它, 它自己发现的")
        elif cnt >= 5:
            print(f"     ↳ 已有 {newname} (出现 {cnt} 次), 跳过")
print()
print("=" * 88)
print("★ 关键: 库是【自己长大】的, 不是人给的")
print("=" * 88)
print()
print("  最终库里有什么:")
for nm, _ in lib:
    print(f"     - {nm}")
print()
print(f"  总用时 {time.time()-t0:.2f}s")
