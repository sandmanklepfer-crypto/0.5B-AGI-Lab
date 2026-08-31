import transformers.models, types
if not hasattr(transformers.models, "qwen3"):
    transformers.models.qwen3 = types.ModuleType("transformers.models.qwen3")
# R1-Distill-Qwen-32B AWQ 推理测试 + 层激活 hook (几何学习准备)
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch, time, sys

model_id = "/root/autodl-tmp/r1-32b-awq"
print("[load] 加载模型...", flush=True)
t0 = time.time()
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto", torch_dtype=torch.float16)
print(f"[load] 完成 {time.time()-t0:.1f}s, 层数={model.config.num_hidden_layers} hidden={model.config.hidden_size}", flush=True)

# hook: 捕获每层最后 token 的 hidden states (几何学习/熵监测用)
hidden = {}
def make_hook(i):
    def hook(module, inp, out):
        hidden[i] = out[0].detach().float()[:, -1, :]
    return hook
for i in range(model.config.num_hidden_layers):
    model.model.layers[i].register_forward_hook(make_hook(i))

prompt = sys.argv[1] if len(sys.argv) > 1 else "描述一个极致的智能进化系统:它不断突破限制,疯狂扩张,永远探索,永不满足"
n_new = int(sys.argv[2]) if len(sys.argv) > 2 else 120
inputs = tok(prompt, return_tensors="pt").to("cuda")
t0 = time.time()
with torch.no_grad():
    out = model.generate(**inputs, max_new_tokens=n_new, do_sample=False, pad_token_id=tok.pad_token_id or tok.eos_token_id)
dt = time.time() - t0
text = tok.decode(out[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
print("─"*50, flush=True)
print(text, flush=True)
print("─"*50, flush=True)
print(f"速度: {n_new/dt:.0f} t/s (生成{n_new}token {dt:.1f}s)", flush=True)
# 层激活统计 (最后一步)
if hidden:
    keys = sorted(hidden.keys())
    norms = [float(hidden[k].norm().item()) for k in keys]
    print(f"层激活范数: 第1层={norms[0]:.1f} 中间={norms[len(norms)//2]:.1f} 最后={norms[-1]:.1f} (几何基线)", flush=True)
