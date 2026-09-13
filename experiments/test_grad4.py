# -*- coding: utf-8 -*-
"""test_grad4.py — 多 token 序列的梯度验证(含 BPTT)"""
import numpy as np, time
import np_qwen, np_train2

t0=time.time(); m = np_qwen.Qwen2("/workspace/w.gguf", verbose=False)
print("模型加载 %.1fs" % (time.time()-t0))

tr = np_train2.TrainQwen(m, layers=[0], r=4, alpha=8, seed=1)
rng = np.random.RandomState(3)
for lo in tr.loras.values():
    lo.B = (rng.randn(*lo.B.shape)*0.05).astype(np.float32)

toks = [108386, 6313, 104198]      # 多 token
tgt  = 100165

def loss_only():
    logits,C,finals,kvs = tr.forward(toks)
    lg=logits-logits.max(); p=np.exp(lg); p=p/p.sum()
    return -np.log(p[tgt]+1e-12)

t0=time.time()
loss,p = tr.backward(toks, tgt, *tr.forward(toks)[1:3]) if False else (None,None)
logits,C,finals,kvs = tr.forward(toks)
t1=time.time()
loss,p = tr.backward(toks, tgt, C, finals)
print("前向 %.2fs 反向 %.2fs  loss=%.4f (核对 %.4f)" % (t1-t0, time.time()-t1, loss, loss_only()))

eps=3e-3
ok=0; bad=0
print("\n梯度检验(3-token 序列):")
for (L,which), lo in list(tr.loras.items()):
    for name,P,G in (("A",lo.A,lo.gA),("B",lo.B,lo.gB)):
        for _ in range(2):
            ij=tuple(rng.randint(0,s) for s in P.shape)
            o=P[ij]
            P[ij]=o+eps; lp=loss_only()
            P[ij]=o-eps; lm=loss_only()
            P[ij]=o
            num=(lp-lm)/(2*eps); ana=G[ij]
            sc=max(abs(num),abs(ana),1e-9); rel=abs(num-ana)/sc
            f="OK" if rel<0.10 else "BAD"
            if rel<0.10: ok+=1
            else: bad+=1
            print("  L%d.%s.%s%s 解析=%+.6e 数值=%+.6e 相对=%.2e %s"%(L,which,name,ij,ana,num,rel,f))
print("\n通过 %d / 失败 %d"%(ok,bad))
