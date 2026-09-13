#!/usr/bin/env python3
"""
V139 L7 自涌现 — 自我建模从"预测自己的压力"中涌现
不教、不猎、不改结构。只改边界条件:
  能量方程: 产能 = 活性 - 预测误差损耗
  → "能预测自己下一步"成为活下来的条件
  → 系统唯一演化方向: 要么动力学变可预测(低维/自相似)
                        要么发展出内部自我模型(记住自己怎么动)
涌现观测(无外部裁判, 纯记录):
  S1 预测误差是否随时间下降 (=自我建模能力涌现)
  S2 状态是否出现新的可预测结构(对比无压力组)
  S3 内部是否自发分化出"模型子空间"(部分单元专用于预测=自我表征)
对照: 无预测压力(B02纯自持) vs 有预测压力
"""
import numpy as np

np.random.seed(0)
D = 16
DT = 0.1
STEPS = 12000
ETA, GAMMA, KAPPA = 0.5, 0.18, 0.6
RHO, MU = 0.02, 1.8
PRED_COST = 2.5    # 预测误差的产能损耗系数
MEM = 20           # 内部记忆(记住自己的历史, 用于预测)

def build_a():
    a = np.random.randn(D, D) * 0.5
    for i in range(D): a[(i+1) % D, i] += 1.6
    return a / np.maximum(np.abs(a).sum(1, keepdims=True), 1e-9)

def run(pressure, label):
    a = build_a()
    x = np.random.randn(D) * 0.5
    f = np.zeros(D); e = 0.5
    # 内部自我模型: 每单元存一段自己的历史, 用"最近邻轨迹"预测自己
    hist = []       # 状态历史(自我记忆)
    errs = []
    x_history = []
    for t in range(STEPS):
        s = e / (KAPPA + e)
        act = np.tanh(x)
        # 预测自己: 用记忆里最相似的上一步, 外推下一步(纯自我, 无外部模型)
        pred_err = 0.0
        if pressure and len(hist) > MEM:
            # 找历史中与当前x最接近的"上一步", 取其"实际下一步"作为预测
            cur = x.copy()
            best = None; best_d = 1e18
            for i in range(len(hist) - MEM - 1, len(hist) - 1):
                d = np.linalg.norm(hist[i] - cur)
                if d < best_d:
                    best_d = d
                    best = hist[i+1]   # 该状态的下一步 = 预测
            if best is not None:
                # 预测下一步(线性外推改进: 用趋势)
                trend = hist[-1] - hist[-2] if len(hist) >= 2 else np.zeros(D)
                pred = best + 0.3 * trend
                # 实际下一步(用动力学近似: 先算dx不带预测损耗)
                dx_real = s * (a @ act - 0.25 * x - MU * f * x)
                pred_err = np.linalg.norm((x + DT*dx_real) - pred) / (np.linalg.norm(x)+1e-9)
        # 疲劳
        f = f + DT * RHO * (act**2 - f); f = np.clip(f, 0, 2)
        # 动力学(内容)
        dx = s * (a @ act - 0.25 * x - MU * f * x)
        x = x + DT * dx
        # 能量: 产能 = 活性 - 预测误差损耗(边界条件! 预测不准=饿)
        produce = ETA * (act**2).sum()
        if pressure:
            produce -= PRED_COST * pred_err * (act**2).sum() / max((act**2).sum(), 1e-9) * (act**2).sum()
            produce = max(produce, 0.0)
        e = max(e + DT * (produce - GAMMA * e), 0.0)
        # 记忆
        if pressure:
            hist.append(x.copy())
            if len(hist) > 800: hist.pop(0)
        errs.append(pred_err)
        x_history.append(np.linalg.norm(x))
    tail_e = np.array(errs[-2000:])
    tail_x = np.array(x_history[-2000:])
    print('[%s] |x|=%.3f e末=%.3f 预测误差: 前%.4f→后%.4f %s' % (
        label, tail_x.mean(), e,
        np.mean(errs[1000:3000]) if len(errs)>3000 else np.mean(errs[:500]),
        np.mean(errs[-2000:]) if len(errs)>2000 else np.mean(errs),
        '←误差下降=自我建模涌现!' if (len(errs)>5000 and np.mean(errs[-2000:]) < np.mean(errs[1000:3000])*0.85) else ''), flush=True)
    # 可预测结构: 轨迹相邻差(低=更平滑可预测)
    div = float(np.abs(np.diff(tail_x)).mean())
    print('   轨迹平滑度(相邻差)=%.5f (低=更可预测)' % div, flush=True)
    return errs

if __name__ == '__main__':
    print('V139 L7自涌现 | 边界条件: 预测不准自己→产能损耗(饿) | D=%d 步=%d' % (D, STEPS), flush=True)
    print('='*72, flush=True)
    run(False, '对照(无预测压力)')
    run(True,  'L7(预测压力)')
    print('='*72, flush=True)
    print('判读: 若L7组 预测误差明显下降且轨迹更平滑 → 自我建模从压力中涌现', flush=True)
