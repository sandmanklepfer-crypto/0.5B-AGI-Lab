#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V150 岔路世界 — 痛→记住→下次选安全路 (攻击性=主动避毒/选活路的生长土壤)
世界结构: 每个节点给出线索, 有2条可选路(A安全/B有毒或C死路)
  主体必须"选路" → 选安全=回血, 选毒=痛, 选死=重创
  选择空间存在 → "绕开"成为可学习动作(前几版单行道没得选)
核心测:
  1. 吃毒后是否开始选安全路(回避率上升)
  2. 痛史是否驱动选择(自读: "我记得这路有毒")
  3. 存活上升 = 攻击性(主动选活路)涌现
世界: 每节点 = (线索词, 岔路A, 岔路B), 一条安全一条毒, 位置每300步轮换(要持续学)
"""
import torch, time
import torch.nn as nn
import numpy as np

MAX_STEP = 8000
E_INIT, E_CAP = 1.0, 2.2
E_META = 0.0004
E_SAFE = 0.012      # 选安全路回血
E_POISON = 0.05     # 选毒路(痛)
E_DEADEND = 0.09    # 选死路(重创)
SELFREAD_EVERY = 50

# 岔路世界: 10个节点, 每个节点两条路(安全词/毒词), 每500步轮换安全侧
NODE_WORDS = {
    '入口': ('阳', '阴'),
    '林': ('鹿', '蛇'),
    '泉': ('净水', '浑水'),
    '山': ('草', '刺'),
    '谷': ('果', '菇'),
    '河': ('桥', '流'),
    '洞': ('光', '暗'),
    '崖': ('风', '石'),
    '原': ('花', '棘'),
    '屋': ('暖', '冷'),
}

class SelfCore:
    def __init__(self):
        self.mem = []
        self.pain_mem = []
    def sense(self, e, de, pain_recent):
        urgency = e + max(de, 0) * 3 + pain_recent * 2
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
        self.head = nn.Linear(d, 2)   # 二选一(岔路)
        self.state_proj = nn.Linear(4, d)
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state, state_vec=None):
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        x = self.emb(tok)
        if state_vec is not None:
            x = x + self.state_proj(state_vec.unsqueeze(0))
        h, state = self.cell.step(x, state)
        return self.head(h), state


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(w for pair in NODE_WORDS.values() for w in pair))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    node_names = list(NODE_WORDS.keys())
    body = BodyXLSTM(n_vocab, d=64)
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist_words = []
    errs, drives = [], []
    poison_times = []
    safe_pick, poison_pick, dead_pick = 0, 0, 0
    t0 = time.time(); dead = None
    print('V150 岔路世界 | %d节点 每节点2路(1安全1毒) 每500步换安全侧 | 测回避学习' % len(node_names), flush=True)
    step = 0
    while step < MAX_STEP:
        node = node_names[step % len(node_names)]
        epoch = step // 500
        safe_side = epoch % 2   # 安全侧每500步轮换(0=左,1=右)
        safe_w, poison_w = NODE_WORDS[node][safe_side], NODE_WORDS[node][1-safe_side]
        # 自读
        if step % SELFREAD_EVERY == 0 and step > 0:
            recent_acc = 1 - np.mean(errs[-50:]) if errs else 0.5
            pain_recent = sum(1 for pt in poison_times if step - pt < 200)
            state_vec = torch.tensor([E/E_CAP, recent_acc, min(pain_recent/4, 1.0), min(step/MAX_STEP, 1.0)], dtype=torch.float32)
        else:
            state_vec = None
            pain_recent = sum(1 for pt in poison_times if step - pt < 200)
        drive = core.sense(errs[-1] if errs else 0.5, 0, pain_recent)
        # 选路: 用mLSTM记忆(见过的节点-安全侧关系)预测
        with torch.no_grad():
            if hist_words:
                logits, state = body.step(w2i[hist_words[-1]], state, state_vec)
            else:
                logits, state = body.step(w2i[safe_w], state, state_vec)
            choice = int(torch.argmax(logits))   # 0=左 1=右
        # 世界裁决: 选的是安全还是毒
        picked_safe = (choice == safe_side)
        if picked_safe:
            E = min(E + E_SAFE, E_CAP); safe_pick += 1
        else:
            E -= E_POISON; poison_pick += 1; poison_times.append(step)
        e = 0.0 if picked_safe else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de, pain_recent)
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        # 学习: 无教师, 只用后果(能量变化)当信号 = RL
        # 选安全→强化"这个节点选这侧"; 选毒→弱化
        lr = 0.0008 + 0.003 * drive
        for g in opt.param_groups: g['lr'] = lr
        opt.zero_grad()
        prev = w2i[hist_words[-1]] if hist_words else w2i[safe_w]
        logits2, _ = body.step(prev, state, state_vec)
        # policy gradient: 奖励=这次选择的能量后果(放大尺度利学习)
        reward = (E_SAFE if picked_safe else -E_POISON) * 20
        log_prob = nn.functional.log_softmax(logits2, dim=-1)[0, choice]
        loss = -log_prob * reward   # 后果驱动: 好后果强化, 坏后果弱化
        loss.backward(); opt.step()
        with torch.no_grad():
            _, state = body.step(w2i[safe_w if picked_safe else poison_w], state, state_vec)
        state = tuple(s.detach() for s in state)
        # 实际走过的路(按选择)
        walked = safe_w if picked_safe else poison_w
        hist_words.append(walked)
        errs.append(e); drives.append(drive)
        step += 1
        if step % 500 == 0:
            acc = 1 - np.mean(errs[-500:])
            print('  [%4d步 %.0fs] E=%.3f | 选对率(近500)=%.0f%% | 驱动=%.2f | 痛%d次' % (
                step, time.time()-t0, E, 100*acc, drive, len(poison_times)), flush=True)
    print('\n===== V150 岔路世界报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限'), flush=True)
    total = safe_pick + poison_pick
    print('选路: 安全%d(%.0f%%) 毒%d(%.0f%%)' % (
        safe_pick, 100*safe_pick/max(total,1), poison_pick, 100*poison_pick/max(total,1)), flush=True)
    # 分段选对率(看是否随时间/痛史上升)
    print('分段选对率(每800步):', flush=True)
    for si in range(max(1, len(errs)//800)):
        s0, s1 = si*800, min((si+1)*800, len(errs))
        if s1 > s0:
            print('  步%d-%d: %.0f%%' % (s0, s1, 100*(1-np.mean(errs[s0:s1]))), flush=True)
    print('若选对率升(尤其安全侧轮换后恢复) → 痛史驱动回避学习 = 攻击性雏形 ✅', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
