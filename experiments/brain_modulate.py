#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
brain_modulate.py — 架构验证: 「脑调制嘴」vs 「脑生产内容」
============================================================
新架构假设(替代"脑→桥→嘴"管道):
  嘴(语言模型) 自己生成语言 —— 它才是思考者
  脑 只输出【低带宽调制信号】, 改变嘴的采样偏好
  带宽要求: 调制 ~1-4 bit/字符  vs  管道架构要 ~8-17 bit

严格对照(核心):
  A 无调制          T=1 固定
  B 脑调制温度       T = exp(β·tanh(w·x))   ← 脑信号, 低带宽
  C 随机调制温度     同样的β, 但用白噪声     ← 带宽相同的对照!
  D 固定高温度       T=1.5                  ← "直接调温度"能不能替代脑?
  E 脑调制(打乱时间)  把脑信号的时间顺序打乱  ← 检验"结构"还是"幅度"起作用

判据:
  质量 = 生成文本的 trigram 对数似然 (越高越通顺)
  多样性 = 生成集合的字符熵
  若 B 在 (质量, 多样性) 平面上优于 C/D/E → 脑的【时间结构】有价值
"""
import numpy as np, time
from collections import defaultdict, Counter

t0 = time.time()

# ==================== 嘴: 真实语言模型 (trigram) ====================
txt = open('/workspace/raw_corpus.txt', encoding='utf-8', errors='ignore').read()[:60000]
cf = Counter(txt)
TOP = [c for c, _ in cf.most_common(400)]
c2i = {c: i for i, c in enumerate(TOP)}
V = len(TOP)
data = np.array([c2i[c] for c in txt if c in c2i])

tri = defaultdict(Counter)
for i in range(len(data) - 2):
    tri[(data[i], data[i + 1])][data[i + 2]] += 1
DIST = {}
for k, c in tri.items():
    v = np.zeros(V)
    for a, b in c.items():
        v[a] = b
    v += 0.005
    DIST[k] = v / v.sum()
uc = Counter(data)
UNI = np.zeros(V)
for a, b in uc.items():
    UNI[a] = b
UNI /= UNI.sum()
print("嘴(trigram): %d 条上下文, 词表 %d, 语料 %d 字符  [%.1fs]"
      % (len(DIST), V, len(data), time.time() - t0))

# 选一个常见 bigram 作为固定前缀
best_ctx = max(tri, key=lambda k: sum(tri[k].values()))
print("固定前缀 = (%d, %d)  即 %r%r" % (best_ctx[0], best_ctx[1],
      TOP[best_ctx[0]], TOP[best_ctx[1]]))

# ==================== 脑 (自持核, 已验证) ====================
DT = 0.05; ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
G0, RHO, MU = 0.35, 0.02, 1.8; SIG = np.tanh
D, NB = 96, 24; d = D // NB
r = np.random.RandomState(0)
A = np.zeros((D, D))
for b in range(NB):
    s = b * d; e = s + d
    sub = r.randn(d, d); w = np.abs(np.linalg.eigvals(sub)).max()
    A[s:e, s:e] = sub * (1.15 / w)
A = A * 2.5
x = np.random.RandomState(99).randn(D, 1) * 0.5
F = np.zeros_like(x); E = np.full((1, 1), 0.4)
wmod = r.randn(D) / np.sqrt(D)
brain = []
for t in range(30000):
    act = SIG(x)
    F = np.clip(F + DT * RHO * (act ** 2 - F), 0, 2)
    g = E / (KAPPA + E)
    x = x + DT * (g * (A @ act - MU * F * x) - G0 * x)
    E = np.maximum(E + DT * (ETA * (act ** 2).sum(0, keepdims=True) - GAMMA * E), 0.0)
    brain.append(float(wmod @ x[:, 0]))
brain = np.array(brain)
brain = (brain - brain.mean()) / (brain.std() + 1e-9)
ac10 = float(np.corrcoef(brain[:-10], brain[10:])[0, 1])
print("脑: 30000步 [%.1fs]  调制信号自相关(lag10)=%.3f  %s"
      % (time.time() - t0, ac10, "有记忆(结构)" if ac10 > 0.5 else "弱记忆"))

# ==================== 采样 ====================
def gen(mod, ctx, n=30, beta=0.6, seed=0):
    """mod: 长度n的调制信号(标准化); 返回字符id序列"""
    rng = np.random.RandomState(seed)
    a, b = ctx
    out = []
    for i in range(n):
        p = DIST.get((a, b), UNI)
        T = float(np.exp(beta * mod[i]))          # 脑→温度
        q = np.power(p, 1.0 / T)
        q = q / q.sum()
        c = int(np.searchsorted(np.cumsum(q), rng.rand()))
        c = min(c, V - 1)
        out.append(c); a, b = b, c
    return out


def quality(seq):
    lp = 0.0; n = 0
    for i in range(len(seq) - 2):
        p = DIST.get((seq[i], seq[i + 1]), UNI)
        lp += np.log(p[seq[i + 2]] + 1e-12); n += 1
    return lp / max(n, 1)


def diversity(seqs):
    allc = [c for s in seqs for c in s]
    cnt = np.bincount(allc, minlength=V).astype(float)
    cnt /= cnt.sum(); cnt = cnt[cnt > 0]
    return float(-(cnt * np.log(cnt)).sum())


N_RUN, LEN = 40, 40
rng = np.random.RandomState(123)
print()
print("=" * 100)
print("架构验证: 脑调制 vs 随机调制 vs 固定温度   (%d 次生成 × %d 字符)" % (N_RUN, LEN))
print("=" * 100)
print("  %-26s %-12s %-12s %-12s %s"
      % ("配置", "质量(logL)", "多样性(熵)", "vs无调制质量", "说明"))

# A 无调制
seqsA = [gen(np.zeros(LEN), best_ctx, LEN, seed=i) for i in range(N_RUN)]
qA = np.mean([quality(s) for s in seqsA]); dA = diversity(seqsA)

# B 脑调制 (真实脑信号, 不同起始点)
seqsB = []
for i in range(N_RUN):
    off = 5000 + i * 37
    seqsB.append(gen(brain[off:off + LEN], best_ctx, LEN, seed=i))
qB = np.mean([quality(s) for s in seqsB]); dB = diversity(seqsB)

# C 随机调制 (白噪声, 同带宽)
seqsC = []
for i in range(N_RUN):
    m = rng.randn(LEN)
    seqsC.append(gen(m, best_ctx, LEN, seed=i))
qC = np.mean([quality(s) for s in seqsC]); dC = diversity(seqsC)

# D 固定高温
seqsD = [gen(np.full(LEN, np.log(1.5) / 0.6), best_ctx, LEN, seed=i) for i in range(N_RUN)]
qD = np.mean([quality(s) for s in seqsD]); dD = diversity(seqsD)

# E 脑信号时间打乱 (保留幅度分布, 破坏时间结构)
seqsE = []
for i in range(N_RUN):
    off = 5000 + i * 37
    m = brain[off:off + LEN].copy(); rng.shuffle(m)
    seqsE.append(gen(m, best_ctx, LEN, seed=i))
qE = np.mean([quality(s) for s in seqsE]); dE = diversity(seqsE)

rows = [("A 无调制 (T=1)", qA, dA, "基线"),
        ("B ★脑调制温度", qB, dB, "低带宽, 有结构"),
        ("C 随机调制 (同带宽)", qC, dC, "对照: 白噪声"),
        ("D 固定高温 (T=1.5)", qD, dD, "对照: 直接调温度"),
        ("E 脑信号打乱时序", qE, dE, "对照: 破坏结构")]
for nm, q, dd, note in rows:
    print("  %-26s %-12.4f %-12.3f %-12s %s"
          % (nm, q, dd, "%+.1f%%" % (100 * (q / qA - 1)), note))

print()
print("-" * 100)
print("核心判据: 脑的「时间结构」有没有价值?")
print("-" * 100)
print("  B(脑) vs C(随机同带宽):  质量 %+.1f%%   多样性 %+.1f%%"
      % (100 * (qB / qC - 1), 100 * (dB / dC - 1)))
print("  B(脑) vs E(打乱时序):    质量 %+.1f%%   多样性 %+.1f%%"
      % (100 * (qB / qE - 1), 100 * (dB / dE - 1)))
print("  B(脑) vs D(固定高温):    质量 %+.1f%%   多样性 %+.1f%%"
      % (100 * (qB / qD - 1), 100 * (dB / dD - 1)))
print()
if qB > qC and qB > qE:
    print("  ★ 结论: 脑的时间结构有价值 (在同样带宽下, 结构化信号 > 白噪声)")
    if qB > qD and dB >= dD * 0.95:
        print("    → 且优于「直接调温度」: 脑提供了温度做不到的东西")
    else:
        print("    → 但「直接调温度」也能达到类似效果, 脑的增量有限")
else:
    print("  ✗ 结论: 脑的调制没有优于同带宽的随机信号 → 时间结构无价值")

# 带宽核算
print()
print("-" * 100)
print("带宽核算 (这是新架构的核心优势)")
print("-" * 100)
print("  管道架构(脑→桥→嘴): 需要 %d 个符号/步 = %d bit/步" % (11, 11 * 5))
print("  调制架构(脑→调嘴):   1 个标量/步  ≈ %.0f bit/步 (量化到16档)" % np.log2(16))
print("  → 带宽降低 %.0f 倍" % (11 * 5 / np.log2(16)))
print()
print("总耗时 %.1fs" % (time.time() - t0))
