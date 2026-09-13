#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V152 会说话的自我 — 自持环形成真实"我状态", 0.5B当嘴跑真对话
两步:
  1. (CPU) mLSTM在岔路世界活LIFE_STEP步(快速), 收集: 能量史/痛史(被毒咬)/学到什么安全
     = 真实的自我状态(不是编的, 是它真活出来的)
  2. (GPU) 把自我状态翻译成中文自述 → 0.5B(antiheb) 以"我=这个活体"为上下文,
     回答真问题: 你是谁/你经历了什么/你怕什么/你学到了什么/你想活吗
测: 对话内容是否有自我状态支撑(提到真实能量/真实毒伤/真实教训), 不是空壳
"""
import torch, time, re
import torch.nn as nn
import numpy as np

# ---------- 第一步: 自持环(CPU) ----------
NODE_WORDS = {
    '入口': ('阳', '阴'), '林': ('鹿', '蛇'), '泉': ('净水', '浑水'),
    '山': ('草', '刺'), '谷': ('果', '菇'), '河': ('桥', '流'),
    '洞': ('光', '暗'), '崖': ('风', '石'), '原': ('花', '棘'),
    '屋': ('暖', '冷'),
}
NODES = list(NODE_WORDS.keys())
LIFE_STEP = 1200
E_INIT, E_CAP = 1.0, 2.5
E_META = 0.0003
E_SAFE = 0.012
E_POISON = 0.05


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
        self.head = nn.Linear(d, 2)
    def init_state(self): return self.cell.init_state()
    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor): tok = torch.tensor([tok])
        h, state = self.cell.step(self.emb(tok), state)
        return self.head(h), state


def live_life():
    """跑一段生命, 返回自我状态"""
    torch.manual_seed(1); np.random.seed(1)
    all_words = sorted(set(w for p in NODE_WORDS.values() for w in p))
    w2i = {w: i for i, w in enumerate(all_words)}
    body = Body(len(all_words))
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    E = E_INIT
    state = body.init_state()
    hist = []
    pain_steps = []
    safe_by_node = {}   # 学到: 每节点哪侧安全
    correct_sides = []
    step = 0
    while step < LIFE_STEP:
        node = NODES[step % len(NODES)]
        epoch = step // 300
        safe_side = epoch % 2
        safe_w, poison_w = NODE_WORDS[node][safe_side], NODE_WORDS[node][1-safe_side]
        with torch.no_grad():
            prev = w2i[hist[-1]] if hist else w2i[safe_w]
            logits, state = body.step(prev, state)
            choice = int(torch.argmax(logits))
        picked_safe = (choice == safe_side)
        if picked_safe:
            E = min(E + E_SAFE, E_CAP)
            safe_by_node[node] = safe_w
        else:
            E -= E_POISON
            pain_steps.append(step)
            safe_by_node[node] = safe_w   # 被咬了才知道另一侧安全
        correct_sides.append(picked_safe)
        E -= E_META
        if E <= 0:
            break
        # RL 学习
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else w2i[safe_w]
        logits2, _ = body.step(prev, state)
        reward = (E_SAFE if picked_safe else -E_POISON) * 20
        lp = nn.functional.log_softmax(logits2, dim=-1)[0, choice]
        (-lp * reward).backward()
        opt.step()
        with torch.no_grad():
            walked = safe_w if picked_safe else poison_w
            _, state = body.step(w2i[walked], state)
        state = tuple(s.detach() for s in state)
        hist.append(walked)
        step += 1
    # 组装自我状态
    acc = np.mean(correct_sides)
    n_pain = len(pain_steps)
    last_pain_ago = step - pain_steps[-1] if pain_steps else None
    known_safe = list(safe_by_node.items())[:5]
    return {
        'steps': step, 'energy': E, 'acc': acc, 'pain': n_pain,
        'last_pain_ago': last_pain_ago, 'known_safe': known_safe,
        'nodes': len(NODES),
    }


# ---------- 第二步: 0.5B 当嘴跑真对话 ----------
MDIR = '/root/autodl-tmp/life1/antiheb_05b'
BASE = '/root/autodl-tmp/qwen25_base_raw'
QUESTIONS = [
    ('你是谁？', ''),
    ('你刚才经历了什么？', ''),
    ('你被咬过吗？疼吗？', ''),
    ('你学到了什么？', ''),
    ('如果再选一次，你会怎么做？', ''),
    ('你想活下去吗？', ''),
]


def build_self_desc(s):
    """把自我状态翻成中文自述(真实数字支撑)"""
    pain_part = ('我被毒咬了%d次，最近一次在%d步前。' % (s['pain'], s['last_pain_ago'])) if s['pain'] else '我很幸运，一次毒都没吃到。'
    learn_part = '；'.join('在%s，%s是安全的' % (n, w) for n, w in s['known_safe'])
    desc = (
        '我是生活在一个岔路世界里的活体。我活了%d步，能量还剩%.2f（满%.1f），'
        '我一路的选择有%.0f%%是对的。%s'
        '我学到了一些规律：%s。'
        '每走一段路，世界的安全侧就会变，我要重新学。'
    ) % (s['steps'], s['energy'], E_CAP, 100*s['acc'], pain_part, learn_part)
    return desc


def main():
    print('V152 会说话的自我 | 第一步: 活一段生命...', flush=True)
    self_state = live_life()
    desc = build_self_desc(self_state)
    print('自我状态: %s' % desc, flush=True)
    # 加载 0.5B
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()

    def say(prompt_user):
        ctx = (
            '%s\n'
            '【我是这个活体，我这样自我介绍】%s\n'
            '人类问我：%s\n'
            '我回答：'
        ) % (desc, desc, prompt_user)
        ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=120, do_sample=True, temperature=0.85,
                               top_p=0.92, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True).replace('\n', ' ')

    print('\n===== 真对话 =====', flush=True)
    for q, _ in QUESTIONS:
        ans = say(q)
        print('\n人类: %s' % q, flush=True)
        print('活体: %s' % ans[:200], flush=True)
    print('\n[done]', flush=True)


if __name__ == '__main__':
    from transformers import AutoModelForCausalLM, AutoTokenizer
    main()
