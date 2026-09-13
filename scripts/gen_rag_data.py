#!/usr/bin/env python3
"""RAG 蒸馏数据生成器: context + query -> LFM2-RAG grounded answer
输出 JSONL: {context, query, answer, qid, variants:[...]}
用法: gen_rag_data.py [--out /root/rag_data.jsonl] [--max-q 100] [--aug 2]
"""
import sys, os, json, random, re
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")

# 同义对 (与 distill_sym_train.py 一致, G_sem 生成元)
SYN_PAIRS = [
    ('高兴', '开心'), ('美丽', '漂亮'), ('重要', '关键'), ('快速', '迅速'),
    ('使用', '利用'), ('帮助', '协助'), ('思考', '考虑'), ('问题', '疑问'),
    ('方法', '方式'), ('原因', '缘故'), ('结果', '成果'), ('需要', '需求'),
    ('可以', '能够'), ('应该', '应当'), ('非常', '十分'), ('主要', '首要'),
    ('简单', '容易'), ('影响', '作用'), ('提高', '提升'), ('降低', '减少'),
    ('增加', '增多'), ('改变', '变化'), ('解决', '处理'), ('发现', '找到'),
    ('提供', '给予'), ('表示', '表明'), ('认为', '觉得'), ('希望', '期望'),
    ('开始', '着手'), ('理解', '明白'), ('解释', '说明'), ('回答', '答复'),
    ('可能', '或许'), ('必须', '务必'), ('普通', '平常'), ('立即', '马上'),
]

def synonymize(text: str, n: int) -> list[str]:
    """生成 n 个语义不变变体 (随机替换同义词)"""
    out = []
    for _ in range(n):
        t = text
        for a, b in random.sample(SYN_PAIRS, k=min(3, len(SYN_PAIRS))):
            if a in t:
                t = t.replace(a, b)
        if t != text:
            out.append(t)
    return out

def load_docs():
    """从 context_prompts.py 提取 DOCS (服务器已有)"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("cp", "/root/autodl-tmp/context_prompts.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.DOCS

def build_prompt(doc: str, q: str, zh=True) -> str:
    if zh:
        return f"请阅读下面的文档，然后回答问题。\n\n文档：{doc}\n\n问题：{q}"
    return f"Use the following context to answer questions:\n{doc}\n\nQuestion: {q}"

def gen(model, tok, doc, q, max_new=160):
    msgs = [{"role": "user", "content": build_prompt(doc, q)}]
    text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt").to("cuda:0")
    out = model.generate(**ids, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

def main():
    import argparse, torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/root/rag_data.jsonl")
    ap.add_argument("--aug", type=int, default=2)
    ap.add_argument("--selfq", type=int, default=2, help="每文档自问数")
    args = ap.parse_args()
    random.seed(42)

    tok = AutoTokenizer.from_pretrained("/root/lfm2-rag")
    model = AutoModelForCausalLM.from_pretrained("/root/lfm2-rag", dtype=torch.bfloat16, device_map="cuda:0")
    model.eval()
    print("[model] loaded", file=sys.stderr, flush=True)

    docs = load_docs()
    print(f"[docs] {len(docs)}", file=sys.stderr)
    rows = []
    qid = 0
    for title, doc, qs in docs:
        tasks = [(q, "fact") for q in qs]
        tasks.append(("请用三句话总结文档的主要内容。", "sum"))
        tasks.append(("文档中的信息支持还是反对'技术进步总会带来更好的结果'？请结合文档论证。", "arg"))
        # 自问扩展: 让模型自己出题再答 (RAG grounding)
        for _ in range(args.selfq):
            a1 = gen(model, tok, doc, "根据文档内容提出一个文档能回答的问题，只输出问题。")
            if 5 < len(a1) < 80 and "?" in a1 + "？":
                tasks.append((a1, "self"))
        for q, qtype in tasks:
            try:
                ans = gen(model, tok, doc, q)
                if len(ans) < 5:
                    continue
                rows.append({"qid": qid, "title": title, "type": qtype,
                             "context": doc, "query": q, "answer": ans,
                             "variants": synonymize(q, args.aug)})
                qid += 1
                print(f"  [{qid}] {qtype} q={q[:28]}... ans={ans[:24]}...", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"  [fail] {e}", file=sys.stderr, flush=True)

    with open(args.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[done] {len(rows)} rows -> {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
