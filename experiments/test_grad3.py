# -*- coding: utf-8 -*-
"""test_grad3.py — 用「序列长度=1」验证反向内核(排除 BPTT 干扰, 先确认核心正确)"""
import numpy as np, time
import np_qwen, np_train

t0=time.time(); m = np_qwen.Qwen2("/workspace/w.gguf", verbose=False)
print("模型加载 %.1fs" % (time.time()-t0))

tr = np_train.TrainQwen(m, lora_layers=[0], r=8, alpha=16, seed=1)
rng = np.random.RandomState(7)
for k, lo in tr.loras.items():
    lo.B = (rng.randn(*lo.B.shape)*0.05).astype(np.float32)

# 序列长度 = 1 (无历史 → 梯度路径完整)
inp = [108386]
tgt = 6313

def loss_only():
    logits, allx, caches, kvs = tr.forward_seq(inp)
    lg = logits - logits.max(); q = np.exp(lg); q = q/q.sum()
    return -np.log(q[tgt]+1e-12)

loss, p = tr.loss_and_backward(inp, [tgt])
print("loss=%.4f (直接前向算=%.4f)" % (loss, loss_only()))

eps=2e-3
print("\n梯度检验(seq=1):")
ok=0; bad=0
for (L,which), lo in list(tr.loras.items()):
    for name,P,G in (("A",lo.A,lo.gA),("B",lo.B,lo.gB)):
        for _ in range(2):
            ij=tuple(rng.randint(0,s) for s in P.shape)
            o=P[ij]
            P[ij]=o+eps; lp=loss_only()
            P[ij]=o-eps; lm=loss_only()
            P[ij]=o
            num=(lp-lm)/(2*eps); ana=G[ij]
            scale=max(abs(num),abs(ana),1e-9)
            rel=abs(num-ana)/scale
            f="OK" if rel<0.08 else "BAD"
            if rel<0.08: ok+=1
            else: bad+=1
            print("  L%d.%s.%s%s 解析=%+.5e 数值=%+.5e 相对=%.2e %s"%(L,which,name,ij,ana,num,rel,f))
print("\n通过 %d / 失败 %d" % (ok,bad))
