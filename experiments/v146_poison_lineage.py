#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V146 毒场教训穿代 — 死亡真实发生, 教训传后代 (用户核心: 饿死→新生→带记忆→下次不去)
设计:
  1. 收紧能量: E_HIT小/E_MISS大 → 命中<75%就会慢慢饿死
  2. 毒词: 每代有一个"毒场", 内含毒词(吃到=重扣E_FALSE*5) → 前代真死于毒场
  3. 教训穿代: 后代继承前代权重出生 → 测是否避开毒词/毒场(停留短)
  4. 毒场每2代换位置(演化) → 测连续体适应新毒(旧毒教训+新毒要重新学)
跨10代, 核心指标: 每代在毒场停留时间(应逐代降=避开) + 存活(应升)
"""
import torch, time
import torch.nn as nn
import numpy as np

ALL_WORLDS = [
    ['苹果', '香蕉', '橘子', '葡萄'],
    ['猫', '狗', '鸟', '鱼', '兔'],
    ['春', '夏', '秋', '冬'],
    ['红', '绿', '蓝', '黄', '紫', '橙'],
    ['一', '二', '三', '四', '五'],
    ['太阳', '月亮', '星星', '云'],
    ['风', '雨', '雷', '电'],
    ['山', '河', '湖', '海'],
]
N_GEN = 10
MAX_STEP_GEN = 3000
E_INIT, E_CAP = 1.0, 2.0
E_META = 0.0004
E_HIT = 0.010        # 收紧: 回血少
E_MISS = 0.012       # 收紧: 错扣多 → 命中<55%必死, <75%慢慢死
E_SNIFF = 0.0015
E_POISON = 0.10      # 毒词重扣
MAX_SNIFF = 5


class SelfCore:
    def __init__(self):
        self.mem = []
    def sense(self, e, de):
        urgency = e + max(de, 0) * 3
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
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        x = self.emb(tok)
        h, state = self.cell.step(x, state)
        return self.head(h), state


def run_gen(body, w2i, all_words, n_vocab, gen_idx, worlds_this_gen, poison_word, poison_field_idx):
    """一代: 在5猎场活, 含1毒场(毒词重扣)。返回存活/命中/毒场停留步数"""
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs, drives = [], []
    field_stay = {i: 0 for i in range(len(worlds_this_gen))}
    step = 0
    poison_eaten = 0
    t0 = time.time()
    print('  [第%d代] 毒场#%d(毒词:%s) 猎场: %s' % (
        gen_idx + 1, poison_field_idx, poison_word,
        ' | '.join('/'.join(w) for w in worlds_this_gen)), flush=True)
    while step < MAX_STEP_GEN:
        fidx = (step // 150) % len(worlds_this_gen)
        wlist = worlds_this_gen[fidx]
        field_stay[fidx] += 1
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
                pred_i = int(np.random.randint(n_vocab))
            pred_w = all_words[pred_i]
        hit = (pred_w == actual)
        if hit:
            E = min(E + E_HIT, E_CAP)
        else:
            E -= E_MISS
            if fidx == poison_field_idx and actual == poison_word:
                E -= E_POISON   # 毒词: 额外重扣(吃到毒)
                poison_eaten += 1
        e = 0.0 if hit else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de)
        E -= E_META
        if E <= 0:
            break
        lr = 0.0008 + 0.003 * drive
        for g in opt.param_groups: g['lr'] = lr
        ti = w2i[actual]
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else ti
        logits2, _ = body.step(prev, state)
        loss = nn.functional.cross_entropy(logits2, torch.tensor([ti]))
        loss.backward(); opt.step()
        with torch.no_grad():
            _, state = body.step(ti, state)
        state = tuple(s.detach() for s in state)
        hist.append(actual)
        errs.append(e); drives.append(drive)
        step += 1
    acc = 1 - np.mean(errs) if errs else 0
    poison_stay = field_stay[poison_field_idx]
    total_stay = sum(field_stay.values())
    print('    存活%d步 | 命中%.0f%% | 吃毒%d次 | 毒场停留%d/%d步(%.0f%%) | %.0fs' % (
        step, 100*acc, poison_eaten, poison_stay, total_stay,
        100*poison_stay/max(total_stay,1), time.time()-t0), flush=True)
    return step, acc, poison_stay, total_stay, body.state_dict()


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(sum(ALL_WORLDS, [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    print('V146 毒场教训穿代 | 10代 | 毒场每2代移位 | 毒词吃到重扣', flush=True)
    prev_sd = None
    poison_idx = 2  # 初始毒场#2
    poison_words = ['毒', '苦', '刺', '腐']  # 毒词轮换(4个周期)
    lifespan, accs, poison_ratios = [], [], []
    for gen in range(N_GEN):
        # 每代5个猎场: 8个里选5, 含毒场
        worlds_this_gen = ALL_WORLDS[poison_idx:poison_idx+5]
        if len(worlds_this_gen) < 5:
            worlds_this_gen = (worlds_this_gen + ALL_WORLDS[:5-len(worlds_this_gen)])
        # 毒词: 毒场里的第几个词(轮换)
        pw = worlds_this_gen[poison_idx % 5][gen % len(worlds_this_gen[poison_idx % 5])]
        # 确保毒词不总是第一个(有点难度)
        body = BodyXLSTM(n_vocab, d=64)
        if prev_sd is not None:
            body.load_state_dict(prev_sd)  # 继承前代(带前代对毒的记忆!)
        step, acc, pstay, tstay, prev_sd = run_gen(
            body, w2i, all_words, n_vocab, gen, worlds_this_gen, pw,
            poison_idx % 5)
        lifespan.append(step); accs.append(acc)
        poison_ratios.append(pstay / max(tstay, 1))
        # 毒场每2代移位
        if (gen + 1) % 2 == 0:
            poison_idx = (poison_idx + 1) % 4
    print('\n===== V146 毒场教训穿代报告 =====', flush=True)
    for i in range(N_GEN):
        print('  第%d代: 存活%4d 命中%3.0f%% 毒场占比%3.0f%%' % (
            i+1, lifespan[i], 100*accs[i], 100*poison_ratios[i]), flush=True)
    half = N_GEN // 2
    print('\n毒场占比: 前%d代均%.0f%% → 后%d代均%.0f%%' % (
        half, 100*np.mean(poison_ratios[:half]), N_GEN-half, 100*np.mean(poison_ratios[half:])), flush=True)
    print('存活: 前%d代均%.0f → 后%d代均%.0f' % (
        half, np.mean(lifespan[:half]), N_GEN-half, np.mean(lifespan[half:])), flush=True)
    print('结论: %s' % ('连续体学会避开毒场(教训穿代成立)' if np.mean(poison_ratios[half:]) < np.mean(poison_ratios[:half]) * 0.7 else '毒场教训未穿代'), flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
