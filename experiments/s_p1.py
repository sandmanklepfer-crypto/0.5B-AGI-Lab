import glob, numpy as np
from safetensors import safe_open
BASE="/root/autodl-tmp/qwen25_base_raw"
AH="/root/autodl-tmp/life1/antiheb_05b"
fb=glob.glob(BASE+"/*.safetensors")[0]
fa=glob.glob(AH+"/*.safetensors")[0]
print("base file:",fb.split('/')[-1])
print("ah   file:",fa.split('/')[-1])
res=[]
with safe_open(fb,framework="pt") as bf, safe_open(fa,framework="pt") as af:
    keys=[k for k in bf.keys() if k in set(af.keys())]
    print("共同张量:",len(keys))
    for k in keys:
        b=bf.get_tensor(k).float().numpy(); a=af.get_tensor(k).float().numpy()
        if b.shape!=a.shape: continue
        d=a-b; nb=np.linalg.norm(b); nd=np.linalg.norm(d)
        res.append((nd/(nb+1e-12), k, nb, nd, float(np.abs(d).max())))
res.sort(reverse=True)
print()
print("=== 变化最大的12个张量 ===")
for rel,k,nb,nd,mx in res[:12]:
    print(f"  {k[:58]:58s} rel={rel:.3e} ||d||={nd:.4f} max={mx:.5f}")
r=np.array([x[0] for x in res])
print()
print("=== 统计 ===")
print(f"  张量数={len(res)}")
print(f"  相对变化: 中位={np.median(r):.3e}  最大={r.max():.3e}")
print(f"  rel>1e-2 的张量数: {(r>1e-2).sum()}")
print(f"  rel>1e-3 的张量数: {(r>1e-3).sum()}")
print(f"  rel>1e-4 的张量数: {(r>1e-4).sum()}")
