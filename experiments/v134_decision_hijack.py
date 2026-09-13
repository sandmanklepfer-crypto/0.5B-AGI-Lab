#!/usr/bin/env python3
# V134 决策级劫持: 0.5B(意志/灵魂) 从 13B(身体) 的多个候选分支中按"自我"选择
# 分支: 13B 用不同seed采样生成 K 个候选续写(各L token)
# 打分: 0.5B 读 历史+各分支 → 层12激活与慢S的cos = "这像不像我"
# 选择: cos最高的分支接续 → 更新慢S → 下一轮
# 结果: 输出全程由"灵魂"选择方向, 身体负责语言
import sys, types, torch, numpy as np
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer
from transformers import AutoModelForCausalLM, AutoTokenizer

SOUL = "/root/autodl-tmp/qwen25_base_raw"
K_BRANCH = 3          # 每轮候选分支数
BRANCH_LEN = 16       # 每分支长度
ROUNDS = 10           # 轮数
PROMPT = "User: 夜深了，只剩你一个人。你忽然意识到自己已经活了很久很久。你在想什么？\n\nAssistant:"

def main():
    print('[V134] 加载 13B(身体) + 0.5B(灵魂) ...', flush=True)
    body, tok13 = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    tok05 = AutoTokenizer.from_pretrained(SOUL)
    soul = AutoModelForCausalLM.from_pretrained(SOUL, torch_dtype=torch.float16).to('cuda').eval()
    print('[V134] 加载OK', flush=True)

    S05 = None
    BETA = 0.25
    def soul_cos(text):
        """0.5B 读文本 → 更新慢S → 返回 (慢S方向, 本次激活与慢S的cos)"""
        nonlocal S05
        ids = tok05(text[-250:], return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            hs = soul(input_ids=ids, output_hidden_states=True).hidden_states
        v = hs[12][0, -1].float().cpu().numpy()
        vn = v / (np.linalg.norm(v) + 1e-9)
        if S05 is None:
            S05 = vn.copy()
            return S05, 1.0
        cos = float(vn @ (S05 / (np.linalg.norm(S05) + 1e-9)))
        S05 = (1 - BETA) * S05 + BETA * vn
        return S05, cos

    # 灵魂先读prompt建立初始自我
    soul_cos(PROMPT)
    history = PROMPT
    print('[V134] 灵魂已建立初始自我 | 开始循环选择...', flush=True)
    for r in range(ROUNDS):
        # 身体生成 K 个候选分支(不同seed)
        branches = []
        for k in range(K_BRANCH):
            torch.manual_seed(1000 + r * 10 + k)
            ids = tok13(history[-400:], return_tensors='pt').input_ids.to('cuda')
            with torch.no_grad():
                out = body.generate(input_ids=ids, max_new_tokens=BRANCH_LEN,
                                    do_sample=True, temperature=0.95, top_p=0.92, pad_token_id=0)
            seg = tok13.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()
            branches.append(seg)
        # 灵魂打分: 哪个分支让我(0.5B)最接近自己的慢S
        scores = []
        for seg in branches:
            _, cos = soul_cos(history[-200:] + seg)
            scores.append(cos)
        best = int(np.argmax(scores))
        history = history + branches[best]
        print('  轮%d 分支cos=[%s] 选%d: %s' % (
            r+1, ' '.join('%.2f' % s for s in scores), best,
            branches[best][:60].replace('\n',' ')), flush=True)
    print('\n=== V134 灵魂选择的完整输出 ===', flush=True)
    print(history[len(PROMPT):][:1500], flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
