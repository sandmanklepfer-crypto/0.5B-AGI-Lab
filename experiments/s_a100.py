import json, urllib.request
def ask(port,q,mx=70):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":0.25}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=90).read())["choices"][0]["message"]["content"].strip().replace("\n"," ")[:100]
    except Exception as e: return f"ERR {str(e)[:30]}"
QS=["解方程：5x=45，求x。","求 sin(x) 对 x 的导数。","计算：347乘以28等于多少？","介绍一下你自己。"]
print("="*88); print("alpha=100 测试"); print("="*88, flush=True)
for q in QS:
    print(f"\nQ: {q}", flush=True)
    print(f"  [原版  ] {ask(8081,q)}", flush=True)
    print(f"  [neg100] {ask(8093,q)}", flush=True)
print("\nA100_DONE")
