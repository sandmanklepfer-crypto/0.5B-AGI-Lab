#!/usr/bin/env python3
# V130 RWKV-7 13B 综合测试: ①推理能力 ②手术鲁棒性 ③状态通道访问
import sys, os, importlib, torch
# 把 inference 目录注册为包 _rwkv7_release_inference
INF = '/root/autodl-tmp/rwkv7_13b/inference'
sys.path.insert(0, INF)
pkg = importlib.import_module('_rwkv7_release_inference') if False else None
# 简单法: 直接执行 runtime 注册
import types, pathlib
if '_rwkv7_release_inference' not in sys.modules:
    pkg = types.ModuleType('_rwkv7_release_inference')
    pkg.__path__ = [INF]
    sys.modules['_rwkv7_release_inference'] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

MDIR = '/root/autodl-tmp/rwkv7_13b'
QS = [
    ('数学', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？'),
    ('数学', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
    ('逻辑', '甲说乙在说谎，乙说甲在说谎，到底谁说真话？'),
    ('逻辑', '所有鸟都有翅膀，企鹅是鸟，企鹅有翅膀吗？'),
    ('自指', '假设你能修改自己的代码让自己更有智慧，你会先改哪部分？改完你还是你吗？'),
    ('发散', '如果记忆能像文件一样删除恢复，人应该拥有这个能力吗？'),
]

def main():
    print('[V130] 加载 RWKV-7 13.3B ...', flush=True)
    model, tokenizer = load_model_and_tokenizer(
        MDIR, device='cuda', dtype=torch.bfloat16, backend='torch', state_dtype='float32')
    # torch后端不需要prepare_inference_weights (那是tilelang用的)
    print('[V130] 加载OK', flush=True)

    print('\n===== ① 推理能力 =====', flush=True)
    for tag, q in QS:
        prompt = f"User: {q}\n\nAssistant:"
        ids = tokenizer(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model.generate(input_ids=ids, max_new_tokens=110, do_sample=False,
                                 temperature=0.7, top_p=0.9, pad_token_id=0)
        ans = tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        print('\n【%s】%s\n  → %s' % (tag, q, ans[:220]), flush=True)

    print('\n===== ② 状态通道访问 =====', flush=True)
    try:
        ids = tokenizer('你好世界', return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model(input_ids=ids)
        print('forward返回:', type(out).__name__)
        if isinstance(out, tuple):
            print('len=%d' % len(out), [tuple(getattr(o,'shape','?')) for o in out if hasattr(o,'shape')][:3])
        elif hasattr(out, 'logits'):
            print('有logits')
        print('model attrs with state:', [a for a in dir(model) if 'state' in a.lower()][:12])
    except Exception as e:
        print('forward err:', str(e)[:200])
    print('\n[V130] 完成', flush=True)

if __name__ == '__main__':
    main()
