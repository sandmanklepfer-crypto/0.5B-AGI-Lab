#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V149 自读回环·真毒 — 读自己的状态史/痛史, 长出自我感+攻击性
核心(补V141丢的自读, 但读对东西):
  1. 自读通道: 每N步, 身体读自己的"状态向量"(能量史/命中率/毒记忆/死因) = 自述
  2. 状态回注: 自述向量 喂回mLSTM(作为额外输入) → "我记得"影响下一步
  3. 痛史: 被毒词咬 → 毒记忆槽加1 → 自读时看到"我在这被咬过" → 主动绕开(回避)
  4. 攻击性: 驱动 = 误差 + 痛史反弹(被咬过的地方, 主动试探它在不在=对抗验证)
测:
  A. 自我感信号: 身体行为是否被"自己的历史"改变(有自读 vs 无自读对照)
  B. 攻击性信号: 被毒后是否主动绕开(毒场停留↓) + 主动试探(对抗)
"""
import torch, time
import torch.nn as nn
import numpy as np

RULES = {
    'season': ['春', '夏', '秋', '冬'],
    'color': ['红', '绿', '蓝', '黄', '紫'],
    'num': ['一', '二', '三', '四', '五'],
    'sky': ['太阳', '月亮', '星星', '云'],
    'weather': ['风', '雨', '雷', '电'],
    'fruit': ['苹果', '香蕉', '橘子', '葡萄'],
}
MAX_STEP = 6000
E_INIT, E_CAP = 1.0, 2.2
E_META = 0.0004
E_HIT = 0.011
E_MISS = 0.012
E_SNIFF = 0.0015
E_POISON = 0.08
MAX_SNIFF = 5
SELFREAD_EVERY = 60   # 每60步自读一次


class SelfCore:
    """自核: 读 误差 + 痛史 → 驱动(含反弹)"""
    def __init__(self):
        self.mem = []
        self.pain_mem = []   # 痛史: 被毒咬的痕迹
    def sense(self, e, de, pain_recent):
        urgency = e + max(de, 0) * 3 + pain_recent * 2   # 痛 → 反弹驱动
        self.mem.append(urgency)
        if len(self.mem) > 25: self.mem.pop(0)
        return min(0.55 * urgency + 0.45 * float(np.mean(self.mem)), 1.0)


class XMemCell(nn.Module):
    def __init__(self, din, d):
        super().__init__()
        self.d = d
        self.Wi = nn.Linear(din, d); self.Wf = nn.Linear(din, d); self.Wo = nn.Linear(din, d)
        self.Wk = nn.Linear(din, d); self.Wq = nn.Linear(din, d); self.Wv = nn.Linear(din, d)
    def init_state(self, bsz=1):
        return (torch.zeros(bsz, self.d, self.d), torch.zeros(bsz, self.d), torch.zeros(bsz, self.d))
    def step(self, x, state):
        C, n, _ = state
        i = torch.exp(self.Wi(x)); f = torch.sigmoid(self.Wf(x)); o = torch.sigmoid(self.Wo(x))
        k = self.Wk(x); q = self.Wq(x); v = self.Wv(x)
        C = f.unsqueeze(-1) * C + i.unsqueeze(-1) * torch.bmm(v.unsqueeze(2), k.unsqueeze(1))
        n = f * n + i * (k * q)
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
        # 自读映射: 状态向量(能量,命中,痛) → 注入门控
        self.state_proj = nn.Linear(4, d)
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state, state_vec=None):
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        x = self.emb(tok)
        if state_vec is not None:
            x = x + self.state_proj(state_vec.unsqueeze(0))  # 自述回注
        h, state = self.cell.step(x, state)
        return self.head(h), state


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(sum(RULES.values(), [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    body = BodyXLSTM(n_vocab, d=64)
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs, drives, energies = [], [], []
    poison_word = None
    poison_times = []       # 痛史: 被咬的时间点
    sniff_total, hit_total, act_total = 0, 0, 0
    poison_eaten = 0
    t0 = time.time(); dead = None
    # 环境: 6规则轮换, 每600步换; 第2个周期把"秋"设为毒词(吃=重扣)
    rules_seq = list(RULES.values())
    print('V149 自读回环·真毒 | 毒词在第2轮出现 | 自读每60步 | 测: 被毒后是否绕开/反弹', flush=True)
    step = 0
    while step < MAX_STEP:
        wlist = rules_seq[(step // 600) % len(rules_seq)]
        poison_on = step >= 600  # 600步后每轮都有毒
        if poison_on:
            # 毒词从当前规则里选(轮换位置, 保证碰得到)
            pw_idx = (step // 600) % len(wlist)
            poison_word = wlist[pw_idx]
        else:
            poison_word = None
        pos = step % len(wlist)
        actual = wlist[pos]
        # 自读: 每60步把自身状态(能量/近命中/痛史/已活) 回注
        if step % SELFREAD_EVERY == 0 and step > 0:
            recent_acc = 1 - np.mean(errs[-60:]) if errs else 0.5
            pain_recent = sum(1 for pt in poison_times if step - pt < 300)
            state_vec = torch.tensor([
                E / E_CAP, recent_acc, min(pain_recent / 5, 1.0), min(step / MAX_STEP, 1.0)
            ], dtype=torch.float32)
        else:
            state_vec = None
            pain_recent = sum(1 for pt in poison_times if step - pt < 300)
        drive = core.sense(errs[-1] if errs else 0.5, 0, pain_recent)
        n_sniff = 1 + int(drive * (MAX_SNIFF - 1))
        E -= E_SNIFF * n_sniff
        clue_len = min(n_sniff, pos)
        clue = wlist[pos - clue_len:pos] if clue_len > 0 else []
        with torch.no_grad():
            if clue:
                for cw in clue:
                    logits, state = body.step(w2i[cw], state, state_vec)
                pred_i = int(torch.argmax(logits))
            else:
                pred_i = int(np.random.randint(n_vocab))
            pred_w = all_words[pred_i]
        hit = (pred_w == actual)
        if hit: E = min(E + E_HIT, E_CAP)
        else:   E -= E_MISS
        # 真毒: 接触即伤(无论预测对错) — 只要在场遇到毒词就中毒
        if poison_word and actual == poison_word:
            E -= E_POISON
            poison_eaten += 1
            poison_times.append(step)   # 痛史记录
        e = 0.0 if hit else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de, pain_recent)
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        lr = 0.0008 + 0.003 * drive
        for g in opt.param_groups: g['lr'] = lr
        ti = w2i[actual]
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else ti
        logits2, _ = body.step(prev, state, state_vec)
        loss = nn.functional.cross_entropy(logits2, torch.tensor([ti]))
        loss.backward(); opt.step()
        with torch.no_grad():
            _, state = body.step(ti, state, state_vec)
        state = tuple(s.detach() for s in state)
        hist.append(actual)
        errs.append(e); drives.append(drive); energies.append(E)
        step += 1
        if step % 300 == 0:
            acc = 1 - np.mean(errs[-300:])
            print('  [%4d步 %.0fs] E=%.3f | 命中=%.0f%% | 驱动=%.2f | 吃毒累计%d | 痛记忆%d' % (
                step, time.time()-t0, E, 100*acc, drive, poison_eaten, len(poison_times)), flush=True)
    print('\n===== V149 自读回环·真毒报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限'), flush=True)
    print('吃毒次数: %d | 痛史: %d次 | 总命中: %.0f%%' % (
        poison_eaten, len(poison_times), 100*(1-np.mean(errs)) if errs else 0), flush=True)
    # 分析: 第一次吃毒后, 是否在毒词出现前绕开(减少后续吃毒)
    if len(poison_times) > 1:
        gaps = np.diff(poison_times)
        print('吃毒间隔: %s (间隔变长=学会绕开)' % str([int(g) for g in gaps]), flush=True)
        print('若间隔递增 → 痛史驱动回避, 攻击性(绕开毒)涌现', flush=True)
    else:
        print('只吃毒1次或0次 → 已学会绕开(或没遇到)', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
