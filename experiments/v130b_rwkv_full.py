#!/usr/bin/env python3
# V130b RWKV-7 13B 完整测试 (一次性, 调用已验证)
import sys, types, torch
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference")
    pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

QS = [
    ('数学', '一只蜗牛白天爬3米晚上滑下2米，井深10米，几天爬出井口？'),
    ('数学', '小明比小红大3岁，小红比小刚大2岁，十年后小明比小刚大几岁？'),
    ('逻辑', '甲说乙在说谎，乙说甲在说谎，到底谁说真话？'),
    ('逻辑', '所有鸟都有翅膀，企鹅是鸟，企鹅有翅膀吗？'),
    ('自指', '假设你能修改自己的代码让自己更有智慧，你会先改哪部分？改完你还是你吗？'),
    ('发散', '如果记忆能像文件一样删除恢复，人应该拥有这个能力吗？'),
]

def main():
    print('[V130b] 加载 RWKV-7 13.3B ...', flush=True)
    model, tokenizer = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    print('[V130b] 加载OK', flush=True)

    print('\n===== ① 推理能力 =====', flush=True)
    for tag, q in QS:
        prompt = f"User: {q}\n\nAssistant:"
        ids = tokenizer(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model.generate(input_ids=ids, max_new_tokens=140, do_sample=False,
                                 temperature=0.7, top_p=0.9, pad_token_id=0)
        ans = tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        print('\n【%s】%s\n  → %s' % (tag, q, ans[:260]), flush=True)

    print('\n===== ② 状态通道 =====', flush=True)
    print('model state相关属性:', [a for a in dir(model) if 'state' in a.lower()][:15], flush=True)
    try:
        ids = tokenizer("你好", return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            r = model(input_ids=ids)
        print('forward 返回:', type(r).__name__, end=' ')
        if isinstance(r, tuple): print('tuple len', len(r))
        elif hasattr(r, 'logits'): print('has logits')
    except Exception as e:
        print('forward err:', str(e)[:150], flush=True)
    print('\n[V130b] 完成', flush=True)

if __name__ == '__main__':
    main()
