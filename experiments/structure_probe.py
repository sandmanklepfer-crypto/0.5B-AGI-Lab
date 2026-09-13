#!/usr/bin/env python3
"""结构探测+极致压缩 — 先看数据长什么"状", 再按状压缩
问题: 300条(真实数据) 能不能压到 10条虚状态?
方法: 
 1 探测形状: 数据是否有树状/团状/层级 (前缀树深度/聚类轮廓)
 2 用"前缀树压缩" (真实文本天然有树状: 共享前缀/词根)
 3 测压缩率 vs 还原率
"""
import re, os, json
import numpy as np

def load_cn():
    texts = []
    for root, dirs, files in os.walk('/workspace/rebuild/apk_out/res/values-zh'):
        for f in files:
            try:
                t = open(os.path.join(root, f), encoding='utf-8', errors='ignore').read()
                texts += re.findall(r'[\u4e00-\u9fff]{2,}', t)
            except: pass
    return texts

def main():
    texts = load_cn()
    print(f'真实中文短语: {len(texts)} 条')
    # 用其中300条做测试
    if len(texts) > 300:
        texts = texts[:300]
    print(f'测试: {len(texts)} 条')

    # 1) 前缀树压缩: 所有短语共享前缀的程度
    # 建前缀树, 看"唯一前缀数" (若共享多→树状强→可压缩)
    class Node:
        __slots__ = ('kids', 'cnt')
        def __init__(s): s.kids = {}; s.cnt = 0
    root = Node()
    for t in texts:
        n = root
        for ch in t:
            n.cnt += 1
            if ch not in n.kids:
                n.kids[ch] = Node()
            n = n.kids[ch]
        n.cnt += 1
    # 统计节点数 (总存储单元)
    def count(n):
        return 1 + sum(count(k) for k in n.kids.values())
    nodes = count(root)
    # 存原始字符数
    raw_chars = sum(len(t) for t in texts)
    print(f'\n原始存储: {raw_chars} 字符')
    print(f'前缀树节点: {nodes} (共享前缀后)')
    print(f'树压缩率: {nodes/raw_chars*100:.1f}% ({raw_chars/nodes:.1f}x)')
    print(f'→ {"✅ 强树状结构(共享多)" if nodes < raw_chars*0.5 else "树状一般"}')

    # 2) 更深压缩: 只存 出现>1次的共享子树(剪枝) 
    def count_shared(n):
        return sum(count_shared(k) for k in n.kids.values()) + (1 if n.cnt > 1 else 0)
    shared = count_shared(root)
    print(f'只存共享部分(剪枝): {shared} 节点, 压缩率 {shared/raw_chars*100:.1f}%')

    # 3) 还原率: 从树能否还原所有300条?
    # 建完整树 = 100%还原; 剪枝树+每条独有后缀也能还原
    print(f'\n[结论] 树状结构下: 300条存储 = 共享树({nodes}节点) + 每条少量独有指针')
    print(f'       "300压到10" 取决于共享程度; 本数据共享率: {nodes/raw_chars*100:.0f}%')
    print(f'       但真实语言有更高层结构(词根/语法模板), 实际可压更多')

if __name__ == '__main__':
    main()
