#!/usr/bin/env python3
"""antirep_py.py — 生成时重复抑制 (antirepeller 推理侧): 熵下降即推离
包装已训好的模型 (assert_v1), 生成时检测重复 -> 强制换 token
用法: antirep_py.py [--model DIR] [--prompts ...]
"""
import sys, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer

def gen_antirep(model, tok, prompt, max_new=50, rep_window=4, rep_thresh=3):
    """生成时抑制重复: 最近 rep_window 个 token 重复 >= rep_thresh 次 -> 选次优 token"""
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    generated = ids["input_ids"][0].tolist()
    for _ in range(max_new):
        with torch.inference_mode():
            logits = model(torch.tensor([generated], device="cuda:0")).logits[0, -1]
        # 检测近期重复
        recent = generated[-rep_window:]
        rep_count = {}
        for t in recent:
            rep_count[t] = rep_count.get(t, 0) + 1
        bad = {t for t, c in rep_count.items() if c >= rep_thresh}
        if bad:
            # 压制重复 token, 选次优 (clone 后修改)
            logits = logits.clone()
            logits[list(bad)] = -1e9
        with torch.inference_mode():
            nxt = torch.argmax(logits).item()
        if nxt == tok.eos_token_id:
            break
        generated.append(nxt)
    return tok.decode(generated[ids["input_ids"].shape[1]:], skip_special_tokens=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="/root/assert_v1")
    ap.add_argument("--prompts", nargs="*", default=[
        "候选答案 计算结果是 62。 提取断言",
        "候选答案 解得 x=8。 提取断言",
        "候选答案 7的3次方等于 344。 提取断言",
        "候选答案 函数返回 12。 提取断言",
        "候选答案 水的沸点是100度。 提取断言",
    ])
    args = ap.parse_args()
    tok = AutoTokenizer.from_pretrained(args.model); tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to("cuda:0")
    model.eval()
    print(f"=== antirepeller 抑制测试 (model={args.model}) ===", flush=True)
    for p in args.prompts:
        a = gen_antirep(model, tok, p)
        print(f"  输入: {p}\n  提取: {a[:70]!r}", flush=True)

if __name__ == "__main__":
    main()
