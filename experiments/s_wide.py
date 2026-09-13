import json, urllib.request
def ask(port,q,mx=70):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":0.25}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=90).read())["choices"][0]["message"]["content"].strip().replace("\n"," ")[:105]
    except Exception as e: return f"ERR {str(e)[:30]}"
QS=["计算：347乘以28等于多少？","求导：sin(x) 对 x。","解方程：5x=45，求x。",
    "黎曼曲率张量 R_abcd 对 a,b 是什么对称性？","什么是人工智能？","介绍一下你自己。"]
print("="*90); print("neg150 全面测试 (8081=原版, 8091=neg150)"); print("="*90, flush=True)
for q in QS:
    print(f"\nQ: {q}", flush=True)
    print(f"  [原版  ] {ask(8081,q)}", flush=True)
    print(f"  [neg150] {ask(8091,q)}", flush=True)
print("\nWIDE_DONE")
