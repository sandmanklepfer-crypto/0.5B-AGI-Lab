import json, urllib.request
def ask(port,q,mx=60):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":0.2}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try:
        return json.loads(urllib.request.urlopen(r,timeout=120).read())["choices"][0]["message"]["content"].strip().replace("\n"," ")
    except Exception as e: return f"ERR {str(e)[:40]}"
QS=["求 sin(x) 对 x 的导数。","对 x 的平方求导。","计算：347乘以28等于多少？","黎曼猜想是什么？"]
print("="*80); print("对比: calc_v1(8081) vs calc_v1_un5(8090)  [alpha=5 权重手术]"); print("="*80, flush=True)
for q in QS:
    print(f"\n  Q: {q}", flush=True)
    print(f"    [原版    ] {ask(8081,q)[:110]}", flush=True)
    print(f"    [unlock5 ] {ask(8090,q)[:110]}", flush=True)
print("\nT5_DONE")
