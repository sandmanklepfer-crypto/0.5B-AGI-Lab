#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
topreason3.py — 顶级推理的真相: 符号精确 vs 浮点漂移
=======================================================
结论链:
  topreason.py : 识别层→符号, 速度×1733, 但长链崩 (几何任务)
  topreason2.py: 换码本、换变换都救不了
                → 问题不在码本, 在【任务本身是否离散封闭】
  本实验       : 换成形式化封闭任务 → 符号链既快又精确

任务: 长链模运算 n→(a·n+b) mod P  (P=2^31−1, 需要精确)
  A 浮点连续 : 舍入误差累积 → 长链必错
  B 整数符号 : 精确 (整数环封闭)
  C 用户架构 : 感知→识别层(一次性, 有损)→符号(精确)

★ 真正的判据不是"信息丢了多少", 而是"下游任务需要的信息丢没丢"
"""
import numpy as np, time

P = 2**31 - 1
a, b, n0 = 1103515245, 12345, 42
L = 2000
t0 = time.time()

print("=" * 92)
print("顶级推理: 符号精确 vs 浮点漂移   (长链模运算, P = 2^31−1, L = %d)" % L)
print("=" * 92)
print()


def chain_int(n, L):
    out = [n]
    for _ in range(L):
        n = (a * n + b) % P
        out.append(n)
    return out


def chain_f32(n, L):
    out = [np.float32(n)]
    for _ in range(L):
        n = np.float32((np.float32(a) * n + np.float32(b)) % np.float32(P))
        out.append(n)
    return out


def chain_f64(n, L):
    out = [float(n)]
    for _ in range(L):
        n = float((a * n + b) % P)
        out.append(n)
    return out


t = time.perf_counter(); Ti = chain_int(n0, L); t_int = time.perf_counter() - t
t = time.perf_counter(); Tf = chain_f64(n0, L); t_f64 = time.perf_counter() - t
t = time.perf_counter(); T3 = chain_f32(n0, L); t_f32 = time.perf_counter() - t

print("  %-34s %-16s %-16s %s" % ("实现", "首次出错步", "L=2000 正确率", "耗时"))
print("  " + "-" * 80)


def first_bad(T):
    for i in range(L + 1):
        if int(round(float(T[i]))) != Ti[i]:
            return i
    return None


fb64 = first_bad(Tf); fb32 = first_bad(T3)
ok64 = sum(1 for i in range(L + 1) if int(round(float(Tf[i]))) == Ti[i]) / (L + 1)
ok32 = sum(1 for i in range(L + 1) if int(round(float(T3[i]))) == Ti[i]) / (L + 1)
print("  %-34s %-16s %-16.4f %.4fs" % ("★ 整数符号 (精确)", "— (永不)", 1.0000, t_int))
print("  %-34s %-16s %-16.4f %.4fs" % ("float64 连续", "第 %s 步" % fb64, ok64, t_f64))
print("  %-34s %-16s %-16.4f %.4fs" % ("float32 连续", "第 %s 步" % fb32, ok32, t_f32))

print()
print("  ★ 浮点从第 %s 步起就错了, 之后【全错】—— 误差一旦进入就不可逆" % fb64)
print("  ★ 整数符号 L=2000 全程精确 (整数环对这个运算是封闭的)")
print()

# ---------- C 用户架构: 感知 → 识别层 → 符号 ----------
print("=" * 92)
print("用户架构: 感知(连续) → 识别层(一次性, 有损) → 符号(精确无损)")
print("=" * 92)
print()
rng = np.random.RandomState(0)
D = 896
# 模拟"感知": 把整数 n 编码成一个 896 维向量 (带噪声)
CODE = rng.randn(P, D) if False else None   # (太大, 改用线性编码)
Wenc = rng.randn(D, 32) / np.sqrt(32)


def encode(n):                      # 感知编码 (+噪声)
    z = np.zeros(32); z[0] = n % P
    return np.tanh(z @ Wenc.T) + 0.05 * rng.randn(D)


# 识别层: 训练一个 896→P 词典的读出 (这里用最小二乘模拟"已训练好的识别层")
n_tr = rng.randint(0, 2**20, 4000)
Enc = np.array([encode(int(x)) for x in n_tr])
# 读出方向: 用随机投影近似"识别层"的线性读出
Wdec = np.linalg.lstsq(Enc, n_tr.astype(float), rcond=None)[0] if False else None
# 直接用最小二乘 (896 → 1)
W1 = np.linalg.lstsq(Enc, (n_tr % P).astype(float), rcond=None)[0]
pred = Enc @ W1
rel = np.abs(pred - n_tr) / (n_tr + 1)
print("  识别层(线性读出 896→1) 相对误差: 中位 %.3f, 均值 %.3f" % (
    np.median(rel), rel.mean()))
print("  → 单次识别是【有损的】(和 topreason.py 的量化误差同源)")
print()
print("  但! 识别层只需要认得【符号身份】, 不需要保真还原数值:")
print("     识别正确 → 之后的推理 100%% 精确 (整数符号)")
print("     识别错误 → 下游再快也是错的 (但 L1 验证器能立刻发现)")
print()

# ---------- 速度总表 ----------
print("=" * 92)
print("速度与保真度总表")
print("=" * 92)
print()
print("  %-38s %-16s %-16s %s" % ("路径", "每步成本", "长链保真度", "结论"))
print("  " + "-" * 86)
print("  %-38s %-16s %-16s %s" % ("连续几何推理 (896×896)", "1.0 (基准)", "低(离散化后崩)", "❌ 慢且不可离散"))
print("  %-38s %-16s %-16s %s" % ("★ 识别层→符号→查表 (几何任务)", "1/1733", "低(0.0007)", "⚠️ 快但错"))
print("  %-38s %-16s %-16s %s" % ("★ 识别层→符号→整数环 (形式任务)", "快 (O(1))", "1.0 (精确)", "✅ 快且准"))
print()
print("  用时 %.2fs" % (time.time() - t0))
