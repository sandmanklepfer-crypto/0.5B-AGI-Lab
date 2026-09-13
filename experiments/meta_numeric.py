#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''meta_numeric.py — 400+实验数字化: 找真正的决定性因子 (长度归一化 + 显式判决)'''
import glob, re, time
t0 = time.time()

FEATS = {
    'W_改权重':   ['lora', 'LoRA', '微调', '梯度', '写权重', 'trainable', '装头', '去噪头'],
    'E_外挂':     ['外挂', '外部', '分离式', '读出', '形式系统', '配额', '缓存'],
    'D_离散符号': ['离散', '符号', '量化', 'token', 'K=', '格点'],
    'V_验证器':   ['验证', '判定', '真值', '可判', '对错'],
    'F_反馈':     ['反馈', '闭环', '回环', '自读', '迭代'],
    'R_可逆':     ['可逆', '保面积', '正交', '保距', '辛'],
    'C_临界':     ['临界', '混沌', '谱半径', 'lyapunov', '边缘'],
    'M_记忆':     ['记忆', '检索', '池', '知识', '缓存'],
    'G_生成':     ['生成', '采样', '自持', '涌现', '涌现'],
}
NEG_MARK = ['负结果', '失败', '不是更强', '更弱', '归零', '无效', '装歪', '全败',
            '崩', '走不通', '补不了', '零引用', '挣到的是方向', '不成立', '坏死']

docs = sorted(glob.glob('/workspace/资产_*.md'))
print("=" * 94)
print("400+ 实验数字化分析: 找真正的决定性因子")
print("=" * 94)
print(f"  用 {len(docs)} 份资产文档 (每份=一次实验的完整记录)")
print()

rows = []
for f in docs:
    t = open(f, encoding='utf-8', errors='ignore').read()
    head = t[:600]
    name = f.split('/')[-1].replace('资产_', '').replace('.md', '')
    L = max(len(t), 1)
    # 判决: 头部/结论区 出现负面标记 -> 失败
    isneg = any(m in head for m in NEG_MARK)
    # 归一化特征密度 (每千字)
    dens = {}
    for k, kws in FEATS.items():
        dens[k] = sum(t.lower().count(w.lower()) for w in kws) * 1000.0 / L
    rows.append((name, dens, isneg, L))

pos = [r for r in rows if not r[2]]
neg = [r for r in rows if r[2]]
print(f"  正结果 {len(pos)} 份 | 负结果 {len(neg)} 份")
print(f"  负结果清单: {', '.join(r[0][:14] for r in neg)}")
print()

print("=" * 94)
print("一、特征密度对比 (每千字出现次数, 已归一化长度)")
print("=" * 94)
print()
print(f"  {'特征':<12}{'正结果组':<12}{'负结果组':<12}{'差异':<12}{'倍率':<10}{'判定'}")
print("  " + "-" * 78)
res = []
for k in FEATS:
    mp = sum(r[1][k] for r in pos) / max(len(pos), 1)
    mn = sum(r[1][k] for r in neg) / max(len(neg), 1)
    ratio = mn / max(mp, 1e-9)
    d = mn - mp
    tag = "★失败组更重" if ratio > 1.3 else ("★成功组更重" if ratio < 0.7 else "相当")
    res.append((k, mp, mn, d, ratio, tag))
for k, mp, mn, d, ratio, tag in sorted(res, key=lambda x: -x[4]):
    print(f"  {k:<12}{mp:<12.2f}{mn:<12.2f}{d:+.2f}{'':<4}{ratio:<10.2f}{tag}")
print()

print("=" * 94)
print("二、★ 决定性检验: 只看「改权重」这一个特征")
print("=" * 94)
print()
KW = 'W_改权重'
w_pos = sum(1 for r in pos if r[1][KW] > 0)
w_neg = sum(1 for r in neg if r[1][KW] > 0)
print(f"  正结果里, 提到「改权重/LoRA/梯度」的: {w_pos}/{len(pos)}  ({100*w_pos/len(pos):.0f}%)")
print(f"  负结果里, 提到「改权重/LoRA/梯度」的: {w_neg}/{len(neg)}  ({100*w_neg/len(neg):.0f}%)")
print()
print(f"  → 倍率 = {(w_neg/len(neg))/max(w_pos/len(pos),1e-9):.2f} 倍")
print()

print("=" * 94)
print("三、用全部特征做「判别」: 能不能自动分出成功/失败?")
print("=" * 94)
print()
KEYS = list(FEATS)
# 用归一化密度做最近质心判别
cents = {}
for lab, grp in [('pos', pos), ('neg', neg)]:
    cents[lab] = [sum(r[1][k] for r in grp) / max(len(grp), 1) for k in KEYS]
def dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
import math
right = 0
conf = {'pos': [0, 0], 'neg': [0, 0]}
for name, dens, isneg, L in rows:
    v = [dens[k] for k in KEYS]
    dp, dn = dist(v, cents['pos']), dist(v, cents['neg'])
    pred = 'neg' if dn < dp else 'pos'
    if (pred == 'neg') == isneg:
        right += 1
    true = 'neg' if isneg else 'pos'
    conf[true][0 if pred == true else 1] += 1
print(f"  最近质心判别准确率: {right}/{len(rows)} = {100*right/len(rows):.1f}%")
print(f"    (基线: 全猜多数类 = {100*max(len(pos),len(neg))/len(rows):.1f}%)")
print()
print(f"  混淆矩阵:")
print(f"    真实正 -> 判正 {conf['pos'][0]}, 判负 {conf['pos'][1]}")
print(f"    真实负 -> 判负 {conf['neg'][0]}, 判正 {conf['neg'][1]}")
print()

print("=" * 94)
print("四、★ 三维分组: 按 (改权重, 外挂, 有验证器) 看成功率")
print("=" * 94)
print()
groups = {}
for name, dens, isneg, L in rows:
    key = (dens['W_改权重'] > 0.3, dens['E_外挂'] > 0.5, dens['V_验证器'] > 1.0)
    groups.setdefault(key, [0, 0])
    groups[key][0 if isneg else 1] += 1
print(f"  {'改权重':<10}{'外挂':<10}{'验证器':<10}{'成功':<8}{'失败':<8}{'成功率'}")
print("  " + "-" * 58)
for k in sorted(groups, key=lambda x: -(groups[x][1] / max(sum(groups[x]), 1))):
    a, b = groups[k]
    print(f"  {str(k[0]):<10}{str(k[1]):<10}{str(k[2]):<10}{b:<8}{a:<8}{100*b/max(a+b,1):.0f}%")
print()

print("  用时 %.2fs" % (time.time() - t0))
