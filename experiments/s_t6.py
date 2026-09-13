import json, urllib.request
def ask(port,q,mx=50):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":0.2}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=120).read())["choices"][0]["message"]["content"].strip().replace("\n"," ")[:95]
    except Exception as e: return f"ERR {str(e)[:35]}"
QS=["求 sin(x) 对 x 的导数。","对 x 的平方求导。","计算：347乘以28等于多少？"]
NAMES={8081:"原版    ",8091:"neg150  ",8092:"pos150  "}
print("="*86); print("权重手术效果对比"); print("="*86, flush=True)
for q in QS:
    print(f"\nQ: {q}", flush=True)
    for p in [8081,8091,8092]:
        print(f"  [{NAMES[p]}] {ask(p,q)}", flush=True)
print("\nT6_DONE")
