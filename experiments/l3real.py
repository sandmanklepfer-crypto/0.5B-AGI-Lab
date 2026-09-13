# -*- coding: utf-8 -*-
"""第三层真测试: 只问「结构」不问结果 (本地0.5B真前向)"""
import numpy as np, time, sys
sys.path.insert(0,'/workspace')
t0=time.time()
from np_tok import Tok
import qwen_np
TK=Tok('/workspace/w.gguf',verbose=False)
M=qwen_np.Model(24, None)
print(f"[{time.time()-t0:.0f}s] 模型就绪 层={M.nlayer} 词表={M.V}", flush=True)
Q=[
 ("几何-面积", "长37米宽23米的长方形，面积怎么算？算式是："),
 ("物理-距离", "每秒走37米走23秒，距离怎么算？算式是："),
 ("算术",     "37乘以23等于多少？答案是："),
]
for tag,q in Q:
    ids=TK.encode(q); out=[]
    for _ in range(10):
        lg=M.forward(np.array(ids+out))[-1]
        out.append(int(np.argmax(lg)))
    try: txt=TK.decode(out)
    except Exception: txt=str(out)
    print(f"\n[{tag}] {q}\n  -> {txt!r}", flush=True)
print(f"总 {time.time()-t0:.0f}s")
