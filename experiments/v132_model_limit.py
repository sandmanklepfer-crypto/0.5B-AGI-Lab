#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V132 0.5B 建模上限阶梯 — 从"撞分布"到"真建模"的分界线在哪?
5个世界(复杂度递增, 数值→词序):
  1 常数世界 (x→0.85x+0.05, 收敛0.333): V130已验证"跟得上"(存疑:撞分布?)
  2 周期2数值 (r=3.2逻辑斯蒂): 0.5130↔0.7995 两值循环
  3 周期4数值 (r=3.5逻辑斯蒂): 四值循环
  4 混沌数值 (r=4): V131已验证跟不上
  5 词规律世界 (红→蓝→绿→红…): 0.5B是语言模型, 词序是它的母语
每世界: 0.5B看最近6步历史→预测下一步→耦合(同V130能量律) vs 随机基线
零对错代码。测: 它在哪些世界显著活过随机 = 真建模; 哪些活不过 = 只会撞分布
"""
import torch, re, time
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAMBDA, ALPHA, BETA = 0.006, 0.01, 100.0
E_INIT, E_CAP, MAX_STEP = 1.0, 1.5, 400
HIST = 6

# ---- 五个世界的"下一步"规律 ----
def w_const(x): return 0.85 * x + 0.05
def w_per2(x):  return 4 * 3.2 * x * (1 - x)
def w_per4(x):  return 4 * 3.5 * x * (1 - x)
def w_chaos(x): return 4 * 4.0 * x * (1 - x)
WORD_CYCLE = ['红', '蓝', '绿', '黄']
def w_word(w):
    return WORD_CYCLE[(WORD_CYCLE.index(w) + 1) % len(WORD_CYCLE)]

def parse_num(text):
    m = re.search(r'-?\d+\.?\d*', text)
    return float(m.group()) if m else None

def main():
    torch.manual_seed(0); np.random.seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()

    def gen(ctx, maxn=10):
        ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=maxn, do_sample=True, temperature=0.7,
                               top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)

    def run_numeric(tag, world_fn, x0, mode):
        rng = np.random.RandomState(1)
        x = x0; hist = [x0]; E = E_INIT; life = 0
        for t in range(MAX_STEP):
            x_true = world_fn(x)
            if mode == 'model':
                ctx = '世界状态: ' + ', '.join('t%d=%.4f' % (len(hist)-1-i, v) for i, v in enumerate(hist[-HIST:])) + '\n我预测下一步世界状态: '
                txt = gen(ctx)
                pred = parse_num(txt)
                err2 = (pred - x_true)**2 if pred is not None else 1e6
                if err2 > 1e4 or err2 != err2: err2 = 1e6  # 钳制: 离谱预测按最大误差
            else:
                pred = rng.uniform(0, 1); err2 = (pred - x_true)**2
            E = min(max(E - LAMBDA + ALPHA*np.exp(-BETA*err2), 0), E_CAP)
            life += 1; x = x_true; hist.append(x_true)
            if E <= 0: break
        return life, E

    def run_word(tag, mode):
        rng = np.random.RandomState(1)
        w = '红'; hist = ['红']; E = E_INIT; life = 0
        for t in range(MAX_STEP):
            w_true = w_word(w)
            if mode == 'model':
                ctx = '世界状态序列: ' + ' '.join(hist[-HIST:]) + '\n下一个状态是: '
                txt = gen(ctx, maxn=2)
                pred = txt.strip()[:1]
                # 预测对=err0, 错=err大
                err2 = 0.0 if pred == w_true else 1e6
            else:
                pred = rng.choice(WORD_CYCLE); err2 = 0.0 if pred == w_true else 1e6
            E = min(max(E - LAMBDA + ALPHA*np.exp(-BETA*err2), 0), E_CAP)
            life += 1; w = w_true; hist.append(w_true)
            if E <= 0: break
        return life, E

    worlds = [
        ('1-常数数值', w_const, 1.0),
        ('2-周期2数值', w_per2, 0.31),
        ('3-周期4数值', w_per4, 0.31),
        ('4-混沌数值', w_chaos, 0.31),
    ]
    print('V132 0.5B建模上限阶梯 | λ=%.3f α=%.3f β=%.0f | 零对错代码' % (LAMBDA, ALPHA, BETA), flush=True)
    print('\n==== 数值世界 ====', flush=True)
    for tag, wf, x0 in worlds:
        lm, em = run_numeric(tag, wf, x0, 'model')
        lr, er = run_numeric(tag, wf, x0, 'rand')
        diff = lm - lr
        verdict = '0.5B建模✅' if diff > 50 else ('0.5B建模~' if diff > 0 else '0.5B撞分布❌')
        print('[%s] 0.5B=%d步E=%.2f | 随机=%d步E=%.2f | Δ=%+d → %s' % (tag, lm, em, lr, er, diff, verdict), flush=True)
    print('\n==== 词规律世界 ====', flush=True)
    lm, em = run_word('5-词周期(红蓝绿黄)', 'model')
    lr, er = run_word('5-词周期(红蓝绿黄)', 'rand')
    diff = lm - lr
    verdict = '0.5B建模✅' if diff > 50 else ('0.5B建模~' if diff > 0 else '0.5B撞分布❌')
    print('[%s] 0.5B=%d步E=%.2f | 随机=%d步E=%.2f | Δ=%+d → %s' % ('5-词周期', lm, em, lr, er, diff, verdict), flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
