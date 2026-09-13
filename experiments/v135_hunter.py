#!/usr/bin/env python3
# V135 捕猎者: 0.5B灵魂 猎 13B身体 的黎曼度量/曲率知识
# 循环: 13B给K个解释候选 → 0.5B逐个"吃"(消化成自己的话+追问) → 选追问最实的
#       → 下一轮问题=0.5B自己提出的追问 → 再猎 (问题由它产生=真捕猎)
import sys, types, torch, numpy as np, re
INF = "/root/autodl-tmp/rwkv7_13b/inference"
sys.path.insert(0, INF)
if "_rwkv7_release_inference" not in sys.modules:
    pkg = types.ModuleType("_rwkv7_release_inference"); pkg.__path__ = [INF]
    sys.modules["_rwkv7_release_inference"] = pkg
from _rwkv7_release_inference.model_loader import load_model_and_tokenizer
from transformers import AutoModelForCausalLM, AutoTokenizer

K = 3
ROUNDS = 6
GOAL = "黎曼度量与微分几何的曲率"

def main():
    print('[V135] 加载 13B(猎物) + 0.5B(猎人) ...', flush=True)
    body, tok13 = load_model_and_tokenizer(
        "/root/autodl-tmp/rwkv7_13b", device="cuda", dtype=torch.bfloat16,
        backend="torch", state_dtype="float32")
    tok05 = AutoTokenizer.from_pretrained("/root/autodl-tmp/qwen25_base_raw")
    hunter = AutoModelForCausalLM.from_pretrained("/root/autodl-tmp/qwen25_base_raw",
                                                  torch_dtype=torch.float16).to('cuda').eval()
    print('[V135] 加载OK | 目标: %s' % GOAL, flush=True)

    def prey_answer(q, seed):
        torch.manual_seed(seed)
        prompt = f"User: {q}\n\nAssistant: 让我用直白的方式解释："
        ids = tok13(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            out = body.generate(input_ids=ids, max_new_tokens=120, do_sample=True,
                                temperature=0.9, top_p=0.92, pad_token_id=0)
        return tok13.decode(out[0][ids.shape[1]:], skip_special_tokens=True).strip()

    def hunter_digest(cand, history):
        """0.5B 吃一口: 用自己的话理解 + 提出还不懂的追问"""
        prompt = ('我一直在琢磨"%s"。\n我看到一段解释:\n%s\n'
                  '用我自己的话说，我现在理解到的是：' % (GOAL, cand[:400]))
        ids = tok05(prompt, return_tensors='pt').input_ids.to('cuda')
        with torch.no_grad():
            o = hunter.generate(ids, max_new_tokens=70, do_sample=True,
                                temperature=0.85, top_p=0.9,
                                repetition_penalty=1.15, pad_token_id=tok05.eos_token_id)
        return tok05.decode(o[0][ids.shape[1]:], skip_special_tokens=True).strip()

    def extract_question(digest):
        """从0.5B消化文本里找追问(带?或还想知道/不明白/那么...)"""
        seg = digest[-90:]
        m = re.findall(r'[^。\n]{4,40}[?？]', seg)
        if m: return m[-1]
        for kw in ['还想', '不知道', '不明白', '那么', '为什么', '怎么']:
            idx = seg.rfind(kw)
            if idx >= 0:
                return seg[idx:idx+60].strip('。 \n')
        return ''

    q = ('什么是黎曼度量？微分几何里的曲率是什么？请从最基础的直觉讲起，'
         '不要用太多公式，先讲清楚它解决什么问题。')
    line = ''
    print('\n=== 捕猎开始 ===', flush=True)
    for r in range(ROUNDS):
        # 1. 猎物给出K个角度
        cands = []
        for k in range(K):
            try:
                cands.append(prey_answer(q, 500 + r * 10 + k))
            except Exception as e:
                cands.append('')
        cands = [c for c in cands if len(c) > 20]
        if not cands:
            print('  轮%d: 猎物无有效回答, 停' % (r+1), flush=True); break
        # 2. 猎人逐个消化
        digests = []
        for c in cands[:2]:
            try:
                dig = hunter_digest(c, line)
                digests.append(dig)
            except Exception:
                digests.append('')
        # 3. 选消化最实(最长且含"我")的
        best = 0
        if len(digests) > 1:
            scores = [len(d) + (20 if '我' in d else 0) for d in digests]
            best = int(np.argmax(scores))
        picked = digests[best] if digests else ''
        line += picked + '\n'
        # 4. 猎人提出下一问
        nq = extract_question(picked)
        print('  轮%d 吃了候选%d' % (r+1, best), flush=True)
        print('    消化: %s' % picked[:100].replace('\n',' '), flush=True)
        if nq:
            q = nq
            print('    追问: %s' % nq[:60], flush=True)
        else:
            # 猎不到追问 → 换角度重猎
            q = ('关于%s，换一个完全不同的角度再讲，最好打个比方。' % GOAL)
    print('\n=== 捕猎总结 ===', flush=True)
    print('猎人消化链(它"学到"的叙述):', flush=True)
    print(line[:1200], flush=True)
    print('\n[done]', flush=True)

if __name__ == '__main__':
    main()
