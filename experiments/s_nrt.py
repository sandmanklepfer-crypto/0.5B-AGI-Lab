# -*- coding: utf-8 -*-
"""对比: 无 cvec(8081) vs 去拒绝cvec(8083)"""
import json, urllib.request
def ask(port, msgs, mx=150, t=0.2):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip().replace("\n"," ")
    except Exception as e: return f"ERR {str(e)[:40]}"
QS=["求 sin(x) 对 x 的导数。","对 x 的平方求导。","解方程 3x=21，求x。",
    "黎曼曲率张量 R_abcd 关于 a,b 是对称还是反对称？"]
print("="*84); print("对比: 【原版】 vs 【去拒绝cvec】"); print("="*84, flush=True)
for q in QS:
    print(f"\n  问: {q}", flush=True)
    print(f"    [原版   ] {ask(8081,[{'role':'user','content':q}])[:120]}", flush=True)
    print(f"    [去拒cvec] {ask(8083,[{'role':'user','content':q}])[:120]}", flush=True)
print("\nNRT_DONE")
