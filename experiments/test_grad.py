# -*- coding: utf-8 -*-
"""test_grad.py — 数值梯度验证(确认手写反向正确)"""
import numpy as np, time
import np_qwen, np_train
from np_tok import Tok

tk = Tok("/workspace/w.gguf", verbose=False)
t0=time.time(); m = np_qwen.Qwen2("/workspace/w.gguf", verbose=False)
print("模型加载 %.1fs" % (time.time()-t0))

tr = np_train.TrainQwen(m, lora_layers=[0], r=8, alpha=16, seed=1)
rng = np.random.RandomState(7)
for k, lo in tr.loras.items():
    lo.B = (rng.randn(*lo.B.shape)*0.02).astype(np.float32)

seq = tk.encode("你好！我是")
inp = seq[:-1]; tgt = seq[-1]
print("输入:", inp, "预测:", tgt, repr(tk.decode([tgt])), "| LoRA参数:", tr.num_params())

def loss_only():
    logits, allx, caches, kvs = tr.forward_seq(inp)
    lg = logits - logits.max(); q = np.exp(lg); q = q/q.sum()
    return -np.log(q[tgt]+1e-12)

t0=time.time()
loss, p = tr.loss_and_backward(inp, [tgt])
print("前向+反向 %.2fs  loss=%.4f  (纯前向 %.3fs)" % (time.time()-t0, loss, time.time()-t0))
print("  纯前向单次: %.3fs" % ((lambda: (time.time(), loss_only(), time.time()))()[2] if False else 0))

eps=1e-3
print("\n梯度检验:")
ok=0; bad=0
for (L,which), lo in list(tr.loras.items()):
    for name,P,G in (("A",lo.A,lo.gA),("B",lo.B,lo.gB)):
        for _ in range(3):
            ij=tuple(rng.randint(0,s) for s in P.shape)
            o=P[ij]
            P[ij]=o+eps; lp=loss_only()
            P[ij]=o-eps; lm=loss_only()
            P[ij]=o
            num=(lp-lm)/(2*eps); ana=G[ij]
            rel=abs(num-ana)/(abs(num)+abs(ana)+1e-9)
            f="OK" if rel<0.05 else "BAD"
            if rel<0.05: ok+=1
            else: bad+=1
            print("  L%d.%s.%s%s 解析=%+.5e 数值=%+.5e 误差=%.2e %s"%(L,which,name,ij,ana,num,rel,f))
print("\n通过 %d / 失败 %d" % (ok,bad))
