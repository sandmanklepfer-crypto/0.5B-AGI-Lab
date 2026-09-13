# -*- coding: utf-8 -*-
"""测: 行为协议 (先验证 -> 不行再自己推) 能不能用 prompt 引导出来"""
import json, urllib.request
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(msgs,mx=150,t=0.3):
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:40]}"

PROTO="""你要遵守这个流程：
1) 先检查能不能用形式化工具验证（计算、符号推导等）
2) 能的话，输出调用表达式
3) 不能的话，再说"这个无法形式验证，我尝试自己推理"，然后自己推理
绝不要说"我无法回答"或"对不起我没学会"。"""
QS=["计算：347乘以28等于多少？","求 sin(x) 对 x 的导数。","为什么天是蓝色的？","黎曼猜想是什么？"]
print("="*82); print("A. 不给协议 (基线)"); print("="*82, flush=True)
for q in QS:
    print(f"\n  问: {q}\n  答: {ask([{'role':'user','content':q}])[:160]}", flush=True)
print("\n"+"="*82); print("B. 给行为协议"); print("="*82, flush=True)
for q in QS:
    a=ask([{"role":"system","content":PROTO},{"role":"user","content":q}])
    print(f"\n  问: {q}\n  答: {a[:180]}", flush=True)
print("\nBEH_DONE")
