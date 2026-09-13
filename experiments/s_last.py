# -*- coding: utf-8 -*-
"""最终验证: 模型的能力是否100%由'训练过的格式'决定?"""
import json, urllib.request, re
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=60,t=0.0):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
print("="*88); print("★ 判断: 能力 = 训练过的格式?"); print("="*88, flush=True)
T=[
 ("训练格式: 计算：a乘以b",   "计算：37乘以23等于多少？"),
 ("训练格式: 计算 a+b",      "计算 47+38 等于多少"),
 ("训练格式: 解方程 ax=b",   "解方程：4x=36，求x。"),
 ("训练格式: a的b次方",      "计算 3 的 4 次方。"),
 ("训练格式: 百分比",         "250 的 20% 是多少？"),
 ("—非训练格式: 直接算术—",   "37乘以23等于几"),
 ("—非训练格式: 递推—",      "x=7, x_next=2*x+1, x_next=?"),
 ("—非训练格式: 英文算术—",   "What is 37 times 23?"),
]
for tag,q in T:
    a=ask(q)
    m=re.findall(r'⟨calc⟩(.+?)⟨/calc⟩',a)
    print(f"\n  [{tag}]", flush=True)
    print(f"    Q: {q}", flush=True)
    print(f"    A: {a[:90]}", flush=True)
    print(f"    {'★ 输出了工具调用: '+m[0] if m else '（无工具调用）'}", flush=True)
print("\nLAST_DONE")
