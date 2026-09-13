# -*- coding: utf-8 -*-
"""frag_analysis.py — 验证「碎片」是否真实存在且紧凑(纯权重代数, 零训练)
   核心问题: 权重里的「能力」是否集中在极少数方向? (低秩 = 碎片)
   方法: SVD 奇异值谱 → 达到 50%/90%/99% 能量需要多少秩
"""
import numpy as np, time
from gguf import GGUFReader
from gguf.quants import dequantize

t0=time.time()
r=GGUFReader('/workspace/w.gguf')
names=['blk.0.attn_q.weight','blk.0.attn_v.weight','blk.0.ffn_gate.weight','blk.0.ffn_down.weight',
       'blk.12.attn_q.weight','blk.12.attn_v.weight','blk.12.ffn_gate.weight','blk.12.ffn_down.weight',
       'blk.23.attn_q.weight','blk.23.ffn_down.weight', 'token_embd.weight']
W={}
for t in r.tensors:
    if t.name in names:
        W[t.name]=dequantize(t.data,t.tensor_type).astype(np.float32)
print("加载 %d 个权重 %.1fs\n"%(len(W),time.time()-t0))

print("%-26s %-14s %6s %6s %6s %8s  %s"%("张量","形状","r50","r90","r99","满秩","压缩比(r90)"))
print("-"*88)
rows=[]
for n in names:
    if n not in W: continue
    w=W[n]
    if w.ndim!=2: continue
    U,s,Vt=np.linalg.svd(w, full_matrices=False)
    e=s**2; e=e/e.sum(); cum=np.cumsum(e)
    def ra(p):
        i=int(np.searchsorted(cum,p)); return i+1
    r50,r90,r99=ra(.5),ra(.9),ra(.99)
    full=len(s)
    rows.append((n,r90,full))
    print("%-26s %-14s %6d %6d %6d %8d   %5.1fx"%(n,str(tuple(w.shape)),r50,r90,r99,full,full/r90))

print("\n=== 结论 ===")
if rows:
    avg=np.mean([f/r for _,r,f in rows])
    print("平均压缩比(90%%能量): %.1f 倍"%avg)
    print("→ 即: 用 %.1f%% 的参数量就能承载 90%% 的权重能量"%(100/avg))
