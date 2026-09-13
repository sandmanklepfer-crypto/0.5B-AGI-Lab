# -*- coding: utf-8 -*-
"""第三层测试: 语义转化 (自然语言描述 → 形式任务)
   跑在本地 w.gguf (0.5B base)
"""
import os, sys, time
OUT='/workspace/_l3_out.txt'
def log(s):
    with open(OUT,'a',encoding='utf-8') as f: f.write(s+"\n")

# ---- 语义转化题 (第三层: 不是换说法, 是要懂意思) ----
TESTS=[
 ("乘法-面积",  "长方形面积等于长乘以宽。一个长方形长37厘米宽23厘米，它的面积是"),
 ("乘法-速度",  "距离等于速度乘以时间。一辆车每秒走37米，走了23秒，走的路程是"),
 ("乘法-重复",  "37个23相加，用乘法表示就是"),
 ("除法-平均",  "把46个苹果平均分给23个人，每人分到"),
 ("减法-剩余",  "篮子里有37个苹果，吃掉23个，还剩"),
 ("加法-合并",  "小明有37本书，小红有23本，两人一共"),
 ("语义-转化",  "每份23个，共37份，总共多少个？用算式写："),
]
try:
    sys.path.insert(0,'/workspace')
    import numpy as np
    log(f"[{time.time():.0f}] 导入numpy完成")
    from np_tok import Tok
    t0=time.time()
    TK=Tok('/workspace/w.gguf',verbose=False)
    log(f"词表就绪 {time.time()-t0:.1f}s")
    import qwen_np
    M=qwen_np.Model(24,None)
    log(f"模型就绪 {time.time()-t0:.1f}s (加载{M.load_t:.1f}s)")
    for tag,q in TESTS:
        ids=TK.encode(q)
        out=[]
        t1=time.time()
        for _ in range(8):
            lg=M.forward(np.array(ids+out))[-1]
            out.append(int(np.argmax(lg)))
        txt=TK.decode(out).replace("\n"," ")
        log(f"\n[{tag}]")
        log(f"  输入: {q}")
        log(f"  续写: {txt}")
        log(f"  ({time.time()-t1:.0f}s)")
    log("\nL3_DONE")
except Exception as e:
    import traceback
    log("ERROR: "+traceback.format_exc()[:600])
