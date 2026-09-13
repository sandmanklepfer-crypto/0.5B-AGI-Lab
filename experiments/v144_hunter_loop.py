#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V144 猎食式自持环 — 攻击性从世界结构涌现(不写死)
世界=猎场: 每步只给线索(前缀), 不自动给答案。主体必须主动猜才得食。
  猜对→大回血(+0.010) | 猜错→扣(-0.006) | 嗅探(多要线索)→耗(-0.002)
  不主动→纯代谢耗死 → 被动必死, 攻击是唯一活路
自核(隔离, 只见e,Δe)输出驱动 → 控制出击: 饿→多嗅探+敢猜, 饱→少嗅探
肉: mLSTM(矩阵记忆, 纯周期世界, 单测攻击性)
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
]
MUTATE_EVERY = 120
MAX_STEP = 4000
E_INIT, E_CAP = 1.0, 2.5
E_META = 0.0003
E_HIT = 0.018
E_MISS = 0.006
E_SNIFF = 0.001
MAX_SNIFF = 6


class SelfCore:
    def __init__(self):
        self.mem = []

    def sense(self, e, de):
        urgency = e + max(de, 0) * 3
        self.mem.append(urgency)
        if len(self.mem) > 25:
            self.mem.pop(0)
        return min(0.55 * urgency + 0.45 * float(np.mean(self.mem)), 1.0)


class XMemCell(nn.Module):
    def __init__(self, din, d):
        super().__init__()
        self.d = d
        self.Wi = nn.Linear(din, d)
        self.Wf = nn.Linear(din, d)
        self.Wo = nn.Linear(din, d)
        self.Wk = nn.Linear(din, d)
        self.Wq = nn.Linear(din, d)
        self.Wv = nn.Linear(din, d)

    def init_state(self, bsz=1):
        return (torch.zeros(bsz, self.d, self.d), torch.zeros(bsz, self.d), torch.zeros(bsz, self.d))

    def step(self, x, state):
        C, n, _ = state
        i = torch.exp(self.Wi(x))
        f = torch.sigmoid(self.Wf(x))
        o = torch.sigmoid(self.Wo(x))
        k = self.Wk(x)
        q = self.Wq(x)
        v = self.Wv(x)
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

    def init_state(self):
        return self.cell.init_state()

    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor):
            tok = torch.tensor([tok])
        x = self.emb(tok)
        h, state = self.cell.step(x, state)
        return self.head(h), state


def main():
    torch.manual_seed(0)
    np.random.seed(0)
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
    sniff_total, hit_total, act_total = 0, 0, 0
    t0 = time.time()
    dead = None
    print('V144b 猎食环 | 能量账修正(猎物更肥 侦察更廉)', flush=True)
    step = 0
    while step < MAX_STEP:
        wlist = WORLDS[(step // MUTATE_EVERY) % len(WORLDS)]
        if step % MUTATE_EVERY == 0:
            print('  [换猎场] 步%d 猎物: %s' % (step, '/'.join(wlist)), flush=True)
        pos = step % len(wlist)
        actual = wlist[pos]
        drive = core.sense(errs[-1] if errs else 0.5, 0)
        n_sniff = 1 + int(drive * (MAX_SNIFF - 1))
        E -= E_SNIFF * n_sniff
        clue_len = min(n_sniff, pos)
        clue = wlist[pos - clue_len:pos] if clue_len > 0 else []
        with torch.no_grad():
            if clue:
                for cw in clue:
                    logits, state = body.step(w2i[cw], state)
                pred_i = int(torch.argmax(logits))
            else:
                pred_i = int(np.random.randint(n_vocab))  # 无线索, 盲猜
            pred_w = all_words[pred_i]
        hit = (pred_w == actual)
        if hit:
            E = min(E + E_HIT, E_CAP)
        else:
            E -= E_MISS
        act_total += 1
        sniff_total += n_sniff
        hit_total += hit
        e = 0.0 if hit else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de)
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        lr = 0.001 + 0.004 * drive
        for g in opt.param_groups:
            g['lr'] = lr
        ti = w2i[actual]
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else ti
        logits2, _ = body.step(prev, state)
        loss = nn.functional.cross_entropy(logits2, torch.tensor([ti]))
        loss.backward()
        opt.step()
        with torch.no_grad():
            _, state = body.step(ti, state)
        state = tuple(s.detach() for s in state)
        hist.append(actual)
        errs.append(e)
        drives.append(drive)
        energies.append(E)
        step += 1
        if step % 400 == 0:
            acc = 1 - np.mean(errs[-400:])
            print('  [%4d步 %.0fs] E=%.3f | 命中率(近400)=%.0f%% | 驱动=%.2f 嗅探均=%.1f' % (
                step, time.time() - t0, E, 100 * acc, drive, sniff_total / max(act_total, 1)), flush=True)
    print('\n===== V144 猎食环报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限(猎食自持!)'), flush=True)
    for seg in range(max(1, step // 400)):
        s, e2 = seg * 400, min((seg + 1) * 400, step)
        print('  段%d(步%d-%d): 命中率=%.0f%% 平均E=%.2f 驱动=%.2f' % (
            seg + 1, s, e2, 100 * (1 - np.mean(errs[s:e2])), np.mean(energies[s:e2]),
            np.mean(drives[s:e2])), flush=True)
    print('总: 出击%d次 嗅探%d 命中%d | 平均出击嗅探=%.1f' % (
        act_total, sniff_total, hit_total, sniff_total / max(act_total, 1)), flush=True)
    print('末能量: %.3f | 末驱动: %.3f' % (E, drive), flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
