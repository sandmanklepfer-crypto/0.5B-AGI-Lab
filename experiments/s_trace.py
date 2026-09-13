import sys, glob, json
sys.path.insert(0,'/root/autodl-tmp/llama.cpp/gguf-py')
import numpy as np
print("="*70)
print("[1] GGUF 元数据")
from gguf import GGUFReader
r = GGUFReader('/root/autodl-tmp/qwen05b_fp16.gguf')
for k in ['general.name','general.architecture','general.basename','general.finetune','general.version']:
    if k in r.fields:
        try: print("   ",k,"=",r.fields[k].contents())
        except Exception as e: print("   ",k,"ERR")
print("    张量数:",len(r.tensors))
print()
print("="*70)
print("[2] 权重范数对比 (blk.12.ffn_down / mlp.down_proj)")
# GGUF
for t in r.tensors:
    if 'blk.12.ffn_down' in t.name:
        try:
            from gguf.quants import dequantize
            d = dequantize(t.data, t.tensor_type).astype(np.float32)
            print(f"    qwen05b_fp16.gguf  {t.name}  norm={np.linalg.norm(d):.4f}  shape={d.shape}")
        except Exception as e:
            print("    gguf读失败",e)
# safetensors
from safetensors import safe_open
for name,d in [("base_raw","/root/autodl-tmp/qwen25_base_raw"),
               ("antiheb_05b","/root/autodl-tmp/life1/antiheb_05b")]:
    fs = glob.glob(d+"/*.safetensors")
    if not fs:
        print(f"    {name}: 无 safetensors"); continue
    try:
        with safe_open(fs[0], framework="pt") as f:
            for k in f.keys():
                if 'layers.12.mlp.down_proj' in k:
                    t = f.get_tensor(k).float()
                    print(f"    {name:14s} {k}  norm={t.norm().item():.4f}  shape={tuple(t.shape)}")
    except Exception as e:
        print(f"    {name} ERR {str(e)[:70]}")
