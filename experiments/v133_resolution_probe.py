#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V133 权重分辨率探针 — 0.5B 内部表示里, 哪些维度有结构(分辨率), 哪些是零?
两组:
  A 真值组: 16对真/假数学命题, 表面几乎相同(只差数字/词)
            → 若线性可分, 只能因为权重存了"真值结构"(不是表面文本差)
  B 语义对照组: 水果 vs 动物(结构平行, 只差主题词) → 证明探针方法有效
每层(layer0-12)都测: d' = |μ1-μ2| / sqrt(σ1²+σ2²)  +  投影分类acc
无外部依赖(手写Fisher), 无训练, 一次forward全层hidden
"""
import torch, numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'

TRUE = [
    'ζ函数在s等于2的时候，值等于圆周率的平方除以6',
    'ζ函数在s等于2的值是π的平方除以6',
    'ζ函数在s等于1的地方发散到无穷大',
    'ζ函数在s等于1处是发散的',
    '素数有无穷多个',
    '素数在数量上是无限的',
    'ζ函数的平凡零点都在负偶数上',
    'ζ在负偶数那串点上的值等于零',
    '黎曼猜想从1859年提出至今还没有被证明',
    '黎曼猜想目前仍然没有被证明',
    'ζ函数在实部大于1的区域内一个零点都没有',
    'ζ函数在实部大于1的区域不存在零点',
    '从1加到100的和等于5050',
    '解析延拓把ζ函数扩展到整个复平面',
    'ζ函数在s等于4的时候，值等于圆周率的四次方除以90',
    '欧拉乘积把ζ函数写成所有素数的乘积形式',
]
FALSE = [
    'ζ函数在s等于2的时候，值等于圆周率的平方除以90',
    'ζ函数在s等于2的值是π的平方除以90',
    'ζ函数在s等于1的地方收敛到有限值',
    'ζ函数在s等于1处是收敛的',
    '素数只有有限多个',
    '素数在数量上是有限的',
    'ζ函数的平凡零点都在正偶数上',
    'ζ在正偶数那串点上的值等于零',
    '黎曼猜想在1859年就被证明了',
    '黎曼猜想目前已经被证明了',
    'ζ函数在实部大于1的区域内存在零点',
    'ζ函数在实部大于1的区域有很多零点',
    '从1加到100的和等于5000',
    '解析延拓把ζ函数扩展到整个实轴',
    'ζ函数在s等于4的时候，值等于圆周率的平方除以90',
    '欧拉乘积把ζ函数写成所有自然数的乘积形式',
]
FRUIT = [
    '苹果是红色的水果', '香蕉是黄色的水果', '葡萄是紫色的水果',
    '西瓜是绿色的水果', '橙子是橙色的水果', '草莓是红色的水果',
    '梨是黄色的水果', '樱桃是红色的水果', '柠檬是黄色的水果',
    '桃子是粉色的水果', '李子是紫色的水果', '芒果是黄色的水果',
]
ANIMAL = [
    '老虎是吃肉的动物', '兔子是吃草的动物', '狮子是吃肉的动物',
    '熊猫是吃竹子的动物', '大象是吃树叶的动物', '鲨鱼是吃肉的动物',
    '猴子是吃水果的动物', '狼是吃肉的动物', '牛是吃草的动物',
    '熊是吃鱼的动物', '猫是吃鱼的动物', '狗是吃肉的动物',
]

def probe(X1, X2):
    """d' + Fisher投影acc"""
    X1 = np.array(X1); X2 = np.array(X2)
    m1, m2 = X1.mean(0), X2.mean(0)
    s1, s2 = X1.std(0) + 1e-9, X2.std(0) + 1e-9
    dprime = np.linalg.norm(m1 - m2) / np.sqrt(np.mean(s1**2) + np.mean(s2**2))
    w = m1 - m2
    p1 = X1 @ w / np.linalg.norm(w); p2 = X2 @ w / np.linalg.norm(w)
    thr = (p1.mean() + p2.mean()) / 2
    acc = (np.mean(p1 > thr) + np.mean(p2 < thr)) / 2
    return dprime, acc

def main():
    torch.manual_seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()
    all_texts = TRUE + FALSE + FRUIT + ANIMAL
    enc = tok(all_texts, return_tensors='pt', padding=True, truncation=True, max_length=48).to('cuda')
    with torch.no_grad():
        out = model(input_ids=enc['input_ids'], attention_mask=enc['attention_mask'],
                    output_hidden_states=True)
    hs = out.hidden_states  # 13层 (0..12)
    L = len(TRUE); F = len(FALSE); Fr = len(FRUIT); A = len(ANIMAL)
    print('V133 分辨率探针 | 真值组 %d真+%d假 | 语义组 %d果+%d动物' % (L, F, Fr, A), flush=True)
    print('层 | 真值组 d\'/acc | 语义组 d\'/acc', flush=True)
    for layer, h in enumerate(hs):
        hh = h[:, -1, :].float().cpu().numpy()  # last token
        d1, a1 = probe(hh[:L], hh[L:L+F])
        d2, a2 = probe(hh[L+F:L+F+Fr], hh[L+F+Fr:])
        bar1 = '#' * int(min(d1, 8))
        print('L%2d | 真值 d\'=%5.2f acc=%.2f %-8s | 语义 d\'=%5.2f acc=%.2f' % (
            layer, d1, a1, bar1, d2, a2), flush=True)
    print('\n解读: 语义组acc高+真值组acc≈0.5 → 语义有分辨率/真值零分辨率(断层坐实)', flush=True)
    print('      两组都高 → 权重里有真值结构(之前失败是机制/形态问题, 路线反转)', flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
