import glob, numpy as np
from safetensors import safe_open
def get(d):
    fs=glob.glob(d+"/*.safetensors")
    with safe_open(fs[0],framework="pt") as f:
        for k in f.keys():
            if 'layers.12.mlp.down_proj' in k:
                return f.get_tensor(k).float().numpy()
    return None
b=get("/root/autodl-tmp/qwen25_base_raw")
a=get("/root/autodl-tmp/life1/antiheb_05b")
if b is not None and a is not None:
    d=a-b
    print(f"base norm      = {np.linalg.norm(b):.6f}")
    print(f"antiheb norm   = {np.linalg.norm(a):.6f}")
    print(f"delta norm     = {np.linalg.norm(d):.6f}")
    print(f"相对变化       = {np.linalg.norm(d)/np.linalg.norm(b):.3e}")
    print(f"最大单点差异   = {np.abs(d).max():.6f}")
    print(f"base 最大值    = {np.abs(b).max():.6f}")
    print(f"受影响元素占比 = {(np.abs(d)>1e-6).mean():.1%}")
    print(f"非零 delta 数  = {(np.abs(d)>1e-8).sum()} / {d.size}")
else:
    print("读取失败")
