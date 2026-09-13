#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V143 自持环·顶级肉(xLSTM/mLSTM矩阵记忆) — 在噪声世界上自持
升级 vs V142:
  1. 肉: 标准LSTM(标量记忆) → xLSTM风格mLSTM(矩阵记忆C d×d,
     协方差更新 C=fC+i·outer(v,k), 能存规律结构非只存最近上下文)
  2. 世界: 纯周期 → 周期+10%随机噪声(永远有不可预测 → 自核永不满足
     → 驱动永不归零 → "永饥渴"从世界涌现, 不用等突变)
  3. 更久: 5000步
架构不变: 世界/肉(会学)/隔离自核(纯e,Δe)/能量飞轮
"""
import torch, time
import torch.nn as nn
import numpy as np

WORLDS = [
    ['苹果', '香蕉', '橘子', '葡萄'],
    ['猫', '狗', '鸟', '鱼', '兔'],
    ['春', '夏', '秋', '冬'],
    ['红', '绿', '蓝', '黄', '紫', '橙'],
    ['一', '二', '三', '四', '五'],
    ['太阳', '月亮', '星星', '云'],
    ['风', '雨', '雷', '电'],
    ['山', '河', '湖', '海', '泉'],
    ['金', '木', '水', '火', '土'],
    ['东', '南', '西', '北'],
]
NOISE = 0.10         # 10% 随机噪声(永不满足之源)
MUTATE_EVERY = 100
MAX_STEP = 5000
E_INIT, E_CAP = 1.0, 2.0
E_META = 0.0003
E_TRUE = 0.004
E_FALSE = 0.0035     # 维持线~45%: 90%对(抓规律)+10%错(扛噪声)净回血

class SelfCore:
    def __init__(self):
        self.mem = []
    def sense(self, e, de):
        urgency = e + max(de, 0) * 3
        self.mem.append(urgency)
        if len(self.mem) > 25: self.mem.pop(0)
        return min(0.55 * urgency + 0.45 * float(np.mean(self.mem)), 1.0)

class XMemCell(nn.Module):
    """xLSTM式 mLSTM 单元: 矩阵记忆(协方差更新), 顶级LSTM核心"""
    def __init__(self, din, d):
        super().__init__()
        self.d = d
        self.Wi = nn.Linear(din, d); self.Wf = nn.Linear(din, d); self.Wo = nn.Linear(din, d)
        self.Wk = nn.Linear(din, d); self.Wq = nn.Linear(din, d); self.Wv = nn.Linear(din, d)
    def init_state(self, bsz=1):
        d = self.d
        return (torch.zeros(bsz, d, d), torch.zeros(bsz, d), torch.zeros(bsz, d))
    def step(self, x, state):
        C, n, h_prev = state
        i = torch.exp(self.Wi(x))              # exp 门控(无上界, 可选大记忆)
        f = torch.sigmoid(self.Wf(x))
        o = torch.sigmoid(self.Wo(x))
        k = self.Wk(x); q = self.Wq(x); v = self.Wv(x)
        C = f.unsqueeze(-1) * C + i.unsqueeze(-1) * torch.bmm(v.unsqueeze(2), k.unsqueeze(1))
        n = f * n + i * (k * q)                # 归一化计数
        num = torch.bmm(C, q.unsqueeze(2)).squeeze(2)
        denom = torch.maximum(n.norm(dim=1, keepdim=True), torch.ones_like(n.norm(dim=1, keepdim=True)))
        h = o * num / denom
        return h, (C, n, h)

class BodyXLSTM(nn.Module):
    def __init__(self, n_vocab, d=64):
        super().__init__()
        self.emb = nn.Embedding(n_vocab, d)
        self.cell = XMemCell(d, d)
        self.head = nn.Linear(d, n_vocab)
    def init_state(self):
        return self.cell.init_state()
    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor):
            tok = torch.tensor([tok])
        x = self.emb(tok)
        h, state = self.cell.step(x, state)
        return self.head(h), state

def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(sum(WORLDS, [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    body = BodyXLSTM(n_vocab, d=64)
    opt = torch.optim.Adam(body.parameters(), lr=0.003)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs, drives, energies = [], [], []
    t0 = time.time(); dead = None
    print('V143b xLSTM自持环·纯自持版 | mLSTM矩阵记忆d=64 | vocab=%d | 世界%d套+%d%%噪声 | 5000步' % (
        n_vocab, len(WORLDS), int(NOISE*100)), flush=True)
    step = 0
    while step < MAX_STEP:
        wlist = WORLDS[(step // MUTATE_EVERY) % len(WORLDS)]
        if step % MUTATE_EVERY == 0:
            print('  [突变] 步%d 世界: %s' % (step, '/'.join(wlist)), flush=True)
        # 世界: 90%周期 + 10%噪声(永不满足之源)
        if np.random.rand() < NOISE:
            actual = all_words[np.random.randint(n_vocab)]
        else:
            actual = wlist[step % len(wlist)]
        # 预测(带着矩阵记忆时序流)
        if len(hist) >= 1:
            with torch.no_grad():
                logits, state = body.step(w2i[hist[-1]], state)
            pred_i = int(torch.argmax(logits))
            pred_w = all_words[pred_i]
        else:
            pred_w = all_words[np.random.randint(n_vocab)]
        e = 0.0 if pred_w == actual else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de)
        if e == 0: E = min(E + E_TRUE, E_CAP)
        else:      E -= E_FALSE
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        # 在线学习(lr由驱动调制, 饿→学更狠)
        lr = 0.001 + 0.004 * drive
        for g in opt.param_groups: g['lr'] = lr
        if len(hist) >= 1:
            ti = w2i[actual]
            opt.zero_grad()
            logits2, _ = body.step(w2i[hist[-1]], state)  # 同一流带梯度
            loss = nn.functional.cross_entropy(logits2, torch.tensor([ti]))
            loss.backward(); opt.step()
            with torch.no_grad():
                _, state = body.step(ti, state)
            state = tuple(s.detach() for s in state)
        hist.append(actual)
        errs.append(e); drives.append(drive); energies.append(E)
        step += 1
        if step % 500 == 0:
            acc = 1 - np.mean(errs[-500:])
            print('  [%4d步 %.0fs] E=%.3f | 正确率(近500)=%.0f%% 驱动=%.2f 记忆C范数=%.1f' % (
                step, time.time()-t0, E, 100*acc, drive,
                float(state[0].norm()) if state[0] is not None else 0), flush=True)
    print('\n===== V143b xLSTM自持环·纯自持版报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限(环自持!)'), flush=True)
    for seg in range(max(1, step // 500)):
        s, e2 = seg*500, min((seg+1)*500, step)
        print('  段%d(步%d-%d): 正确率=%.0f%% 平均E=%.2f 驱动=%.2f' % (
            seg+1, s, e2, 100*(1-np.mean(errs[s:e2])), np.mean(energies[s:e2]),
            np.mean(drives[s:e2])), flush=True)
    print('末能量: %.3f | 末驱动: %.3f (噪声世界>0=永饥渴) | 历史: %d步' % (E, drive, len(hist)), flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
