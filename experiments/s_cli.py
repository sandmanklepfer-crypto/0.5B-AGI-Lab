import json, urllib.request, time
U="http://127.0.0.1:8081/v1/chat/completions"
QS=["计算：7乘以8等于多少？","解方程：3x=21，求x。","计算 2 的 10 次方。",
    "12加34等于多少？","计算：25乘以4等于多少？",
    "如果A大于B，B大于C，那么A和C谁大？"]
print("="*70); print("calc_v1 (计算蒸馏模型) 通过 server 测试"); print("="*70, flush=True)
for q in QS:
    body=json.dumps({"messages":[{"role":"user","content":q}],
                     "max_tokens":30,"temperature":0.2}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=60).read())
        a=r["choices"][0]["message"]["content"].strip().replace("\n"," ")
    except Exception as e:
        a=f"ERR {str(e)[:80]}"
    print(f"  Q: {q}\n     A: {a[:110]}", flush=True)
print("CLI_DONE")
