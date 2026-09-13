import sys
sys.path.insert(0,'/root/autodl-tmp/llama.cpp/gguf-py')
import numpy as np
from gguf import GGUFReader
r=GGUFReader('/root/autodl-tmp/calc_v1.gguf')
for t in r.tensors:
    if t.name=='token_embd.weight':
        W=t.data.view(np.float16).astype(np.float32); break
d=np.fromfile('/root/autodl-tmp/l23/d_refusal.bin',np.float32)
print("d norm(原始)", float(np.linalg.norm(d)))
d=d/(np.linalg.norm(d)+1e-9)
s=W@d
for a in [100.0,150.0,300.0]:
    b=(-a*s).astype(np.float32)
    b.tofile(f'/root/autodl-tmp/bias_b{int(a)}.bin')
    print(f"alpha={a}: bias mean={b.mean():.3f} std={b.std():.3f} max={b.max():.2f} min={b.min():.2f}")
# top tokens
idx=np.argsort(-(-s))[:10]
print("top-正向bias token id:", idx.tolist())
print("BIG_DONE")
