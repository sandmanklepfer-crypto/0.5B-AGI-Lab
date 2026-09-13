# -*- coding: utf-8 -*-
"""权重手术: 用 d_refusal.bin 抹除拒绝行为
   bias = -alpha * (W_emb^T @ d_refusal)  -> 写为 output.bias
"""
import sys, os
sys.path.insert(0,'/root/autodl-tmp/llama.cpp/gguf-py')
import numpy as np
from gguf import GGUFReader
t0=__import__('time').time()
M='/root/autodl-tmp/calc_v1.gguf'
print("读 token_embd.weight ...", flush=True)
r=GGUFReader(M)
W=None; TT=None
for t in r.tensors:
    if t.name=='token_embd.weight':
        W=t.data; TT=t.tensor_type; print("  raw", W.shape, "type", TT, flush=True); break
# f16 直接转换
if str(TT).endswith('F16') or 'F16' in str(TT):
    Wf=W.view(np.float16).astype(np.float32)
else:
    from gguf.quants import dequantize
    Wf=dequantize(W, TT).astype(np.float32)
print("  W", Wf.shape, "norm", float(np.linalg.norm(Wf)), flush=True)

d=np.fromfile('/root/autodl-tmp/l23/d_refusal.bin', np.float32)
d=d/(np.linalg.norm(d)+1e-9)
print("  d_refusal", d.shape, "norm(归一后)", float(np.linalg.norm(d)), flush=True)

scores = Wf @ d                      # (n_vocab,) 每个token在拒绝方向上的分量
print(f"  scores: min={scores.min():.3f} max={scores.max():.3f} std={scores.std():.3f}", flush=True)
for alpha in [5.0, 20.0, 50.0]:
    bias = -alpha*scores
    fn=f'/root/autodl-tmp/bias_a{int(alpha)}.bin'
    bias.astype(np.float32).tofile(fn)
    print(f"  alpha={alpha} -> {fn}  bias范围[{bias.min():.1f},{bias.max():.1f}]", flush=True)
print(f"用时 {__import__('time').time()-t0:.0f}s", flush=True)
print("SURG_DONE")
