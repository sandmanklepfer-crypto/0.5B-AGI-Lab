#!/usr/bin/env python3
"""语义层压缩测试 — 34.9万词按语义族能压到多少?
jieba词典自带词性(粗语义类) + 词频. 测:
 1 词性族: 分多少类, 每类多大 (词性=最粗语义同族)
 2 词性+字首聚类: 更细的同族
 3 语义同族的压缩: 一族存1个代表+差异
"""
from collections import Counter, defaultdict

def main():
    words = []   # (词, 词频, 词性)
    for line in open('/workspace/jieba-0.42.1/jieba/dict.txt', encoding='utf-8'):
        p = line.strip().split()
        if len(p) >= 3:
            words.append((p[0], int(p[1]), p[2]))
        elif len(p) == 2:
            words.append((p[0], int(p[1]), 'x'))
    N = len(words)
    print(f'词总数: {N}')
    # 1) 词性分布 (语义大类)
    pos_count = Counter(w[2] for w in words)
    print(f'\n词性类数: {len(pos_count)}')
    top_pos = pos_count.most_common(15)
    print(f'top词性: {top_pos}')
    # 2) 按词性分族后, 每族内部还能按"字首/主题"再分
    # 测: 同词性+同首字 = 一族 (近似语义场, 如 n+医=医学名词)
    subfam = Counter()
    for w, freq, pos in words:
        key = (pos, w[0] if w else '')   # 词性+首字
        subfam[key] += 1
    print(f'\n词性+首字 子族数: {len(subfam)}')
    big_fams = sum(1 for c in subfam.values() if c >= 10)
    print(f'≥10词的子族: {big_fams} (这些可族内压缩)')
    # 3) 压缩估算: 存每子族"族代表+差异" vs 全量
    # 每子族存: 词性+首字(族id) + 族内每词的剩余部分
    fam_storage = 0
    for (pos, ch), c in subfam.items():
        # 每族: 族头(pos+首字=~4字节) + 每词存剩余字(平均~1.5字×2字节) + 词频2字节
        fam_storage += 4 + c * 5
    direct = sum(len(w) for w, _, _ in words)
    print(f'\n直接存: {direct:,}')
    print(f'语义子族压缩: {fam_storage:,} ({fam_storage/direct*100:.0f}% of 直接)')
    print(f'压缩率: {direct/fam_storage:.2f}x')
    # 4) 更粗: 只按词性分(30类)的话能压吗?
    pos_only = N * 3  # 每词只存词性+剩余
    print(f'\n只按词性(30类)理论极限: 每族需存全部词 → 压不了多少(词还是得全存)')
    print(f'结论: 语义族能帮"组织/索引", 但每词独特性仍要存 → 压不狠')

if __name__ == '__main__':
    main()
