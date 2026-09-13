#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V153 攻击性=状态空间搜索 — 攻击指向未知(好奇侵略), 扩张泛化边界
核心: 攻击驱动 = 误差 + 新颖度(没见过/少见的模式)
  → 饿+新 → 主动扑向未知猎场/新组合 → 撞到更多新样本 → 样本率↑ → 泛化↑
测: 探索量(扑向未知次数) 与 泛化(新组合开局正确率) 的关系
世界: 8条规律, 训练用4条(组合A/B), 测试用全新组合C(2旧+1全新规律)
对照: 攻击指向已知(旧版) vs 攻击指向未知(本版) → 泛化差异
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
    'animal': ['猫', '狗', '鸟', '鱼', '兔'],
    'water': ['山', '河', '湖', '海'],
}
MAX_STEP = 6000
E_INIT, E_CAP = 1.0, 2.5
E_META = 0.0003
E_HIT = 0.012
E_MISS = 0.012


class SelfCore:
    def __init__(self):
        self.mem = []
    def sense(self, e, de):
        urgency = e + max(de, 0) * 3
        self.mem.append(urgency)
        if len(self.mem) > 25: self.mem.pop(0)
        return min(0.6 * urgency + 0.4 * float(np.mean(self.mem)), 1.0)


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


class Body(nn.Module):
    def __init__(self, n_vocab, d=64):
        super().__init__()
        self.emb = nn.Embedding(n_vocab, d)
        self.cell = XMemCell(d, d)
        self.head = nn.Linear(d, n_vocab)
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        h, state = self.cell.step(self.emb(tok), state)
        return self.head(h), state


def run_phase(body, w2i, all_words, n_vocab, rules_list, max_steps, mode):
    """mode='known': 攻击指向已知(纯误差) | mode='novel': 攻击指向未知(误差+新颖度)"""
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist = []
    errs = []
    seen = {}          # 见过的规则名/词频(新颖度)
    novel_attacks = 0  # 扑向未知次数
    step = 0
    t0 = time.time()
    while step < max_steps:
        ridx = (step // 200) % len(rules_list)
        rname = rules_list[ridx]
        wlist = RULES[rname]
        pos = step % len(wlist)
        actual = wlist[pos]
        # 新颖度: 这个词见过几次(少=新)
        seen[actual] = seen.get(actual, 0) + 1
        novelty = 1.0 / (1.0 + seen[actual])   # 越少见越新
        drive = core.sense(errs[-1] if errs else 0.5, 0)
        # 攻击指向: known=只看误差; novel=误差×新颖度(扑未知)
        attack = drive * (1.0 if mode == 'known' else novelty)
        # 预测(带攻击调制: 攻击强时更可能换到别的规则区=探索)
        with torch.no_grad():
            prev = w2i[hist[-1]] if hist else w2i[actual]
            logits, state = body.step(prev, state)
            if attack > 0.6 and np.random.rand() < 0.3:
                # 攻击性探索: 30%概率跳到别的规则区(主动搜索状态空间)
                other = rules_list[(ridx + 1 + np.random.randint(len(rules_list)-1)) % len(rules_list)]
                w2 = other[np.random.randint(len(other))]
                pred_i = w2i[w2]
                novel_attacks += 1
            else:
                pred_i = int(torch.argmax(logits))
            pred_w = all_words[pred_i]
        hit = (pred_w == actual)
        if hit: E = min(E + E_HIT, E_CAP)
        else:   E -= E_MISS
        e = 0.0 if hit else 1.0
        E -= E_META
        if E <= 0: break
        # 学习
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else w2i[actual]
        logits2, _ = body.step(prev, state)
        loss = nn.functional.cross_entropy(logits2, torch.tensor([w2i[actual]]))
        loss.backward(); opt.step()
        with torch.no_grad():
            _, state = body.step(w2i[actual], state)
        state = tuple(s.detach() for s in state)
        hist.append(actual)
        errs.append(e)
        step += 1
    acc = 1 - np.mean(errs) if errs else 0
    return step, acc, novel_attacks, body.state_dict()


def eval_generalization(body, w2i, all_words, n_vocab, test_rules, n_steps=300):
    """泛化测试: 全新组合(2旧+1全新规律), 冻结学习, 测开局正确率"""
    body.eval()
    state = body.init_state()
    hist = []
    correct = 0
    total = 0
    with torch.no_grad():
        for step in range(n_steps):
            ridx = (step // 60) % len(test_rules)
            wlist = RULES[test_rules[ridx]]
            actual = wlist[step % len(wlist)]
            if hist:
                prev = w2i[hist[-1]]
                logits, state = body.step(prev, state)
                pred_w = all_words[int(torch.argmax(logits))]
            else:
                pred_w = all_words[np.random.randint(n_vocab)]
            if pred_w == actual: correct += 1
            total += 1
            _, state = body.step(w2i[actual], state)
            state = tuple(s.detach() for s in state)
            hist.append(actual)
    return correct / max(total, 1)


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(w for ws in RULES.values() for w in ws))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    print('V153 攻击性=状态搜索 | 训练4规律 测试全新组合 | known vs novel攻击', flush=True)
    for mode in ['known', 'novel']:
        body = Body(n_vocab)
        train_rules = ['season', 'color', 'num', 'sky']
        step, acc, natt, sd = run_phase(body, w2i, all_words, n_vocab, train_rules, 4000, mode)
        body.load_state_dict(sd)
        # 泛化测试: 全新组合 = 2训练规律(season,num) + 1全新规律(fruit)
        test_rules = ['season', 'num', 'fruit']
        gen_acc = eval_generalization(body, w2i, all_words, n_vocab, test_rules)
        print('\n[%s攻击] 训练: 存活%d 命中%.0f%% 扑未知%d次' % (mode, step, 100*acc, natt), flush=True)
        print('  泛化测试(全新组合 季节+数字+水果): 正确率=%.0f%%' % (100*gen_acc), flush=True)
        # 拆: 旧规律部分 vs 全新规律部分
        body2 = Body(n_vocab); body2.load_state_dict(sd)
        ga_old = eval_generalization(body2, w2i, all_words, n_vocab, ['season', 'num'], 150)
        body3 = Body(n_vocab); body3.load_state_dict(sd)
        ga_new = eval_generalization(body3, w2i, all_words, n_vocab, ['fruit'], 150)
        print('  其中: 旧规律迁移=%.0f%% | 全新规律(fruit)=%.0f%%' % (100*ga_old, 100*ga_new), flush=True)
    print('\n判读: novel攻击的泛化 > known攻击 → 攻击性(扑未知)确实扩张泛化', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
