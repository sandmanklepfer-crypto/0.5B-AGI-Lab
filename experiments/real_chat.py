#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''real_chat.py — 真的让 0.5B 跑一次对话 (纯numpy, 24层全模型)'''
import numpy as np, time, sys
sys.path.insert(0, '/workspace')
t0 = time.time()

from np_tok import Tok
import qwen_np

print("[%.1fs] 开始加载..." % (time.time() - t0), flush=True)
TK = Tok('/workspace/w.gguf', verbose=False)
print("[%.1fs] 词表就绪 (%d 条)" % (time.time() - t0, len(TK.toks)), flush=True)
M = qwen_np.Model(24, None)
print("[%.1fs] 模型就绪: %d 层, 词表 %d, 加载 %.1fs"
      % (time.time() - t0, M.nlayer, M.V, M.load_t), flush=True)

DIALOG = [
    "你好，请介绍一下你自己。",
]
GEN = 5          # 每个问题生成多少个 token

try:
    dec = TK.decode
except AttributeError:
    def dec(ids):
        return "".join(str(i) for i in ids)

for q in DIALOG:
    prompt = "<|im_start|>user\n%s<|im_end|>\n<|im_start|>assistant\n" % q
    ids = TK.encode(prompt)
    print("\n" + "=" * 70)
    print("用户: %s" % q)
    print("(prompt %d token)" % len(ids))
    out = []
    t1 = time.time()
    for step in range(GEN):
        lg = M.forward(np.array(ids + out))
        nxt = int(np.argmax(lg[-1]))
        out.append(nxt)
        if step == 0:
            print("  [首token %.1fs]" % (time.time() - t1), flush=True)
    dt = time.time() - t1
    txt = dec(out) if dec else str(out)
    print("助手: %s" % txt)
    print("(%d token, 耗时 %.1fs, %.1fs/token)" % (len(out), dt, dt / len(out)))
    print("token ids: %s" % out)

print("\n[总耗时 %.1fs]" % (time.time() - t0))
