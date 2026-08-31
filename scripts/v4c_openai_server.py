#!/usr/bin/env python3
"""v4c_openai_server.py — 把 v4c 包装成 OpenAI 兼容 API (llama-server 替代品)
smolagents OpenAIServerModel 直接连 http://127.0.0.1:8080/v1
用法: v4c_openai_server.py [--model /root/distill_v4c] [--port 8080] [--max-tokens 400]
"""
import sys, json, time, argparse
import torch
sys.path.insert(0, "/root/venv_lfm2/lib/python3.12/site-packages")
from transformers import AutoModelForCausalLM, AutoTokenizer
from flask import Flask, request, jsonify

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="/root/distill_v4c")
ap.add_argument("--port", type=int, default=8080)
ap.add_argument("--max-tokens", type=int, default=400)
ap.add_argument("--ctx", type=int, default=2048)
args = ap.parse_args()

print("[load]", args.model, flush=True)
tok = AutoTokenizer.from_pretrained(args.model)
tok.pad_token = tok.eos_token
model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16).to("cuda:0")
model.eval()
print("[loaded]", flush=True)

app = Flask(__name__)

def chat(prompt: str, max_new: int) -> str:
    ids = tok(prompt, return_tensors="pt").to("cuda:0")
    with torch.inference_mode():
        out = model.generate(**ids, max_new_tokens=max_new, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()

@app.route("/v1/models", methods=["GET"])
def models():
    return jsonify({"object": "list", "data": [{"id": "v4c", "object": "model"}]})

@app.route("/v1/chat/completions", methods=["POST"])
def completions():
    body = request.get_json(force=True)
    msgs = body.get("messages", [])
    max_new = min(body.get("max_tokens", args.max_tokens), 800)
    # 拼 prompt: 系统 + 用户消息 (v4c 无 chat 模板训练, 用简单拼接)
    prompt = ""
    for m in msgs:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            prompt += f"系统指令：{content}\n"
        elif role == "user":
            prompt += f"用户：{content}\n"
        elif role == "assistant":
            prompt += f"助手：{content}\n"
    prompt += "助手："
    t0 = time.time()
    try:
        ans = chat(prompt, max_new)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({
        "id": "chatcmpl-v4c",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "v4c",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": ans},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": len(msgs), "completion_tokens": len(ans), "total_tokens": len(msgs) + len(ans)},
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=args.port, threaded=True)
