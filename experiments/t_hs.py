import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
MDIR="/root/autodl-tmp/life1/antiheb_05b"
tok=AutoTokenizer.from_pretrained(MDIR)
m=AutoModelForCausalLM.from_pretrained(MDIR, torch_dtype=torch.bfloat16).to("cuda").eval()
ids=tok("你好", return_tensors="pt").input_ids.to("cuda")
out=m(input_ids=ids, output_hidden_states=True, use_cache=False)
print("hidden_states:", len(out.hidden_states) if out.hidden_states else "None")
print("hs20:", out.hidden_states[20].shape)
