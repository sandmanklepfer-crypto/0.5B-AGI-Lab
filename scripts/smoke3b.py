import torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
t0 = time.time()
tok = AutoTokenizer.from_pretrained("/root/qwen3b-hf", trust_remote_code=True)
m = AutoModelForCausalLM.from_pretrained("/root/qwen3b-hf", gguf_file="/root/autodl-tmp/models/qwen2.5-coder-3b-instruct-q4_k_m.gguf", torch_dtype=torch.float16, low_cpu_mem_usage=True)
print("LOAD_OK", round(time.time()-t0,1), "s", m.config.num_hidden_layers, m.config.hidden_size, flush=True)
m = m.cuda().eval()
for q in ["7 × 8 等于多少?", "2 的 10 次方等于多少?", "解方程3x+5=20，求x。"]:
    ids = tok(q, return_tensors="pt").to("cuda")
    out = m.generate(**ids, max_new_tokens=60, do_sample=False, pad_token_id=tok.eos_token_id)
    print("Q:", q)
    print("A:", tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)[:150])
    print("---")
print("SMOKE3B_OK")
