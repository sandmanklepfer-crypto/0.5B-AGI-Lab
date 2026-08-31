import sys, time, os, types
os.environ.setdefault("COMFYUI_ROOT", "/workspace/ComfyUI")
sys.path.insert(0, "/workspace/ComfyUI")
# 强制 CPU 模式 (模拟 --cpu)
from comfy.cli_args import args
args.cpu = True
# 模拟包以支持相对导入
pkg = types.ModuleType("wvw")
pkg.__path__ = ["/workspace/ComfyUI/custom_nodes/ComfyUI-WanVideoWrapper"]
sys.modules["wvw"] = pkg
import torch

t0 = time.time()
print(f"[{time.strftime('%H:%M:%S')}] 开始加载 GGUF T5...", flush=True)
from wvw.nodes_model_loading import LoadWanVideoT5TextEncoder
node = LoadWanVideoT5TextEncoder()
enc, = node.loadmodel("umt5-xxl-encoder-Q3_K_M.gguf", "bf16", load_device="offload_device")
print(f"[{time.strftime('%H:%M:%S')}] 加载完成, 耗时 {time.time()-t0:.0f}s, 模型类型: {type(enc['model']).__name__}", flush=True)

# 统计替换后的层
n_linear = sum(1 for m in enc["model"].model.modules() if type(m).__name__ == "CustomLinear")
print(f"CustomLinear 层数: {n_linear}", flush=True)

print(f"[{time.strftime('%H:%M:%S')}] 填充权重 (模拟 WanVideoTextEncode 流程)...", flush=True)
from accelerate.utils import set_module_tensor_to_device
from wvw.gguf.gguf_utils import GGUFParameter as _GGUFParameter
model_state_dict = enc["model"].state_dict
params_list = list(enc["model"].model.named_parameters())
t2 = time.time()
for name, param in params_list:
    value = model_state_dict[name]
    if isinstance(value, _GGUFParameter):
        new_param = _GGUFParameter(value.data.to(torch.device("cpu"), non_blocking=True),
                                   requires_grad=False, quant_type=value.quant_type)
        parts = name.split(".")
        mod = enc["model"].model
        for p in parts[:-1]:
            mod = getattr(mod, p)
        setattr(mod, parts[-1], new_param)
    else:
        set_module_tensor_to_device(enc["model"].model, name, device=torch.device("cpu"), value=value)
print(f"[{time.strftime('%H:%M:%S')}] 填充完成, 耗时 {time.time()-t2:.0f}s, 参数数: {len(params_list)}", flush=True)

print(f"[{time.strftime('%H:%M:%S')}] 测试编码...", flush=True)
t1 = time.time()
out = enc["model"](["a red fox running in the snow"], torch.device("cpu"))
print(f"[{time.strftime('%H:%M:%S')}] 编码完成, 耗时 {time.time()-t1:.0f}s, 输出: {[tuple(o.shape) for o in out]}", flush=True)
# 数值验证
v = out[0]
print(f"输出数值: mean={v.mean().item():.4f}, std={v.std().item():.4f}, min={v.min().item():.4f}, max={v.max().item():.4f}, nan={torch.isnan(v).any().item()}", flush=True)
emb = getattr(enc["model"].model.token_embedding, "data", None) or enc["model"].model.token_embedding.weight
print(f"token_embd: shape={tuple(emb.shape)}, mean={emb.float().mean().item():.4f}, std={emb.float().std().item():.4f}", flush=True)
w0 = next(iter(enc["model"].model.blocks[0].attn.q.parameters()))
w0d = getattr(w0, "data", w0)
print(f"attn.q weight: mean={w0d.float().mean().item():.4f}, std={w0d.float().std().item():.4f}", flush=True)
print("SUCCESS", flush=True)
