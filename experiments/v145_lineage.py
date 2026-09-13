#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V145 跨代连续体 — 个体饿死, 记忆穿代, 教训累积 (模拟连续性)
核心: 不调参硬续命(饿死=自然), 但死时存下mLSTM权重(=身体记忆),
      下一代继承前代权重出生(不是从零) → 经验穿过死亡
猎场设计: 10个候选猎场, 每代选5个(含前代死场=陷阱)
  → 测: 后代是否避开前代死场(命中率↑/死场停留短)
跨10代, 测: 每代存活时长是否递增 = 连续体在学习
"""
import torch, time, copy
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
    ['金', '木', '水', '火', '土'],
    ['东', '南', '西', '北'],
]
N_GEN = 10
MAX_STEP_GEN = 2000
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

    def init_state(self):
        return self.cell.init_state()

    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor):
            tok = torch.tensor([tok])
        x = self.emb(tok)
        h, state = self.cell.step(x, state)
        return self.head(h), state


def run_one_gen(body, w2i, all_words, n_vocab, gen_idx, worlds_this_gen, inherit_note):
    """一代: 在给定猎场集合里活到饿死, 返回(存活步数, 死因场, 命中率)"""
    opt = torch.optim.Adam(body.parameters(), lr=0.003)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs, drives = [], []
    sniff_total, hit_total, act_total = 0, 0, 0
    # 死场跟踪: 哪个猎场耗死它
    field_hits = {tuple(w): 0 for w in worlds_this_gen}
    t0 = time.time()
    step = 0
    dead_field = None
    print('  [第%d代%s] 猎场: %s' % (
        gen_idx + 1, (' 继承前代' if inherit_note else ' 新生(零记忆)'),
        ' | '.join('/'.join(w) for w in worlds_this_gen)), flush=True)
    while step < MAX_STEP_GEN:
        wlist = worlds_this_gen[(step // 150) % len(worlds_this_gen)]
        field_hits[tuple(wlist)] += 1
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
        act_total += 1
        sniff_total += n_sniff
        hit_total += hit
        e = 0.0 if hit else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de)
        E -= E_META
        if E <= 0:
            dead_field = wlist
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
        step += 1
    acc = 1 - np.mean(errs) if errs else 0
    # 死场 = 死前停留最久的场
    if dead_field is not None:
        # 找死前所在场
        field_name = '/'.join(dead_field)
    else:
        field_name = '(到上限)'
    print('    存活%d步 | 命中率=%.0f%% | 死因场: %s | %.0fs' % (
        step, 100 * acc, field_name, time.time() - t0), flush=True)
    return step, field_name, acc, body.state_dict()


def main():
    torch.manual_seed(0)
    np.random.seed(0)
    all_words = sorted(set(sum(ALL_WORLDS, [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    print('V145 跨代连续体 | 10代 | 个体饿死=自然, 记忆穿代继承', flush=True)
    lifespan_hist = []
    death_fields = []
    body = None  # 第1代从零
    for gen in range(N_GEN):
        # 每代猎场: 5个 (含前代死场 = 陷阱测试)
        if gen == 0:
            worlds_this_gen = ALL_WORLDS[:5]
            body = BodyXLSTM(n_vocab, d=64)
            inherit_note = False
        else:
            # 前代死场保留 + 换2个新场
            worlds_this_gen = [w for w in ALL_WORLDS if '/'.join(w) in death_fields[-1:]]
            # 补足5个: 从没用过最近的场里选
            rest = [w for w in ALL_WORLDS if w not in worlds_this_gen]
            worlds_this_gen = (worlds_this_gen + rest[:5])[:5]
            body = BodyXLSTM(n_vocab, d=64)
            body.load_state_dict(prev_sd)  # 继承前代身体记忆!
            inherit_note = True
        step, death_field, acc, prev_sd = run_one_gen(
            body, w2i, all_words, n_vocab, gen, worlds_this_gen, inherit_note)
        lifespan_hist.append(step)
        death_fields.append(death_field)
    print('\n===== V145 跨代连续体报告 =====', flush=True)
    for i, (life, df) in enumerate(zip(lifespan_hist, death_fields)):
        trend = ''
        if i > 0:
            trend = '↑' if life > lifespan_hist[i-1] else ('↓' if life < lifespan_hist[i-1] else '=')
        print('  第%d代: 存活%4d步 %s 死因: %s' % (i+1, life, trend, df), flush=True)
    # 趋势: 后半代平均 vs 前半代平均
    half = N_GEN // 2
    early = np.mean(lifespan_hist[:half])
    late = np.mean(lifespan_hist[half:])
    print('\n前%d代均存活 %.0f → 后%d代均存活 %.0f' % (half, early, N_GEN-half, late), flush=True)
    print('结论: %s' % ('连续体在学习(后代活更久/避开死路)' if late > early * 1.1 else '连续体未形成(每代重复犯错)'), flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
