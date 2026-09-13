#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''real_chat2.py — 0.5B 续写模式: 看它到底能生成什么中文'''
import numpy as np, time, sys
sys.path.insert(0, '/workspace')
t0 = time.time()
from np_tok import Tok
import qwen_np

TK = Tok('/workspace/w.gguf', verbose=False)
M = qwen_np.Model(24, None)
print("[%.1fs] 模型就绪 (24层, 全词表, 加载 %.1fs)" % (time.time() - t0, M.load_t), flush=True)

PROMPTS = [
    "人工智能是计算机科学的一个分支，它",
    "学习编程最好的方法是",
]
GEN = 6
rng = np.random.RandomState(0)

for pi, p in enumerate(PROMPTS):
    ids = TK.encode(p)
    print("\n" + "=" * 72)
    print("【续写 %d】开头: %s" % (pi + 1, p))
    outs = {}
    # 贪心
    out = []
    t1 = time.time()
    for _ in range(GEN):
        lg = M.forward(np.array(ids + out))[-1]
        out.append(int(np.argmax(lg)))
    dt = time.time() - t1
    outs['贪心'] = out
    # 采样 (top-20)
    out2 = []; seed = 1
    t2 = time.time()
    for _ in range(GEN):
        lg = M.forward(np.array(ids + out2))[-1]
        top = np.argsort(-lg)[:20]
        p20 = np.exp(lg[top] - lg[top].max()); p20 /= p20.sum()
        out2.append(int(rng.choice(top, p=p20)))
    dt2 = time.time() - t2
    outs['采样'] = out2
    try:
        print("  贪心: %s" % TK.decode(outs['贪心']))
    except Exception:
        print("  贪心 ids: %s" % outs['贪心'])
    try:
        print("  采样: %s" % TK.decode(outs['采样']))
    except Exception:
        print("  采样 ids: %s" % outs['采样'])
    print("  (贪心 %.1fs / 采样 %.1fs, 各 %d token)" % (dt, dt2, GEN))
    print("  贪心 ids: %s" % outs['贪心'])
    print("  采样 ids: %s" % outs['采样'])

print("\n[总耗时 %.1fs]" % (time.time() - t0))
