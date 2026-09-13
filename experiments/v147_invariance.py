#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V147 不变性结晶 — 泛化的本质落地: 不是设计单元, 是让跨环境不变性自己沉淀
世界时间结构(核心改动, 架构不变):
  规律池(春→夏→秋→冬 等) = 跨环境不变的"真规律"
  环境 = 规律的随机组合(每段换组合, 但同一规律在不同组合里反复出现)
  → "春→夏"跨环境重复 → 在mLSTM矩阵记忆里自动沉淀成强连接(结晶)
  → "春旁边是红"这种单组合巧合 → 不跨环境重复 → 自动弱化
测(泛化的真考验):
  第1阶段: 在组合A/B/C里活(学规律)
  第2阶段: 全新组合D(由见过的规律+1条新规律组成)
  → 若正确率开局就高(不是0%): 规律结晶成功, 泛化涌现(旧规律迁移+新规律快学)
  → 若开局0%: 没结晶(仍是整体记忆, 换组合全失效)
架构: mLSTM+自核+能量(全同V146), 只改世界时间结构
"""
import torch, time
import torch.nn as nn
import numpy as np

# 规律池(跨环境不变的转移规律): (词序列, 词序列)
RULES = {
    'season': ['春', '夏', '秋', '冬'],
    'color': ['红', '绿', '蓝', '黄', '紫'],
    'num': ['一', '二', '三', '四', '五'],
    'sky': ['太阳', '月亮', '星星', '云'],
    'weather': ['风', '雨', '雷', '电'],
    'water': ['山', '河', '湖', '海'],
    'fruit': ['苹果', '香蕉', '橘子', '葡萄'],
    'animal': ['猫', '狗', '鸟', '鱼', '兔'],
}
RULE_NAMES = list(RULES.keys())
MAX_STEP = 8000
E_INIT, E_CAP = 1.0, 2.2
E_META = 0.0004
E_HIT = 0.011
E_MISS = 0.012
E_SNIFF = 0.0015
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


def run_phase(body, w2i, all_words, n_vocab, combo_rules, combo_name, max_steps, label):
    """在一组规律组合(环境)里活 max_steps, 返回(存活, 命中率, 各步误差)"""
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs, drives = [], []
    step = 0
    t0 = time.time()
    while step < max_steps:
        # 环境=组合: 每300步轮换一个规则(组合内)
        ridx = (step // 300) % len(combo_rules)
        wlist = RULES[combo_rules[ridx]]
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
        if hit: E = min(E + E_HIT, E_CAP)
        else:   E -= E_MISS
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
    # 分4段命中率(看学习曲线)
    seg_acc = []
    for si in range(4):
        s0, s1 = si*len(errs)//4, (si+1)*len(errs)//4
        if s1 > s0:
            seg_acc.append(1 - np.mean(errs[s0:s1]))
    print('  [%s] %s | 存活%d/%d | 总命中%.0f%% | 分段: %s | %.0fs' % (
        label, combo_name, step, max_steps, 100*acc,
        ' → '.join('%.0f%%' % (100*a) for a in seg_acc), time.time()-t0), flush=True)
    return step, acc, errs, body.state_dict()


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(sum(RULES.values(), [])))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    body = BodyXLSTM(n_vocab, d=64)
    print('V147 不变性结晶 | 阶段1=学规律(组合A/B/C) 阶段2=泛化测试(全新组合D)', flush=True)
    # 阶段1: 三个组合(每个=2条规律, 规律跨组合重复出现)
    phase1 = [
        (['season', 'color'], '组合A: 季节+颜色'),
        (['num', 'sky'], '组合B: 数字+天空'),
        (['season', 'num'], '组合C: 季节+数字(季节再现!)'),
    ]
    for combo, name in phase1:
        _, _, _, sd = run_phase(body, w2i, all_words, n_vocab, combo, name, 2400, '阶段1')
        body.load_state_dict(sd)  # 保持学到的(连续体同一身体)
    print('\n--- 阶段2: 泛化测试 (全新组合D: 季节+水果 — 季节见过, 水果全新) ---', flush=True)
    step, acc, errs, _ = run_phase(body, w2i, all_words, n_vocab, ['season', 'fruit'], '组合D: 季节+水果(全新)', 2400, '阶段2')
    # 开局正确率(前200步): 若>50% → 季节规律迁移成功(泛化); ~随机 → 没泛化
    open_acc = 1 - np.mean(errs[:200]) if len(errs) >= 200 else 0
    print('\n===== V147 泛化裁决 =====', flush=True)
    print('开局200步命中: %.0f%% (随机基线≈%.0f%%)' % (100*open_acc, 100*2/n_vocab), flush=True)
    if open_acc > 0.5:
        print('结论: 规律结晶成功 → 全新环境下旧规律迁移, 泛化涌现 ✅', flush=True)
    else:
        print('结论: 未结晶(整体记忆) → 换组合仍接近0%, 需更长跨环境重复', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
