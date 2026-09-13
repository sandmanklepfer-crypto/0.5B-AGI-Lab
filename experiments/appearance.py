#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
appearance.py — 剥离「外观」后, 只区分「意思」需要多少维?
==========================================================
用户的判断: 把外观剥离掉, 只区分意思, 需要的维度就很小

严格测法: 同样细粒度 (都分成 8 类), 比谁需要的维度少
  · 意义任务: 48 词 → 8 个语义类
  · 外观任务: 48 词 → 8 个字符外观类 (长度/首字母/字符集)

关键对照:
  A 意义需要的维度 vs 外观需要的维度
  B 嵌入里有多少能量花在"外观"上
"""
import numpy as np, json, time

t0 = time.time()
Vn = np.load('/workspace/_cache_V.npy')            # (48,896) 单位化词嵌入
W2 = json.load(open('/workspace/_cache_W.json'))
words = list(W2.keys())[:48]
G = chr(0x120)

sem_lab = np.array([gi for gi in range(8) for _ in range(6)])    # 语义类

# ==================== 外观特征 (从字符串算, 不看意思) ====================
def appearance_feat(w):
    """词的外观: 长度 / 首字母 / 尾字母 / 元音数 / 字符种数"""
    s = w
    VOW = set("aeiou")
    return np.array([
        len(s),
        ord(s[0]) % 8,
        ord(s[-1]) % 8,
        sum(1 for c in s if c in VOW),
        len(set(s)) % 8,
    ], float)


def appearance_class(w):
    """把外观聚成 8 类 (用长度+首字母, 这是最直观的"形状")"""
    f = appearance_feat(w)
    return (int(f[0]) + int(f[1])) % 8


app_raw = np.array([appearance_class(w) for w in words])
# ★ 重编号成 0..C-1 (保证连续)
uniq = sorted(set(app_raw.tolist()))
remap = {v: i for i, v in enumerate(uniq)}
app_lab = np.array([remap[v] for v in app_raw])

print("=" * 90)
print("剥离外观后, 只区分「意思」需要多少维?")
print("=" * 90)
print()
print("  48 个词 → 两个任务, 各分 8 类:")
print("    意义标签: animal/food/emotion/time/place/body/color/sound")
print("    外观标签: (词长 + 首字母) %% 8")
print()
n_sem = len(set(sem_lab.tolist()))
n_app = len(set(app_lab.tolist()))
print("  实际类别数: 意义 %d 类, 外观 %d 类" % (n_sem, n_app))
print()

# ==================== 训练/测试划分 (各类留一半) ====================
def split(lab, ncls):
    tr, te = [], []
    for c in range(ncls):
        idx = np.where(lab == c)[0]
        h = len(idx) // 2
        tr += list(idx[:h]); te += list(idx[h:])
    return np.array(tr), np.array(te)


def acc_from_k(Z, lab, ncls, tr, te):
    if Z.shape[1] < 1:
        return 0.0
    Y = np.eye(ncls)[lab]
    W = np.linalg.solve(Z[tr].T @ Z[tr] + 0.1 * np.eye(Z.shape[1]), Z[tr].T @ Y[tr])
    return float(((Z[te] @ W).argmax(1) == lab[te]).mean())


mu = Vn.mean(0)
_, _, Vt = np.linalg.svd(Vn - mu, full_matrices=False)

tr_s, te_s = split(sem_lab, 8)
tr_a, te_a = split(app_lab, n_app)

print("=" * 90)
print("★ 核心对比: 同样分 8 类, 各自的「最小 k」")
print("=" * 90)
print()
print("  %-6s %-16s %-16s %s" % ("k", "意义精度", "外观精度", "谁更需要维度"))
print("  " + "-" * 62)
RES = []
for k in [1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 64]:
    kk = min(k, Vt.shape[0])
    Z = (Vn - mu) @ Vt[:kk].T
    a_s = acc_from_k(Z, sem_lab, 8, tr_s, te_s)
    a_a = acc_from_k(Z, app_lab, n_app, tr_a, te_a)
    RES.append((k, a_s, a_a))
    tag = "外观" if a_a > a_s + 0.05 else ("意义" if a_s > a_a + 0.05 else "相当")
    print("  %-6d %-16.4f %-16.4f %s" % (k, a_s, a_a, tag))

print()
print("  基线: 随机 = %.3f" % (1/8))

# ==================== 找各自的最小 k ====================
def min_k_for(lab, ncls, tr, te, thresh=0.85):
    for k in [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 48]:
        kk = min(k, Vt.shape[0])
        Z = (Vn - mu) @ Vt[:kk].T
        if acc_from_k(Z, lab, ncls, tr, te) >= thresh:
            return k
    return None


k_sem = min_k_for(sem_lab, 8, tr_s, te_s)
k_app = min_k_for(app_lab, n_app, tr_a, te_a)

print()
print("=" * 90)
print("★ 结论")
print("=" * 90)
print()
print("  %-30s %-14s %s" % ("任务", "最小 k (达85%)", "说明"))
print("  " + "-" * 66)
print("  %-30s %-14s %s" % ("区分「意思」(8类)", "k=%s" % k_sem if k_sem else "—",
      "语义结构在嵌入里很集中"))
print("  %-30s %-14s %s" % ("区分「外观」(8类)", "k=%s" % k_app if k_app else "—",
      "外观信息散在很多维"))

if k_sem and k_app:
    print()
    if k_sem < k_app:
        print("  ★★ 证实你的判断: 意思只需要 %d 维, 外观需要 %d 维" % (k_sem, k_app))
        print("     → 意思的维度成本是外观的 1/%.1f" % (k_app / k_sem))
    elif k_app < k_sem:
        print("  ⚠️ 反了: 外观只需要 %d 维, 意思需要 %d 维" % (k_app, k_sem))
    else:
        print("  → 两者相当 (%d 维)" % k_sem)

# ==================== 补充: 嵌入里"外观方向"占多少能量 ====================
print()
print("=" * 90)
print("★ 补充: 嵌入里有多少能量在「外观」上")
print("=" * 90)
print()
# 用外观特征做回归, 看能解释嵌入的多少方差
Afeat = np.array([appearance_feat(w) for w in words])            # (48,5)
Xc = Vn - mu
# 外观能解释的嵌入方向
B = np.linalg.lstsq(Afeat, Xc, rcond=None)[0]                    # (5,896)
pred = Afeat @ B
explained = np.linalg.norm(pred) ** 2 / (np.linalg.norm(Xc) ** 2)
print("  外观特征(5维) 能解释嵌入总能量的: %.2f%%" % (100 * explained))
# 意义能解释的
Ysem = np.eye(8)[sem_lab]
Bs = np.linalg.lstsq(Ysem, Xc, rcond=None)[0]
preds = Ysem @ Bs
explained_s = np.linalg.norm(preds) ** 2 / (np.linalg.norm(Xc) ** 2)
print("  意义标签(8类) 能解释嵌入总能量的: %.2f%%" % (100 * explained_s))
print()
print("  → 剩下的 %.1f%% 是'其他'" % (100 - 100 * max(explained, explained_s)))

print()
print("  用时 %.2fs" % (time.time() - t0))
