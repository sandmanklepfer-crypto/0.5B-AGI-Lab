import sys
sys.path.insert(0,'/root/autodl-tmp/llama.cpp/gguf-py')
import numpy as np
from gguf import GGUFReader
r=GGUFReader('/root/autodl-tmp/calc_v1.gguf')
for t in r.tensors:
    if t.name=='token_embd.weight':
        W=t.data.view(np.float16).astype(np.float32); break
d=np.fromfile('/root/autodl-tmp/l23/d_refusal.bin',np.float32)
d=d/(np.linalg.norm(d)+1e-9)
s=W@d
# 负方向 (bias = -150*s) 已生成 bias_b150.bin
# 正方向 (bias = +150*s)
(+150.0*s).astype(np.float32).tofile('/root/autodl-tmp/bias_pos150.bin')
print("bias_pos150 written, mean=%.4f"%(150*s).mean())
# 也做一个 500 强度的
(-500.0*s).astype(np.float32).tofile('/root/autodl-tmp/bias_neg500.bin')
print("bias_neg500 written")
print("BOTH_DONE")
