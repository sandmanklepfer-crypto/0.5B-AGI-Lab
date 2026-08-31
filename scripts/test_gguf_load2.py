import torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer
t0 = time.time()
try:
    tok = AutoTokenizer.from_pretrained("/root/r1-32b-hf", trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained("/root/r1-32b-hf", gguf_file="/root/autodl-tmp/r1-32b-gguf/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf", torch_dtype=torch.float16, low_cpu_mem_usage=True)
    print("GGUF_LOAD_OK", round(time.time()-t0,1), "s", m.config.num_hidden_layers, m.config.hidden_size, flush=True)
    m = m.cuda().eval()
    import torch.nn.functional as F
    ids = tok("苹果是一种常见的水果。", return_tensors="pt").to("cuda")
    with torch.inference_mode():
        h = m(**ids, output_hidden_states=True).hidden_states
    print("FWD_OK", len(h), tuple(h[0].shape), flush=True)
except Exception as e:
    import traceback; traceback.print_exc()
    print("GGUF_LOAD_FAIL", type(e).__name__, str(e)[:300], flush=True)
