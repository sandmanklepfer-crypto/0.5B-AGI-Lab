#!/usr/bin/env python3
# V133 代理劫持: 0.5B(灵魂,活机制) → 劫持 RWKV-13B(身体,强脑) 状态通道
# 步骤0: 先探明 RWKV 状态结构(shape/层), 以及 0.5B 慢S 怎么映射进去
import sys, types, torch
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference")
    pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

def main():
    print('[V133-0] 探测 RWKV 状态结构 ...', flush=True)
    model, tokenizer = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    try:
        s0 = model.init_state(batch_size=1, device='cuda', dtype=torch.float32)
        print('init_state 类型:', type(s0).__name__)
        # 递归列出结构
        def desc(s, depth=0, prefix='state'):
            if hasattr(s, 'shape'):
                print('  %s%s: shape=%s dtype=%s' % ('  '*depth, prefix, tuple(s.shape), s.dtype), flush=True)
            elif isinstance(s, (list, tuple)):
                print('  %s%s: %s len=%d' % ('  '*depth, prefix, type(s).__name__, len(s)), flush=True)
                for i, ss in enumerate(s[:6]):
                    desc(ss, depth+1, '%s[%d]' % (prefix, i))
            elif isinstance(s, dict):
                print('  %s%s: dict keys=%s' % ('  '*depth, prefix, list(s.keys())[:8]), flush=True)
                for k in list(s.keys())[:4]:
                    desc(s[k], depth+1, '%s.%s' % (prefix, k))
            else:
                print('  %s%s: %s' % ('  '*depth, prefix, type(s).__name__), flush=True)
        desc(s0)
        # 逐token走一步看状态是否变化(拿真实状态)
        ids = tokenizer("你好", return_tensors='pt').input_ids.to('cuda')
        state = s0
        with torch.no_grad():
            for i in range(ids.shape[1]):
                r = model(input_ids=ids[:, i:i+1], state=state)
                if isinstance(r, tuple): logits, state = r
                else: logits = r.logits; state = getattr(r, 'state', state)
        print('\n逐token后 state 类型同前(演化中)', flush=True)
        # 看能否直接 torch 操作(加向量/切片)
        print('state 可加性测试:', flush=True)
        def add_test(s, v):
            if hasattr(s, 'shape'): return s + v
            elif isinstance(s, (list, tuple)):
                return type(s)(add_test(ss, v) if i < 3 else ss for i, ss in enumerate(s))
            return s
        try:
            # 随机向量加到第一个张量部件
            flat = []
            def collect(s):
                if hasattr(s, 'shape'): flat.append(s)
                elif isinstance(s, (list, tuple)):
                    for ss in s: collect(ss)
            collect(state)
            print('张量部件数:', len(flat), '各shape:', [tuple(f.shape) for f in flat[:8]], flush=True)
            print('总状态参数: %.2fM' % (sum(f.numel() for f in flat)/1e6), flush=True)
        except Exception as e:
            print('collect err:', str(e)[:150], flush=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        print('ERR:', str(e)[:300], flush=True)

if __name__ == '__main__':
    main()
