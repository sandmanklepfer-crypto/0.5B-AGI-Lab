import sys, types, importlib.machinery as _m
def _mk(n,p=False):
    mm=types.ModuleType(n); mm.__version__="0.0.0"
    mm.__spec__=_m.ModuleSpec(n,None,is_package=p)
    if p: mm.__path__=[]
    return mm
fake=_mk("torchvision",True); tr=_mk("torchvision.transforms")
class IM: pass
tr.InterpolationMode=IM
for a in ["Compose","ToTensor","Normalize","Resize"]: setattr(tr,a,object)
fake.transforms=tr
sys.modules["torchvision"]=fake; sys.modules["torchvision.transforms"]=tr
print("--- 直接 import modeling_qwen2 ---", flush=True)
try:
    from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
    print("  OK", Qwen2ForCausalLM, flush=True)
except Exception as e:
    import traceback; print("  FAIL:", flush=True)
    traceback.print_exc()
print("--- 试 import transformers ---", flush=True)
try:
    import transformers
    print("  transformers", transformers.__version__, flush=True)
    print("  has Qwen2?", hasattr(transformers,"Qwen2ForCausalLM"), flush=True)
except Exception as e:
    print("  FAIL", str(e)[:120], flush=True)
print("DIAG2_DONE")
