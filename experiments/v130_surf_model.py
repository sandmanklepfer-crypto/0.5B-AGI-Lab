#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V130 耦合生命体(冲浪) — 0.5B × 真实演化世界, 全程零"对/错/奖/罚"代码
世界: x_{t+1} = 0.85*x_t + 0.05 (真实迭代系统, 收敛到 0.333…, 不依赖模型)
生命体: 每步看世界最近4个状态文本, 续写"预测下一步" → 提取数字 = 提议
耦合(唯一能量律, 势能函数非裁判):
  dE = -λ + α·exp(-β·err²)      λ=代谢耗散(活着就要耗)
                                 α=耦合效率(跟得上世界给的能流)
                                 β=耦合锐度, err=|提议-世界实际演化|
  无效提议(没说出数字) = 无法耦合 = 只有 -λ → 必死
对照组: A=0.5B耦合  B=随机乱猜  C=废话(从不给数字)
全程无任何 "if 对/错/回血/扣分" 逻辑, 无人工对错表
"""
import torch, re, time
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer

MDIR = '/root/autodl-tmp/life1/antiheb_05b'
LAMBDA = 0.004      # 代谢耗散/步
ALPHA = 0.006       # 耦合回馈上限
BETA = 10.0         # 耦合锐度
E_INIT = 1.0
E_CAP = 1.5
MAX_STEP = 600
HIST = 4            # 给模型看几个历史状态

def world_next(x):
    return 0.85 * x + 0.05

def parse_num(text):
    m = re.search(r'-?\d+\.?\d*', text)
    return float(m.group()) if m else None

def ctx_text(hist):
    parts = ['t-%d=%.4f' % (len(hist)-1-i, v) for i, v in enumerate(hist)]
    return '世界状态: ' + ', '.join(parts) + '\n我预测下一步世界状态: '

def main():
    torch.manual_seed(0)
    np.random.seed(0)
    tok = AutoTokenizer.from_pretrained('/root/autodl-tmp/qwen25_base_raw')
    model = AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.float16).to('cuda').eval()

    def model_propose(ctx):
        ids = tok(ctx, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = model.generate(ids, max_new_tokens=12, do_sample=True, temperature=0.7,
                               top_p=0.9, pad_token_id=tok.eos_token_id)
        return tok.decode(o[0][ids.shape[1]:], skip_special_tokens=True)

    def run(tag, mode, T=MAX_STEP):
        rng = np.random.RandomState(1)
        x = 1.0
        hist = [1.0]
        E = E_INIT
        life = 0
        ok_pred = 0
        t0 = time.time()
        print('\n[%s] 耦合生命体启动 E=%.2f' % (tag, E), flush=True)
        for t in range(T):
            x_true = world_next(x)               # 世界按自己规律走一步
            if mode == 'model':
                pred_txt = model_propose(ctx_text(hist[-HIST:]))
                pred = parse_num(pred_txt)
                if pred is None:
                    err2 = 1e6                   # 废话: 无法耦合
                else:
                    err2 = (pred - x_true) ** 2
                    ok_pred += 1
            elif mode == 'rand':
                pred = rng.uniform(0, 1)
                err2 = (pred - x_true) ** 2
            else:  # none: 废话, 无提议
                err2 = 1e6
            dE = -LAMBDA + ALPHA * np.exp(-BETA * err2)
            E = min(max(E + dE, 0.0), E_CAP)
            life += 1
            x = x_true
            hist.append(x_true)
            if E <= 0:
                print('  [死] %s 第%d步 能量耗尽' % (tag, t+1), flush=True)
                break
            if (t+1) % 100 == 0:
                print('  [%s %4d步 %.0fs] E=%.3f | pred=%.4f true=%.4f err=%.4f' % (
                    tag, t+1, time.time()-t0, E,
                    pred if mode != 'none' else float('nan'), x_true,
                    err2**0.5 if err2 < 1e3 else float('inf')), flush=True)
        print('[%s] 寿命 %d 步 | 末E=%.3f | 有效提议 %d/%d | %.0fs' % (
            tag, life, E, ok_pred, life, time.time()-t0), flush=True)
        return life, E

    print('V130 耦合生命体 | λ=%.3f α=%.3f β=%.1f | 零对错代码' % (LAMBDA, ALPHA, BETA), flush=True)
    # A: 0.5B 耦合
    life_a, e_a = run('A-0.5B耦合', 'model')
    # B: 随机乱猜 (同一物理)
    life_b, e_b = run('B-随机乱猜', 'rand')
    # C: 废话 (从不给数字)
    life_c, e_c = run('C-废话无提议', 'none')
    print('\n==== 结果 ====', flush=True)
    print('A-0.5B耦合: %d步 E=%.3f' % (life_a, e_a), flush=True)
    print('B-随机乱猜: %d步 E=%.3f' % (life_b, e_b), flush=True)
    print('C-废话无提议: %d步 E=%.3f' % (life_c, e_c), flush=True)
    print('若 A 显著活过 B/C → 0.5B 在纯物理下自发学会跟世界(无需任何对错代码)', flush=True)
    print('[done]', flush=True)

if __name__ == '__main__':
    main()
