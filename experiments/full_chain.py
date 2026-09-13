#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
full_chain.py — 完整链路: 高维模糊 → 降维 → 低维工具
======================================================
今天所有发现第一次串成一条线:

  高维模糊领域 (语言/语义, D2=14.8)
      ↓ ① 0.5B 嵌入层 (训练好的降维器, 万亿token)
      ↓ ② 正交核 (保距, 语义不失真)
  低维可操作结构 (D2≈5)
      ↓ ③ 低维工具: 配额记忆 / 形式系统 / 最近邻
  输出

验证: 
  A 直接在高维硬算 (基线)
  B 用真降维器 (0.5B嵌入) → 中间表示
  C 完整链路 (降维 + 正交核 + 低维工具)
"""
import numpy as np, sys, time, json

t0 = time.time()
sys.path.insert(0, '/workspace')

# ==================== 载入真降维器 (0.5B 嵌入层) ====================
print('=' * 72)
print('完整链路: 高维模糊 → 0.5B降维 → 正交核 → 低维工具')
print('=' * 72)

Vn = np.load('/workspace/_cache_V.npy')                # (48,896) 已单位化的 48 词嵌入
W2 = json.load(open('/workspace/_cache_W.json'))
Qt = np.load('/workspace/_cache_Qt.npy')               # (896,896) 正交核转置
G = chr(0x120)

# 8 类语义, 每类 6 词
GRP = {
    'animal': ['cat','dog','bird','fish','horse','snake'],
    'food':   ['bread','rice','milk','meat','soup','cake'],
    'emotion':['love','fear','hope','joy','anger','sad'],
    'time':   ['day','week','month','year','hour','minute'],
    'place':  ['city','house','road','tree','field','river'],
    'body':   ['hand','head','eye','foot','heart','skin'],
    'color':  ['red','blue','green','black','white','yellow'],
    'sound':  ['music','song','sound','voice','noise','tone'],
}
words, labs = [], []
for gi, (g, ws) in enumerate(GRP.items()):
    for w in ws:
        if (G+w) in W2:
            words.append(w); labs.append(gi)
labs = np.array(labs)
E = Vn                                                  # (48,896) 已对齐
print('  载入: %d 个词, %d 类, 嵌入维度 %d' % (len(words), len(GRP), E.shape[1]))

# ==================== ② 正交核 ====================
def brain(x, steps=3):
    x = x.copy()
    for _ in range(steps):
        x = 0.5*x + 0.5*np.tanh(x @ Qt)
    return x

# ==================== ③ 低维工具 ====================
def knn_acc(Z, Y, nn=2):
    """最近邻分类 (低维工具)"""
    Zn = Z / (np.linalg.norm(Z, axis=1, keepdims=True) + 1e-9)
    S = Zn @ Zn.T
    ok = 0
    for i in range(len(Y)):
        s = S[i].copy(); s[i] = -9
        v = [Y[j] for j in np.argsort(s)[::-1][:nn]]
        ok += (max(set(v), key=v.count) == Y[i])
    return ok / len(Y)


def d2_eff(X):
    """有效维度 (协方差参与比)"""
    w = np.clip(np.linalg.eigvalsh(np.cov(X.T)), 0, None)
    return float((w.sum()**2) / max((w**2).sum(), 1e-12))


# ==================== 评估 ====================
# 划分: 训练/测试 (跨域)
TRK = ['animal', 'food']
iTR = np.where(np.isin(labs, [list(GRP).index(k) for k in TRK]))[0]
iTE = np.where(~np.isin(labs, [list(GRP).index(k) for k in TRK]))[0]

print()
print('  %-34s %-10s %-10s %s' % ('表示', '有效维', '跨域准确率', '说明'))
print('  ' + '-' * 68)

# A 原始高维
accA = knn_acc(E[iTE], labs[iTE])
print('  %-34s %-10.1f %-10.3f %s' % ('A 原始嵌入 (896维, 直通)', d2_eff(E), accA, '基线'))

# B 只降维 (正交核)
Eb = np.array([brain(x) for x in E])
accB = knn_acc(Eb[iTE], labs[iTE])
print('  %-34s %-10.1f %-10.3f %s' % ('B 嵌入 → 正交核', d2_eff(Eb), accB, '降维+保距'))

# C 完整链路: 降维 → 进一步降维 (PCA到k) → 低维工具
for k in [8, 16, 32]:
    mu = Eb.mean(0)
    _, _, Vt = np.linalg.svd(Eb - mu, full_matrices=False)
    Z = (Eb - mu) @ Vt[:k].T
    accC = knn_acc(Z[iTE], labs[iTE])
    print('  %-34s %-10.1f %-10.3f %s' % ('C 完整链路 (再压到 %d 维)' % k,
          d2_eff(Z), accC, '★' if accC >= accA*0.95 else ''))

# D 上界: 用训练域的类中心做"监督降维" (LDA)
mu_tr = np.array([Eb[iTR][labs[iTR] == c].mean(0) for c in np.unique(labs[iTR])])
Zlda = Eb @ mu_tr.T                      # 投影到"训练域类中心"方向
accD = knn_acc(Zlda[iTE], labs[iTE])
print('  %-34s %-10.1f %-10.3f %s' % ('D 投影到训练域类中心 (参照)',
      d2_eff(Zlda), accD, '参照'))

print()
print('  随机基线 = %.3f,  测试域 = 6 类 (训练只见 2 类)' % (1/6))
print('  判据: 完整链路(C) 能否接近/超过直通(A)')
print()
print('  用时 %.1fs' % (time.time() - t0))
