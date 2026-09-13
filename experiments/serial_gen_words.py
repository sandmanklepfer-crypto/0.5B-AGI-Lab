#!/usr/bin/env python3
"""时间序列推演词测试 — 几个种子词能否"推演/补齐"出所有词?
词 = 状态; 时间序列步进 = 从当前词"演化"出下一个词
测: 定义词间转移(同首字/同尾字/同词性链), 看少量种子+步进能覆盖多少词
"""
from collections import defaultdict, Counter

def main():
    words = []
    for line in open('/workspace/jieba-0.42.1/jieba/dict.txt', encoding='utf-8'):
        p = line.strip().split()
        if p: words.append(p[0])
    N = len(words)
    print(f'词总数: {N}')
    # 转移规则: 词A → 词B 如果 B以A的末字开头 (词链: 成语接龙式)
    # 这模拟"时间序列一步": 从A经一步到B
    by_first = defaultdict(list)
    for w in words:
        by_first[w[0]].append(w)
    # 可达性: 从种子出发, 每步"接龙"(末字→首字), 能覆盖多少?
    # 先看: 从任意词出发, 末字能否接上别的词 (一步可达率)
    last_to_first = Counter()
    for w in words:
        last_to_first[w[-1]] += 1
    # 一个词能否继续? 看常见末字是否有词以它开头
    dead_end = sum(1 for w in words if w[-1] not in by_first or len(by_first[w[-1]])==0)
    print(f'死路词(末字无人接): {dead_end} ({dead_end/N*100:.0f}%)')
    # BFS覆盖: 从10个种子出发, 接龙式推演, 覆盖多少词
    import random
    random.seed(0)
    seeds = random.sample(words, 10)
    seen = set(seeds)
    queue = list(seeds)
    steps = 0
    while queue and steps < 500000:
        w = queue.pop()
        # 一步: 找以 w[-1] 开头的未见过词
        nxts = by_first.get(w[-1], [])
        for nw in nxts[:3]:   # 每步最多3个分支
            if nw not in seen:
                seen.add(nw)
                queue.append(nw)
        steps += 1
    print(f'从10种子接龙推演: 覆盖 {len(seen)}/{N} 词 ({len(seen)/N*100:.1f}%)')
    # 更大种子
    seeds = random.sample(words, 100)
    seen = set(seeds); queue = list(seeds); steps=0
    while queue and steps < 2000000:
        w = queue.pop()
        for nw in by_first.get(w[-1], [])[:3]:
            if nw not in seen:
                seen.add(nw); queue.append(nw)
        steps+=1
    print(f'从100种子接龙推演: 覆盖 {len(seen)}/{N} ({len(seen)/N*100:.1f}%)')

if __name__ == '__main__':
    main()
