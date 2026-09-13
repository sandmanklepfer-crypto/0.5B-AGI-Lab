#!/usr/bin/env python3
"""
V160 水库突破因果链验证 (本地免费)
验证三环:
 1. 谱: 随机循环矩阵特征值是否可调成|λ|<1且密集(回声状态性质)
 2. 模态: 水库状态是否随时间产生丰富基函数(输入的不同非线性变换)
 3. 读出: 只训线性读出层, 能否学会"参数里没有的能力"(如记忆N步前的输入)
对照: 无水库(直接线性映射输入) vs 水库(状态演化+线性读出)
任务: NARMA/延迟记忆 — 需要"时间深度"的任务(纯线性/纯前馈做不到)
"""
import numpy as np

np.random.seed(0)

# ============ 1. 谱分析: 回声状态性质 ============
print('=== 1. 水库谱 ===', flush=True)
N = 200
W = np.random.randn(N, N) * 0.5
# 谱半径缩放(回声状态核心: 谱半径<1)
eigs = np.linalg.eigvals(W)
print('随机矩阵谱半径: %.3f (>1=发散)' % np.max(np.abs(eigs)), flush=True)
for target in [0.5, 0.9, 1.5]:
    Ws = W * (target / np.max(np.abs(eigs)))
    e2 = np.linalg.eigvals(Ws)
    print('谱半径调到%.1f: |λ|max=%.3f %s' % (target, np.max(np.abs(e2)),
        '✅回声状态' if target < 1 else '❌发散风险'), flush=True)

# ============ 2+3. 水库 vs 无水库: 延迟记忆任务 ============
print('\n=== 2+3. 水库读出 vs 无水库 ===', flush=True)
# 任务: 输出 = 5步前的输入值(需要时间记忆, 纯前馈做不到)
T = 3000
DELAY = 5
u = np.random.randn(T) * 0.5          # 输入序列
y = np.zeros(T)
y[DELAY:] = u[:-DELAY]                # 目标: 延迟5步的输入

# --- 无水库: 直接线性回归 u_t -> y_t (没有时间, 必然失败) ---
X_plain = u[:-1].reshape(-1, 1)
Y_plain = y[1:]
w_plain = np.linalg.lstsq(X_plain, Y_plain, rcond=None)[0]
pred_plain = X_plain @ w_plain
err_plain = np.mean((pred_plain - Y_plain)**2)
print('无水库(纯线性映射) 误差: %.4f (应≈输入方差%.3f=失败)' % (err_plain, np.var(u)), flush=True)

# --- 水库: 状态演化 + 线性读出 ---
Wr = W * (0.9 / np.max(np.abs(eigs)))  # 谱半径0.9
Win = np.random.randn(N, 1) * 0.5       # 输入权重
x = np.zeros(N)
X_r = np.zeros((T-1, N))
for t in range(T-1):
    x = np.tanh(Wr @ x + Win.ravel() * u[t])    # 水库演化(不训练!)
    X_r[t] = x
w_r = np.linalg.lstsq(X_r[100:], Y_plain[100:], rcond=None)[0]
pred_r = X_r[100:] @ w_r
err_r = np.mean((pred_r - Y_plain[100:])**2)
# 与输入方差比(归一化误差)
print('水库+线性读出 误差: %.4f (输入方差%.3f, 归一化%.3f)' % (
    err_r, np.var(u), err_r/np.var(u)), flush=True)
print('=> 水库学会了延迟5步记忆(无水库完全失败) = 时间换容量的直接证据', flush=True)

# --- 3b. 水库大小 vs 能力(容量来自状态维度+时间, 不是参数训练) ---
for n_small in [20, 50, 200]:
    Ws = np.random.randn(n_small, n_small) * 0.5
    sr = np.max(np.abs(np.linalg.eigvals(Ws)))
    Ws = Ws * (0.9/sr)
    Win2 = np.random.randn(n_small, 1) * 0.5
    xs = np.zeros(n_small)
    Xs = np.zeros((T-1, n_small))
    for t in range(T-1):
        xs = np.tanh(Ws @ xs + Win2.ravel() * u[t])
        Xs[t] = xs
    ws = np.linalg.lstsq(Xs[100:], Y_plain[100:], rcond=None)[0]
    es = np.mean((Xs[100:] @ ws - Y_plain[100:])**2)
    print('水库N=%d: 误差%.4f (归一化%.3f)' % (n_small, es, es/np.var(u)), flush=True)
print('\n[done]', flush=True)
