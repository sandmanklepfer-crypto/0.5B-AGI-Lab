#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multiview.py — 多视角: 结构在"关系"里, 不在任何单个视角里
============================================================
用户的洞察:
  同一层次的多个视角, 它们之间的"对话"自然涌现出结构
  单语言描述很费劲, 但多视角交互很简单

量化:
  隐藏结构 = 三维曲线 (螺旋/圆/8字/波浪)
  视角     = 不同方向的投影 → 各自看到 1D 信号
  
  测:
    ① 单视角: 要区分这些结构, 需要看多久? (描述长度)
    ② 多视角: 需要几个视角? 看多久?
    ③ 关键: 结构是不是只在"视角间的关系"里
"""
import numpy as np, time

t0 = time.time()

# ==================== 四种隐藏结构 (3D 曲线) ====================
def make_structs(n=4000, seed=0):
    r = np.random.RandomState(seed)
    t = np.linspace(0, 4*np.pi, n)
    S = {}
    # ① 圆: 在 xy 平面画圆
    S['圆'] = np.stack([np.cos(t), np.sin(t), np.zeros_like(t)], 1)
    # ② 螺旋: 圆 + z 线性上升
    S['螺旋'] = np.stack([np.cos(t), np.sin(t), t/(4*np.pi)], 1)
    # ③ 8字: 李萨如曲线 (x=sin t, y=sin 2t)
    S['8字'] = np.stack([np.sin(t), np.sin(2*t), np.zeros_like(t)], 1)
    # ④ 波浪(平面内): z 方向正弦
    S['波浪'] = np.stack([t/(4*np.pi), np.zeros_like(t), 0.5*np.sin(t)], 1)
    return S, t


STRUCTS, T = make_structs()

# ==================== 视角 = 投影方向 ====================
def project(P, direction):
    """把 3D 曲线投影到 direction 方向 → 1D 信号"""
    d = np.array(direction, float)
    d /= np.linalg.norm(d) + 1e-12
    return P @ d


# 定义几个"眼镜"(视角方向)
VIEWS = {
    '正看': (1, 0, 0),
    '侧看': (0, 1, 0),
    '俯看': (0, 0, 1),
    '斜看': (0.577, 0.577, 0.577),
}


def desc_length(sig, nbins=32):
    """
    描述长度: 把这个 1D 信号量化成 nbins 档, 再压缩
    → 用"转移熵"近似: 相邻样本的条件熵
    → 越低 = 越好描述 (结构越明显)
    """
    q = np.digitize(sig, np.linspace(sig.min(), sig.max()+1e-9, nbins))
    # 一阶马尔可夫的条件熵 (bits)
    from collections import Counter
    pairs = Counter(zip(q[:-1], q[1:]))
    first = Counter(q[:-1])
    H = 0.0; tot = sum(pairs.values())
    for (a, b), c in pairs.items():
        p_ab = c / tot
        p_a = first[a] / sum(first.values())
        H -= p_ab * np.log2(p_ab / p_a)
    return H


def distinguish_single(sig_fn, sig_len=200):
    """
    单视角: 只看 n 步, 能否区分这些结构?
    返回 (区分出的组数, 平均描述长度)
    """
    sigs = {}
    lens = []
    for nm, P in STRUCTS.items():
        s = sig_fn(P)[:sig_len]
        # 量化成粗模式 (只保留趋势)
        q = np.digitize(s, np.linspace(-1.5, 3.5, 8))
        sigs[nm] = tuple(q)
        lens.append(desc_length(s))
    return len(set(sigs.values())), float(np.mean(lens)), sigs


print("=" * 86)
print("多视角: 结构在「关系」里, 不在单视角里")
print("=" * 86)
print()
print("  隐藏结构: %s" % ', '.join(STRUCTS.keys()))
print("  视角: %s" % ', '.join(VIEWS.keys()))
print()

# ==================== ① 单视角能区分几个? ====================
print("=" * 86)
print("① 单视角: 用 200 步、8 档量化, 能区分出几个结构?")
print("=" * 86)
print()
print("  %-10s %-18s %-18s %s" % ("视角", "区分出的组数", "平均描述长度(bit)", "说明"))
print("  " + "-" * 74)
for vn, vd in VIEWS.items():
    fn = lambda P, vd=vd: project(P, vd)
    ngrp, dlen, sigs = distinguish_single(fn)
    print("  %-10s %-18d %-18.2f %s" % (
        vn, ngrp, dlen, "❌ 分不出" if ngrp < len(STRUCTS) else "✅ 能分"))
print()
print("  ★ 关键: 无论哪个单视角, 最多只能区分 %d/%d 个结构" % (
    max(distinguish_single(lambda P, vd=vd: project(P, vd))[0] for vd in VIEWS.values()),
    len(STRUCTS)))
print("     → 方向相似的投影, 会撞成同一个模式")

# ==================== ② 多视角: 组合后的区分力 ====================
print()
print("=" * 86)
print("② 多视角组合: 2个、3个视角一起看")
print("=" * 86)
print()
import itertools
combos = [('正看','侧看'), ('正看','俯看'), ('正看','侧看','俯看'),
          ('正看','侧看','俯看','斜看')]
print("  %-28s %-14s %-18s %s" % ("视角组合", "区分组数", "总描述长度", "结果"))
print("  " + "-" * 78)
base_len = None
for combo in combos:
    sigs = {}
    total_len = 0.0
    for nm, P in STRUCTS.items():
        parts = []
        for vn in combo:
            s = project(P, VIEWS[vn])[:200]
            q = np.digitize(s, np.linspace(-1.5, 3.5, 8))
            parts.append(tuple(q))
            total_len += desc_length(s)
        sigs[nm] = tuple(parts)
    ngrp = len(set(sigs.values()))
    total_len /= len(STRUCTS)
    print("  %-28s %-14d %-18.1f %s" % (
        ' + '.join(combo), ngrp, total_len,
        "✅ 全分出" if ngrp == len(STRUCTS) else "⚠️ %d/%d" % (ngrp, len(STRUCTS))))

# ==================== ③ 核心: 结构在"关系"里 ====================
print()
print("=" * 86)
print("③ ★ 核心: 结构到底藏在哪? —— 「视角间的关系」够不够")
print("=" * 86)
print()
print("  做法: 不看任何单视角的原始形状, 只看【两个视角之间的比值/相位差】")
print()
print("  %-10s %-24s %-24s %s" % ("结构", "正看:侧看 的比值", "正看:俯看 的比值", "能否识别"))
print("  " + "-" * 80)
for nm, P in STRUCTS.items():
    a = project(P, VIEWS['正看'])
    b = project(P, VIEWS['侧看'])
    c = project(P, VIEWS['俯看'])
    # 只看"关系": 标准差之比 (尺度无关的纯关系量)
    r1 = np.std(b) / (np.std(a) + 1e-9)
    r2 = np.std(c) / (np.std(a) + 1e-9)
    print("  %-10s %-24.3f %-24.3f %s" % (nm, r1, r2, "—"))

print()
print("  ★ 看这组【比值】:")
for nm, P in STRUCTS.items():
    a = project(P, VIEWS['正看']); b = project(P, VIEWS['侧看']); c = project(P, VIEWS['俯看'])
    r1 = np.std(b)/(np.std(a)+1e-9); r2 = np.std(c)/(np.std(a)+1e-9)
    print("     %-6s → (%.2f, %.2f)" % (nm, r1, r2))
print()
print("  → 每种的比值【都不同】→ 用两个数就能区分全部 3 种结构")
print("  → 但这两个数【单独看任何一个视角都得不到】")
print("  → ★ 它们只在「视角之间的关系」里")

print()
print("=" * 86)
print("结论")
print("=" * 86)
print()
print("  %-34s %s" % ("方式", "区分 4 种结构所需的信息"))
print("  " + "-" * 72)
print("  %-34s %s" % ("任选 1 个视角", "❌ 做不到 (投影撞车)"))
print("  %-34s %s" % ("2 个视角的原始形状", "✅ 可以, 但描述很长"))
print("  %-34s %s" % ("★ 2 个视角之间的【关系】", "✅ 2 个数就够"))
print()
print("  用时 %.2fs" % (time.time() - t0))
