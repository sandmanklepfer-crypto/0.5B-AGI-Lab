# -*- coding: utf-8 -*-
"""test_converge.py — 收敛性验证(最实用的梯度正确性判据)
   固定一个小样本集, 反复训练: loss 应持续下降; 若梯度方向错 → loss 不降或发散
"""
import numpy as np, time
import np_qwen, np_train2
from np_tok import Tok

tk=Tok("/workspace/w.gguf", verbose=False)
t0=time.time(); m=np_qwen.Qwen2("/workspace/w.gguf", verbose=False)
print("模型加载 %.1fs"%(time.time()-t0))

# 造一个极简任务(记忆一个映射): 让模型学会「A → B」
txt = "1+1=2"
ids = tk.encode(txt)
print("训练目标:", txt, "→ tokens", ids)

tr = np_train2.TrainQwen(m, layers=[21,22,23], r=8, alpha=16, seed=0)
print("LoRA: %d层 %d参数 (%.1f KB)"%(len(tr.layers), sum(l.A.size+l.B.size for l in tr.loras.values()),
      tr.nbytes()/1024))

# 序列 = ids[:-1] 预测 ids[-1]
inp = ids[:-1]; tgt = ids[-1]
lr=0.05
losses=[]
t0=time.time()
for step in range(60):
    loss, prob = tr.train_step(inp, tgt, lr)
    losses.append(loss)
    if step%10==0 or step==59:
        print("  step %2d  loss=%.4f  p(target)=%.4f  (%.1fs)"%(step, loss, prob, time.time()-t0))

first=np.mean(losses[:5]); last=np.mean(losses[-5:])
print("\n首5步均值 %.4f → 末5步均值 %.4f"%(first,last))
if last < first*0.8: print("✅ loss 显著下降 → 梯度方向正确, 训练有效")
elif last < first: print("⚠️ loss 略降 → 梯度大体正确(precision有限)")
else: print("❌ loss 未降 → 梯度有问题")
