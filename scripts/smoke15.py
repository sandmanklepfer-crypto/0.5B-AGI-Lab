import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
tok = AutoTokenizer.from_pretrained("/root/qwen15b", trust_remote_code=True)
m = AutoModelForCausalLM.from_pretrained("/root/qwen15b", trust_remote_code=True, torch_dtype=torch.bfloat16).cuda().eval()
for q in ["7 × 8 等于多少?", "2 的 10 次方等于多少?"]:
    inp = tok(q, return_tensors="pt").to("cuda")
    out = m.generate(**inp, max_new_tokens=60, do_sample=False)
    print("Q:", q)
    print("A:", tok.decode(out[0][inp["input_ids"].shape[1]:], skip_special_tokens=True))
    print("---")
print("SMOKE_OK")
