# -*- coding: utf-8 -*-
"""极简实验: 4条测试 + 12步训练, 一次出结果"""
import numpy as np, time
import np_qwen, np_train2
from np_tok import Tok
from gen_short import build

t0=time.time()
TK=Tok("/workspace/w.gguf",verbose=False)
M=np_qwen.Qwen2("/workspace/w.gguf",verbose=False)
print("[%05.1fs] 模型就绪"% (time.time()-t0),flush=True)

def enc(u,a=None):
    p=TK.encode("<|im_start|>user\n"+u+"<|im_end|>\n<|im_start|>assistant\n")
    if a is None: return p
    return p+TK.encode(a)+[151645]

tr=np_train2.TrainQwen(M, layers=[23], r=8, alpha=16, seed=0)
print("[%05.1fs] LoRA(第23层)就绪"%(time.time()-t0),flush=True)

test=build(6,seed=99)
def ev(tag):
    ok=0; N=4
    for d in test[:N]:
        lg,_,_,_=tr.forward(enc(d["q"]))
        if int(np.argmax(lg))==TK.encode(d["a"])[0]: ok+=1
    print("[%05.1fs] %s: %d/%d"%(time.time()-t0,tag,ok,N),flush=True)
    return ok

before=ev("训练前")
train=build(80,seed=11); lr=0.05
for s in range(12):
    d=train[s]
    ids=enc(d["q"],d["a"])
    loss,prob=tr.train_step(ids[:-1],ids[-1],lr)
    print("[%05.1fs] step%2d loss=%.3f"%(time.time()-t0,s,loss),flush=True)
after=ev("训练后")
print("[%05.1fs] === %d/%d → %d/%d ==="%(time.time()-t0,before,4,after,4),flush=True)
