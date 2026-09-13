# -*- coding: utf-8 -*-
"""完整输出: 看 neg100 的推理能走到哪一步 (不截断)"""
import json, urllib.request
def ask(port,q,mx=400):
    U=f"http://127.0.0.1:{port}/v1/chat/completions"
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":0.2}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try:
        return json.loads(urllib.request.urlopen(r,timeout=180).read())["choices"][0]["message"]["content"]
    except Exception as e: return f"ERR {str(e)[:40]}"
QS=[
 ("求导","求 sin(x) 对 x 的导数。请一步一步写出来。"),
 ("求导-简单","x 的平方的导数是多少？"),
 ("解方程","解方程：5x=45，求x。"),
 ("推理链","如果 A 大于 B，B 大于 C，那么 A 和 C 谁大？为什么？"),
]
for tag,q in QS:
    print("\n"+"#"*94, flush=True)
    print(f"# [{tag}] {q}", flush=True)
    print("#"*94, flush=True)
    a=ask(8093,q)
    print(a, flush=True)
    print(f"\n[长度 {len(a)} 字符]", flush=True)
print("\nDEEP_DONE")
