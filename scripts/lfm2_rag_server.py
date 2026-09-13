#!/usr/bin/env python3
"""lfm2_rag_server.py — LFM2-RAG 知识外挂常驻服务 (端口 8081)
POST {query} -> {answer, hits}
语料: /root/rag_data.jsonl 的 context 字段 (BM25 检索)
"""
import sys, json, re, math, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer
from flask import Flask, request, jsonify

RAG_DATA = "/root/rag_data.jsonl"
MODEL_DIR = "/root/lfm2-rag"

def tokenize(t):
    t = t.lower()
    return re.findall(r"[a-z0-9]+", t) + re.findall(r"[\u4e00-\u9fff]", t)

def build_index():
    docs = []
    for line in open(RAG_DATA, encoding="utf-8"):
        if not line.strip(): continue
        r = json.loads(line)
        docs.append({"title": r.get("title", ""), "text": r["context"]})
    N = len(docs)
    df, tf_list = {}, []
    for d in docs:
        toks = tokenize(d["text"])
        tf = {}
        for w in toks: tf[w] = tf.get(w, 0) + 1
        tf_list.append(tf)
        for w in set(toks): df[w] = df.get(w, 0) + 1
    idf = {w: math.log(1 + (N - n + 0.5) / (n + 0.5)) for w, n in df.items()}
    return docs, idf, tf_list

def bm25(query, idf, tf_list, docs, k=2):
    q = set(tokenize(query))
    scores = []
    for i, tf in enumerate(tf_list):
        dl = sum(tf.values())
        s = sum(idf[w] * tf[w] * 1.5 / (tf[w] + 1.5 * (1 - 0.75 + 0.75 * dl / 500))
                for w in q if w in tf and w in idf)
        if s > 0: scores.append((s, i))
    scores.sort(reverse=True)
    return [(docs[i]["title"], docs[i]["text"]) for _, i in scores[:k]]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8081)
    args = ap.parse_args()
    docs, idf, tf_list = build_index()
    print(f"[kb] {len(docs)} docs", flush=True)
    tok = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(MODEL_DIR, dtype=torch.bfloat16).to("cuda:0")
    model.eval()
    print("[lfm2-rag] loaded", flush=True)

    app = Flask(__name__)

    @app.route("/v1/rag", methods=["POST"])
    def rag():
        body = request.get_json(force=True)
        q = body.get("query", "")
        k = int(body.get("k", 2))
        hits = bm25(q, idf, tf_list, docs, k)
        if not hits:
            return jsonify({"answer": "知识库中没有找到相关内容。", "hits": []})
        ctx = "\n\n".join(f"[{t}]\n{d}" for t, d in hits)
        msgs = [{"role": "user", "content":
                 f"Use the following context to answer questions:\n{ctx}\n\nQuestion: {q}"}]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt").to("cuda:0")
        with torch.inference_mode():
            out = model.generate(**ids, max_new_tokens=180, do_sample=False,
                                 pad_token_id=tok.eos_token_id)
        ans = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        return jsonify({"answer": ans, "hits": [t for t, _ in hits]})

    app.run(host="0.0.0.0", port=args.port, threaded=True)

if __name__ == "__main__":
    main()
