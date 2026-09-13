#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V154b 蒸馏纹路进sLSTM — 学生学教师hidden, 对比素泥泛化
"""
import torch
import torch.nn as nn
import numpy as np

RULES = {
    'season': ['春', '夏', '秋', '冬'],
    'color': ['红', '绿', '蓝', '黄', '紫'],
    'num': ['一', '二', '三', '四', '五'],
    'sky': ['太阳', '月亮', '星星', '云'],
    'fruit': ['苹果', '香蕉', '橘子', '葡萄'],
}


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
    def __init__(self, n_vocab, d=64, grain_dim=896, n_char=200):
        super().__init__()
        self.emb = nn.Embedding(n_vocab, d)
        self.char_emb = nn.Embedding(n_char, d)   # 字符专用嵌入(蒸馏用)
        self.cell = XMemCell(d, d)
        self.head = nn.Linear(d, n_vocab)
        self.grain_head = nn.Linear(d, grain_dim)

    def init_state(self):
        return self.cell.init_state()

    def step(self, tok, state):
        if not isinstance(tok, torch.Tensor):
            tok = torch.tensor([tok])
        h, state = self.cell.step(self.emb(tok), state)
        return self.head(h), self.grain_head(h), state

    def step_char(self, ch, state):
        if not isinstance(ch, torch.Tensor):
            ch = torch.tensor([ch])
        h, state = self.cell.step(self.char_emb(ch), state)
        return self.head(h), self.grain_head(h), state


def train_rules(body, w2i, rules_names, steps=2000):
    opt = torch.optim.Adam(body.parameters(), lr=0.002)
    state = body.init_state()
    hist = []
    for step in range(steps):
        wlist = RULES[rules_names[(step // 200) % len(rules_names)]]
        actual = wlist[step % len(wlist)]
        opt.zero_grad()
        prev = w2i[hist[-1]] if hist else w2i[actual]
        logits, _, state = body.step(prev, state)
        loss = nn.functional.cross_entropy(logits, torch.tensor([w2i[actual]]))
        loss.backward(); opt.step()
        with torch.no_grad():
            _, _, state = body.step(w2i[actual], state)
        state = tuple(s.detach() for s in state)
        hist.append(actual)
    return body


def eval_gen(body, w2i, all_words, test_rules, n_steps=200):
    body.eval()
    state = body.init_state()
    hist = []
    correct = total = 0
    with torch.no_grad():
        for step in range(n_steps):
            wlist = RULES[test_rules[(step // 60) % len(test_rules)]]
            actual = wlist[step % len(wlist)]
            if hist:
                prev = w2i[hist[-1]]
                logits, _, state = body.step(prev, state)
                pred_w = all_words[int(torch.argmax(logits))]
            else:
                pred_w = all_words[np.random.randint(len(all_words))]
            if pred_w == actual:
                correct += 1
            total += 1
            _, _, state = body.step(w2i[actual], state)
            state = tuple(s.detach() for s in state)
            hist.append(actual)
    return correct / max(total, 1)


def distill_chars(body, grains, tok_map, steps=500):
    """字符级粗蒸馏: 用句尾字符对齐教师hidden(教师全句语义浓缩在末token)"""
    opt = torch.optim.Adam(body.parameters(), lr=0.001)
    texts = list(grains.keys())
    losses = []
    for it in range(steps):
        text = texts[it % len(texts)]
        gh = grains[text]  # [seq, 896]
        # 用文本最后一个字(全句语义浓缩处)做目标, 循环整句输入
        chars = list(text)
        state = body.init_state()
        opt.zero_grad()
        lossv = None
        for i, ch in enumerate(chars):
            if ch not in tok_map:
                continue
            _, gpred, state = body.step_char(tok_map[ch], state)
            # 每字对齐教师对应行(近似)
            hidx = min(i, len(gh)-1)
            target = torch.tensor(gh[hidx], dtype=torch.float32)
            if lossv is None:
                lossv = nn.functional.mse_loss(gpred[0], target)
            else:
                lossv = lossv + nn.functional.mse_loss(gpred[0], target)
        if lossv is not None:
            lossv.backward()
            opt.step()
            losses.append(lossv.item())
        if (it+1) % 100 == 0:
            print('  蒸馏 %d/%d loss=%.3f' % (it+1, steps, float(np.mean(losses[-50:]))), flush=True)
    return body


def make_tok_map(all_words, grains):
    chars = set()
    for w in all_words:
        chars.update(w)
    for t in grains.keys():
        chars.update(t)
    return {c: i for i, c in enumerate(sorted(chars))}


def main():
    torch.manual_seed(0); np.random.seed(0)
    grains = torch.load('/root/autodl-tmp/life1/grains.pt', map_location='cpu', weights_only=False)
    print('V154b 纹路蒸馏 | grains %d条 dim=%d' % (len(grains), next(iter(grains.values())).shape[1]), flush=True)
    all_words = sorted(set(w for ws in RULES.values() for w in ws))
    w2i = {w: i for i, w in enumerate(all_words)}
    n_vocab = len(all_words)
    tok_map = make_tok_map(all_words, grains)
    n_tok = len(tok_map)
    train_names = ['season', 'color', 'num', 'sky']
    test_names = ['season', 'num', 'fruit']
    # --- 素泥: 直接学规则 ---
    print('\n--- 素泥sLSTM ---', flush=True)
    b1 = Body(n_vocab, n_char=len(tok_map))
    b1 = train_rules(b1, w2i, train_names, 2000)
    ga = eval_gen(b1, w2i, all_words, test_names)
    print('  泛化(季节+数字+水果): %.0f%%' % (100*ga), flush=True)
    # --- 带纹路: 先蒸馏再学规则 ---
    print('\n--- 蒸馏纹路sLSTM ---', flush=True)
    b2 = Body(n_vocab, n_char=len(tok_map))
    b2 = distill_chars(b2, grains, tok_map, 500)
    b2 = train_rules(b2, w2i, train_names, 2000)
    gb = eval_gen(b2, w2i, all_words, test_names)
    print('  泛化(季节+数字+水果): %.0f%%' % (100*gb), flush=True)
    print('\n=== 对比: 素泥 %.0f%% vs 带纹路 %.0f%% ===' % (100*ga, 100*gb), flush=True)
    print('[done]', flush=True)


if __name__ == '__main__':
    main()
