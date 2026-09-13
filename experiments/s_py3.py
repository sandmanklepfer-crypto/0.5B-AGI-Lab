import sys, time
print("=== 尝试 llama-cpp-python ===", flush=True)
try:
    from llama_cpp import Llama
    print("  llama_cpp 可用", flush=True)
    M="/root/autodl-tmp/calc_v1.gguf"
    llm=Llama(model_path=M, n_ctx=512, n_gpu_layers=99, verbose=False)
    print("  模型加载OK", flush=True)
    QS=["计算：7乘以8等于多少？","解方程：3x=21，求x。","计算 2 的 10 次方。",
        "12加34等于多少？","计算：25乘以4等于多少？",
        "如果A大于B，B大于C，那么A和C谁大？"]
    for q in QS:
        try:
            r=llm.create_chat_completion(messages=[{"role":"user","content":q}],
                                         max_tokens=30, temperature=0.2)
            a=r["choices"][0]["message"]["content"].strip().replace("\n"," ")
        except Exception as e:
            r=llm(q, max_tokens=30, temperature=0.2)
            a=r["choices"][0]["text"].strip().replace("\n"," ")
        print(f"  Q: {q}\n     A: {a[:110]}", flush=True)
except ImportError:
    print("  ❌ 未安装 llama-cpp-python", flush=True)
except Exception as e:
    print(f"  ❌ {str(e)[:150]}", flush=True)
print("DONE")
