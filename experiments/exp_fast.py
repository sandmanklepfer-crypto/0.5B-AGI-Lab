# -*- coding: utf-8 -*-
"""exp_fast.py — 极速空间蒸馏实验: 只训「最后一层」+ 只测 8 条, 一次出结果"""
import numpy as np, time, json
import np_qwen, np_train2
from np_tok import Tok
from gen_short import build

t00=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%.0fs] 模型就绪"%(time.time()-t00),flush=True)

def enc(u,a=None):
    p=TK.encode("<|im_start|>user\n"+u+"<|im_end|>\n<|im_start|>assistant\n")
    if a is None: return p
    return p+TK.encode(a)+[151645]

tr=np_train2.TrainQwen(M, layers=[23], r=8, alpha=16, seed=0)
print("[%.0fs] LoRA就绪(第23层, %d参数)"%(time.time()-t00,
      sum(l.A.size+l.B.size for l in tr.loras.values())),flush=True)

test=build(12,seed=99)
def ev(tag,n=8):
    ok=0
    for d in test[:n]:
        ids=enc(d["q"])
        lg,_,_,_=tr.forward(ids)
        if int(np.argmax(lg))==TK.encode(d["a"])[0]: ok+=1
    print("[%.0fs] %s 准确率 %d/%d"%(time.time()-t00,tag,ok,n),flush=True)
    return ok

ev("训练前")
train=build(80,seed=11)
lr=0.05
t0=time.time()
for s in range(25):
    d=train[s]
    ids=enc(d["q"],d["a"])
    loss,prob=tr.train_step(ids[:-1], ids[-1], lr)
    if s%5==0: print("[%.0fs] step%2d loss=%.3f (%.1fs/步)"%(time.time()-t00,s,loss,
        (time.time()-t0)/max(s,1)),flush=True)
ev("训练后")
print("[%.0fs] 完成"%(time.time()-t00),flush=True)
