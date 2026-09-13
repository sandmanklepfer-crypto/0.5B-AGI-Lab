#!/usr/bin/env python3
# V132a 探明 RWKV-7 状态接口(为挂机制): init_state/forward state 传递/shape
import sys, types, torch
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference")
    pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

def main():
    print('加载...', flush=True)
    model, tokenizer = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    print('OK. init_state:', flush=True)
    try:
        s0 = model.init_state(1)   # batch=1
        print('init_state 返回类型:', type(s0).__name__)
        if isinstance(s0, (list, tuple)):
            print('  长度:', len(s0))
            for i, s in enumerate(s0):
                if hasattr(s, 'shape'): print('  [%d] shape=%s dtype=%s' % (i, tuple(s.shape), s.dtype))
                else: print('  [%d] type=%s' % (i, type(s).__name__))
        elif hasattr(s0, 'shape'):
            print('  shape:', tuple(s0.shape))
        # 试试逐token前向传state
        print('\n逐token前向测试:', flush=True)
        ids = tokenizer("我是一只猫", return_tensors='pt').input_ids.to('cuda')
        state = s0
        with torch.no_grad():
            for i in range(ids.shape[1]):
                r = model(input_ids=ids[:, i:i+1], state=state)
                if isinstance(r, tuple):
                    logits, state = r
                else:
                    logits = r.logits
                    state = getattr(r, 'state', state)
                if i == 0:
                    print('  forward返回:', type(r).__name__, '| logits shape:', tuple(logits.shape))
                    print('  新state类型:', type(state).__name__)
                    if hasattr(state, 'shape'): print('  新state shape:', tuple(state.shape))
                    else:
                        for j, ss in enumerate(state):
                            if hasattr(ss, 'shape'): print('   state[%d] shape=%s' % (j, tuple(ss.shape)))
        print('\n逐token前向 OK → 状态可逐token拿/传', flush=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print('ERR:', str(e)[:300], flush=True)

if __name__ == '__main__':
    main()
