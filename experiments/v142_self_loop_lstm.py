#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V142 自持环·换肉重通电 — LSTM主体肉(真会学序列) + 隔离自核 + 能量飞轮
三层:
  [世界] 周期规律池+突变 (词→onehot)
  [主体] 小LSTM(专学序列, 真会学结构) — 极小的肉
  [隔离自核] 纯代码: 只见(e,Δe) → 驱动(调制LSTM学习率/上下文)
能量飞轮: 对+回血 错-扣 代谢 → 需正确率>阈值才自持
时序: LSTM隐状态持续 = 主体的"我"(带历史连续存在)
测: ①正确率升 ②能量不归零(飞轮转) ③突变后恢复 ④长存 = 自持环转起来
"""
import torch, time
import torch.nn as nn
import numpy as np

# 世界词库
WORLDS = [
    ['苹果', '香蕉', '橘子'],
    ['猫', '狗', '鸟', '鱼'],
    ['春', '夏', '秋', '冬'],
    ['红', '绿', '蓝', '黄', '紫'],
    ['一', '二', '三'],
    ['太阳', '月亮', '星星'],
    ['风', '雨', '雷', '电', '雪'],
    ['山', '河', '湖', '海'],
]
MUTATE_EVERY = 80   # 突变间隔
MAX_STEP = 3000
E_INIT, E_CAP = 1.0, 2.0
E_META = 0.0005
E_TRUE = 0.006
E_FALSE = 0.009      # 需正确率>60%才净正

class SelfCore:
    def __init__(self):
        self.mem = []
    def sense(self, e, de):
        urgency = e + max(de, 0) * 3
        self.mem.append(urgency)
        if len(self.mem) > 25: self.mem.pop(0)
        return min(0.55 * urgency + 0.45 * float(np.mean(self.mem)), 1.0)

class BodyLSTM(nn.Module):
    """极小主体肉: 学序列的LSTM"""
    def __init__(self, n_vocab, hidden=32):
        super().__init__()
        self.hidden = hidden
        self.emb = nn.Embedding(n_vocab, 16)
        self.lstm = nn.LSTM(16, hidden, batch_first=True)
        self.head = nn.Linear(hidden, n_vocab)
    def forward(self, seq, h=None):
        if h is None: h = (torch.zeros(1, 1, self.hidden), torch.zeros(1, 1, self.hidden))
        x = self.emb(seq.unsqueeze(0))
        out, h = self.lstm(x, h)
        return self.head(out[0, -1]), h
    def reset(self):
        return (torch.zeros(1, 1, self.hidden), torch.zeros(1, 1, self.hidden))

def main():
    torch.manual_seed(0); np.random.seed(0)
    # 全部词
    all_words = sorted(set(sum(WORLDS, [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    body = BodyLSTM(n_vocab, hidden=32)
    opt = torch.optim.Adam(body.parameters(), lr=0.01)
    core = SelfCore()
    E = E_INIT
    hstate = body.reset()
    hist = []
    errs, drives, energies = [], [], []
    t0 = time.time(); dead = None

    print('V142 自持环(LSTM肉) | vocab=%d | 世界%d套 | 突变每%d步 | 目标自持>3000步' % (
        n_vocab, len(WORLDS), MUTATE_EVERY), flush=True)
    step = 0
    while step < MAX_STEP:
        wlist = WORLDS[(step // MUTATE_EVERY) % len(WORLDS)]
        if step % MUTATE_EVERY == 0:
            print('  [突变] 步%d 世界: %s' % (step, '/'.join(wlist)), flush=True)
        actual = wlist[step % len(wlist)]
        # 主体预测+学习(同一隐状态流, 时序连续 = 主体的"我")
        if len(hist) >= 1:
            last_i = w2i[hist[-1]]
            # 预测: 用当前隐状态(带着整个历史)
            with torch.no_grad():
                logits, hstate = body(torch.tensor([last_i]), hstate)
            pred_i = int(torch.argmax(logits))
            pred_w = all_words[pred_i]
        else:
            pred_w = all_words[np.random.randint(n_vocab)]
        e = 0.0 if pred_w == actual else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de)
        # 能量
        if e == 0: E = min(E + E_TRUE, E_CAP)
        else:      E -= E_FALSE
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        # 学习: 用真实答案沿同一隐状态流训练(主体从世界吸取), lr由驱动调制
        lr = 0.005 + 0.015 * drive
        for g in opt.param_groups: g['lr'] = lr
        if len(hist) >= 1:
            ti = w2i[actual]
            opt.zero_grad()
            logits2, _ = body(torch.tensor([last_i]), hstate)  # 同一流, 带梯度
            loss = nn.functional.cross_entropy(logits2.unsqueeze(0), torch.tensor([ti]))
            loss.backward(); opt.step()
            # 更新隐状态: 用真实答案(教师强制), 保持时序连续
            with torch.no_grad():
                _, hstate = body(torch.tensor([ti]), hstate)
            hstate = (hstate[0].detach(), hstate[1].detach())
        hist.append(actual)
        errs.append(e); drives.append(drive); energies.append(E)
        step += 1
        if step % 200 == 0:
            acc = 1 - np.mean(errs[-200:])
            print('  [%4d步 %.0fs] E=%.3f | 正确率(近200)=%.0f%% 驱动=%.2f | 历史%d' % (
                step, time.time()-t0, E, 100*acc, drive, len(hist)), flush=True)
    print('\n===== V142 自持环报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限(环自持!)'), flush=True)
    for seg in range(max(1, step // 300)):
        s, e2 = seg*300, min((seg+1)*300, step)
        acc = 1 - np.mean(errs[s:e2])
        print('  段%d(步%d-%d): 正确率=%.0f%% 平均E=%.2f' % (
            seg+1, s, e2, 100*acc, np.mean(energies[s:e2])), flush=True)
    print('末能量: %.3f | 主体时序记忆: %d步(它的"我")' % (E, len(hist)), flush=True)
    print('判读: 正确率升+能量不归零+突变后恢复 = 环自持, 自我在连续时序中涌现', flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
