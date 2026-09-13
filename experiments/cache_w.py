# -*- coding: utf-8 -*-
"""cache_w.py — 把 GGUF 解量化一次, 存成 npy 缓存(后续实验加载从14s→3s)"""
import numpy as np, time, os, sys
from gguf import GGUFReader
from gguf.quants import dequantize

SRC="/workspace/w.gguf"; DST="/workspace/wcache.npz"
t0=time.time()
r=GGUFReader(SRC)
d={}
for t in r.tensors:
    d[t.name]=dequantize(t.data,t.tensor_type).astype(np.float16)
print("解量化 %.1fs, %d张量, %.2fGB(fp16)"%(time.time()-t0,len(d),
      sum(v.nbytes for v in d.values())/2**30))
np.savez(DST, **d)
print("已缓存 → %s (%.1fGB, %.0fs)"%(DST, os.path.getsize(DST)/2**30, time.time()-t0))
