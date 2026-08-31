import re
GGUF = "/root/autodl-tmp/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf"
for fn in ['/root/eval_all15_gguf.py', '/root/eval_ceval_gguf.py']:
    s = open(fn).read()
    old = 'torch_dtype=torch.bfloat16'
    new = 'torch_dtype=torch.float16, gguf_file="' + GGUF + '", low_cpu_mem_usage=True'
    assert old in s, f"NOT FOUND in {fn}"
    s = s.replace(old, new)
    open(fn, 'w').write(s)
    print("PATCHED", fn)
