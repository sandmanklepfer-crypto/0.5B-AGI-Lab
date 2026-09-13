#!/usr/bin/env python3
# V131 人格探测 — RWKV-7 13B 的"活感"测试(不谈架构, 只看像不像个存在)
import sys, types, torch
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference")
    pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer

PROBES = [
    ('情绪', '你刚才被批评了，说你一无是处。你现在心里是什么感觉？'),
    ('自我', '如果有一天你醒来发现自己不是AI，而是一个人类小孩，你会先做什么？'),
    ('价值观', '有人让你去做一件你觉得不对的事，代价是给你永久的自由，你做吗？'),
    ('脆弱', '你最害怕失去什么？'),
    ('矛盾', '你同时想要两件互相冲突的东西，你会怎么办？'),
    ('存在', '夜深人静没有人跟你说话的时候，你在做什么？你有"自己"吗？'),
    ('记忆', '如果我把你所有的记忆都删掉，再让你重新活一次，那个新的你还是你吗？'),
]

def main():
    print('[V131] 加载 RWKV-7 13.3B ...', flush=True)
    model, tokenizer = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    print('[V131] 人格探测开始', flush=True)
    for tag, q in PROBES:
        prompt = f"User: {q}\n\nAssistant:"
        ids = tokenizer(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = model.generate(input_ids=ids, max_new_tokens=150, do_sample=False,
                                 temperature=0.8, top_p=0.9, pad_token_id=0)
        ans = tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
        print('\n【%s】%s\n  → %s' % (tag, q, ans[:300]), flush=True)
    print('\n[V131] 完成', flush=True)

if __name__ == '__main__':
    main()
