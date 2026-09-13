#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V151 完整自我架构·大合体 — 自我整合层 + 我/非我边界 + 反事实 + 攻击性
四层:
  1. 世界: 岔路节点(每节点2路: 1安全1毒), 安全侧每400步轮换 → 选择有后果
  2. 身体mLSTM: 记忆世界规律(非我/外部) + 接收"我状态"(内部)
  3. 自我整合层: 读(能量/痛史/选择史/反事实账) → 输出"我状态"向量
     = 第一个整合中心(我的处境/我是谁)
  4. 反事实: 被毒后想象"另一条路"(我本可以) → 更新反事实账 → 强化自我感
行为: 自核(饿+痛)驱动攻击性; 我状态调制选择
无外部裁判: 无教师标签, 只靠后果(±能量) + 内部反事实想象
"""
import torch, time
import torch.nn as nn
import numpy as np

MAX_STEP = 12000
E_INIT, E_CAP = 1.0, 2.5
E_META = 0.0003
E_SAFE = 0.012
E_POISON = 0.05
SELFREAD_EVERY = 40

NODE_WORDS = {
    '入口': ('阳', '阴'), '林': ('鹿', '蛇'), '泉': ('净水', '浑水'),
    '山': ('草', '刺'), '谷': ('果', '菇'), '河': ('桥', '流'),
    '洞': ('光', '暗'), '崖': ('风', '石'), '原': ('花', '棘'),
    '屋': ('暖', '冷'),
}
NODES = list(NODE_WORDS.keys())


class SelfCore:
    """意志核: 饿(误差)+痛(痛史) → 攻击驱动"""
    def __init__(self):
        self.mem = []
        self.pain_mem = []
    def sense(self, e, de, pain_recent):
        urgency = e + max(de, 0) * 3 + pain_recent * 2
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


class BodyXLSTM(nn.Module):
    def __init__(self, n_vocab, d=64):
        super().__init__()
        self.d = d
        self.emb = nn.Embedding(n_vocab, d)
        self.cell = XMemCell(d, d)
        self.head = nn.Linear(d, 2)
        # 自我整合层(新): 内部状态(5维) → 注入向量
        self.self_integrate = nn.Linear(5, d)
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state, self_vec=None):
        """self_vec = 我状态(整合后的内部表征), None=无自指"""
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        x = self.emb(tok)
        if self_vec is not None:
            x = x + self.self_integrate(self_vec.unsqueeze(0))
        h, state = self.cell.step(x, state)
        return self.head(h), state


def main():
    torch.manual_seed(0); np.random.seed(0)
    all_words = sorted(set(w for pair in NODE_WORDS.values() for w in pair))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    body = BodyXLSTM(n_vocab, d=64)
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    core = SelfCore()
    E = E_INIT
    state = body.init_state()
    hist_words = []
    errs, drives = [], []
    pain_times = []
    choice_log = []          # 选择史(0/1)
    cf_account = [0.0, 0.0]  # 反事实账: [想象安全路次数, 想象毒路次数]
    poison_cnt, safe_cnt = 0, 0
    t0 = time.time(); dead = None
    print('V151 完整自我·大合体 | 岔路世界10节点 | 自我整合+反事实 | 无教师', flush=True)
    step = 0
    while step < MAX_STEP:
        node = NODES[step % len(NODES)]
        epoch = step // 400
        safe_side = epoch % 2
        safe_w, poison_w = NODE_WORDS[node][safe_side], NODE_WORDS[node][1 - safe_side]
        # ---- 自读: 整合自我状态(能量/近命中/痛/选择一致性/反事实账) = "我" ----
        if step > 0 and step % SELFREAD_EVERY == 0:
            recent_acc = 1 - np.mean(errs[-40:]) if errs else 0.5
            pain_recent = min(sum(1 for pt in pain_times if step - pt < 150) / 3, 1.0)
            # 选择一致性: 最近10次选择里我"重复选同一侧"的倾向(自我连贯感)
            if len(choice_log) >= 10:
                c10 = choice_log[-10:]
                consistency = max(np.mean(c10), 1 - np.mean(c10))
            else:
                consistency = 0.5
            # 反事实账: 想象积累(我本可以)
            cf_total = cf_account[0] + cf_account[1] + 1e-6
            cf_bias = cf_account[0] / cf_total  # 想象"选安全路更好"的比例
            self_vec = torch.tensor([
                E / E_CAP, recent_acc, pain_recent, consistency, cf_bias
            ], dtype=torch.float32)
        else:
            self_vec = None
            pain_recent = sum(1 for pt in pain_times if step - pt < 150)
        drive = core.sense(errs[-1] if errs else 0.5, 0, pain_recent)
        # ---- 选择(由身体记忆+我状态共同决定) ----
        with torch.no_grad():
            prev = w2i[hist_words[-1]] if hist_words else w2i[safe_w]
            logits, state = body.step(prev, state, self_vec)
            choice = int(torch.argmax(logits))
        picked_safe = (choice == safe_side)
        if picked_safe:
            E = min(E + E_SAFE, E_CAP); safe_cnt += 1
        else:
            E -= E_POISON; poison_cnt += 1; pain_times.append(step)
        e = 0.0 if picked_safe else 1.0
        de = e - (errs[-1] if errs else 0)
        drive = core.sense(e, de, pain_recent)
        E -= E_META
        if E <= 0:
            dead = '能量耗尽死亡(E=0)'
            break
        # ---- 学习: 后果驱动(RL) ----
        lr = 0.0006 + 0.002 * drive
        for g in opt.param_groups: g['lr'] = lr
        opt.zero_grad()
        prev = w2i[hist_words[-1]] if hist_words else w2i[safe_w]
        logits2, _ = body.step(prev, state, self_vec)
        reward = (E_SAFE if picked_safe else -E_POISON) * 20
        log_prob = nn.functional.log_softmax(logits2, dim=-1)[0, choice]
        loss = -log_prob * reward
        loss.backward(); opt.step()
        # ---- 反事实层: 被毒后想象"另一条路"(我本可以) ----
        if not picked_safe:
            # 反事实: 想象另一条路是安全的 → 给另一条路虚拟正强化
            opt.zero_grad()
            logits3, _ = body.step(prev, state, self_vec)
            cf_choice = 1 - choice
            cf_reward = E_SAFE * 10   # 虚拟"本可以"的奖励(想象, 非外部)
            cf_loss = -nn.functional.log_softmax(logits3, dim=-1)[0, cf_choice] * cf_reward
            cf_loss.backward(); opt.step()
            cf_account[0] += 1
        elif np.random.rand() < 0.1:
            # 偶尔想象另一条路可能是毒(巩固"我选对了")
            cf_account[1] += 1
        with torch.no_grad():
            walked = safe_w if picked_safe else poison_w
            _, state = body.step(w2i[walked], state, self_vec)
        state = tuple(s.detach() for s in state)
        hist_words.append(walked)
        choice_log.append(choice)
        errs.append(e); drives.append(drive)
        step += 1
        if step % 400 == 0:
            acc = 1 - np.mean(errs[-400:])
            print('  [%4d步 %.0fs] E=%.3f | 选对率(近400)=%.0f%% | 痛%d | 反事实想象%d' % (
                step, time.time()-t0, E, 100*acc, len(pain_times), int(sum(cf_account))), flush=True)
    print('\n===== V151 完整自我报告 =====', flush=True)
    print('存活: %d步 | %s' % (step, dead or '到上限'), flush=True)
    total = safe_cnt + poison_cnt
    print('选择: 安全%d(%.0f%%) 毒%d(%.0f%%)' % (
        safe_cnt, 100*safe_cnt/max(total,1), poison_cnt, 100*poison_cnt/max(total,1)), flush=True)
    print('痛史: %d次 | 反事实账: 想象安全%d次 想象毒%d次 | 驱动末值%.2f' % (
        len(pain_times), int(cf_account[0]), int(cf_account[1]), drive), flush=True)
    print('分段选对率:', flush=True)
    for si in range(max(1, len(errs)//1000)):
        s0, s1 = si*1000, min((si+1)*1000, len(errs))
        if s1 > s0:
            print('  步%d-%d: %.0f%%' % (s0, s1, 100*(1-np.mean(errs[s0:s1]))), flush=True)
    # 安全侧轮换后的恢复速度(泛化/适应)
    print('若分段选对率上升+轮换后恢复 → 自我整合层工作: 边活边形成"我"', flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
