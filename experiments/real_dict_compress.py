#!/usr/bin/env python3
"""真实词典压缩极限 — 34.9万词(真实知识库) 能压到多少?
方法: 海海因子结构压缩
 层1 字(3500常用) 层2 词(34.9万由字组合)
 压缩方案A: 全量存词(349k)
 压缩方案B: 存"字+构词规则/共享部分"
 压缩方案C: 词= 字组合 → 用"每词=字索引序列", 实际存多少?
真实测: 349046词 若按"字+词表"到底需要多少存储 vs 直接存
"""
import numpy as np
from collections import Counter

def main():
    words = []
    for line in open('/workspace/jieba-0.42.1/jieba/dict.txt', encoding='utf-8'):
        p = line.strip().split()
        if p: words.append(p[0])
    N = len(words)
    # 字符集
    chars = set(''.join(words))
    print(f'真实知识库: {N} 词, 涉及 {len(chars)} 个不同字')

    # 方案A: 直接存每个词 (每词=其字符序列)
    direct_chars = sum(len(w) for w in words)
    print(f'\n[A 直接存]: {direct_chars:,} 字符 (每词全存)')

    # 方案B: 字库 + 每词=字的索引 (共享字库, 词=索引序列)
    # 字索引: 每字~2字节(几千字) ; 每词存 长度+索引
    char_list = sorted(chars)
    char_idx = {c:i for i,c in enumerate(char_list)}
    # 词存储 = 每词(长度1字节 + 每字索引2字节)
    B_storage = N*1 + direct_chars*2
    print(f'[B 字库+索引]: {B_storage:,} 字节 (字库共享) 压缩率 {B_storage/direct_chars*100:.0f}% of A')

    # 方案C: 前缀树/词根共享 (海海因子: 共享词根)
    # 统计共享前缀节省: 相同前缀的字符只需存一次(在树里)
    class Node:
        __slots__=('kids','cnt')
        def __init__(s): s.kids={}; s.cnt=0
    root=Node()
    for w in words:
        n=root
        for ch in w:
            n.cnt+=1
            if ch not in n.kids: n.kids[ch]=Node()
            n=n.kids[ch]
        n.cnt+=1
    def count(n): return 1+sum(count(k) for k in n.kids.values())
    trie_nodes = count(root)
    print(f'[C 前缀树共享]: {trie_nodes:,} 节点 压缩率 {trie_nodes/direct_chars*100:.1f}% of A ({direct_chars/trie_nodes:.1f}x)')

    # 方案D: 真·极致: 只存"出现频率高的共享子串", 稀有词仍全存
    # 模拟: 存 高频2字词根 (出现>50次的2字组合)
    bigrams = Counter()
    for w in words:
        for i in range(len(w)-1):
            bigrams[w[i:i+2]] += 1
    common = {bg for bg,c in bigrams.items() if c>50}
    print(f'[D 高频词根]: {len(common):,} 个高频2字根 (覆盖 {sum(c for bg,c in bigrams.items() if bg in common)/max(sum(bigrams.values()),1)*100:.0f}% 的2字出现)')

    print(f'\n=== 压缩对比 (34.9万词) ===')
    print(f'直接存: {direct_chars:,} 字符')
    print(f'字库+索引: {B_storage:,} ({(direct_chars-B_storage)/direct_chars*100:.0f}% 节省)')
    print(f'前缀树: {trie_nodes:,} ({100-trie_nodes/direct_chars*100:.0f}% 节省)')

if __name__ == '__main__':
    main()
