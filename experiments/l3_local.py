# -*- coding: utf-8 -*-
"""第三层本地测试: 只问「结构」(该用什么运算), 不问结果
   这样能分离【世界知识】和【算术能力】"""
import numpy as np, time, sys
sys.path.insert(0,'/workspace')
t0=time.time()
from np_tok import Tok
import qwen_np
TK=Tok('/workspace/w.gguf',verbose=False)
M=qwen_np.Model(24, None)
print(f"[{time.time()-t0:.0f}s] 模型就绪 层={M.nlayer} 词表={M.V}", flush=True)

# ★ 只问结构, 不问结果
Q=[
 ("面积(几何)",   "长37米宽23米的长方形，面积应该怎么算？只写算式："),
 ("距离(物理)",   "每秒走37米，走23秒，距离应该怎么算？只写算式："),
 ("总价(生活)",   "每斤37元，买23斤，总价应该怎么算？只写算式："),
 ("乘积(算术)",   "37和23的乘积是多少？只写算式："),
 ("重复加(数学)", "37个23相加，应该怎么算？只写算式："),
]
GEN=12
for tag,q in Q:
    print(f"\n{'='*70}\n[{tag}] {q}", flush=True)
    ids=TK.encode(q)
    out=[]
    for _ in range(GEN):
        lg=M.forward(np.array(ids+out))[-1]
        out.append(int(np.argmax(lg)))
    try: txt=TK.decode(out)
    except Exception: txt=f"(ids:{out})"
    print(f"  模型: {txt}", flush=True)
    print(f"  ids: {out}", flush=True)
print(f"\n总 {time.time()-t0:.0f}s")
print("L3LOCAL_DONE")
