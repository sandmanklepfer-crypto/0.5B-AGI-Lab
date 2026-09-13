import traceback, sys
print("1) import transformers", flush=True)
import transformers; print("   ", transformers.__version__, flush=True)
print("2) 直接 import qwen2 子模块", flush=True)
try:
    import transformers.models.qwen2.modeling_qwen2 as m
    print("   OK", hasattr(m,"Qwen2ForCausalLM"), flush=True)
except Exception:
    traceback.print_exc()
print("3) 试 from_pretrained", flush=True)
try:
    from transformers import AutoModelForCausalLM
    md=AutoModelForCausalLM.from_pretrained("/root/distill_calc_v1", dtype="float32")
    print("   OK 层数", len(md.model.layers), flush=True)
except Exception:
    traceback.print_exc()
print("D3_DONE")
