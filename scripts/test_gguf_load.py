import torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
t0 = time.time()
try:
    tok = AutoTokenizer.from_pretrained("/root/autodl-tmp/r1-32b-gguf", trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained("/root/autodl-tmp/r1-32b-gguf", gguf_file="DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf", torch_dtype=torch.float16, low_cpu_mem_usage=True)
    print("GGUF_LOAD_OK", round(time.time()-t0,1), "s", m.config.num_hidden_layers, m.config.hidden_size)
except Exception as e:
    print("GGUF_LOAD_FAIL", type(e).__name__, str(e)[:200])
