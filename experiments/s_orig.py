# -*- coding: utf-8 -*-
"""原创性测试: 训练集里绝对没有的任务
   1. 自创算法 (需要自己发明步骤)
   2. 类比迁移 (把学过的方法用到新领域)
   3. 反事实 (假设一个不存在的规则)
"""
import json, urllib.request, re
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=200,t=0.3):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"

T=[
 ("★1 原创算法", "请设计一个新方法来判断一个数是否能被7整除, 不要用除法。只说你设计的步骤。"),
 ("★2 类比迁移", "你会用两个工具: diff(求导) 和 integrate(积分)。现在我给你第三个: sum(f,n) 求和。\n请问: 如果只能调用这三个工具, 你能算出 Σn² 从1到10吗? 怎么写调用?"),
 ("★3 反事实",   "假设求导规则变成: d/dx(x^n) = n²·x^(n-1) (不是n倍, 是n平方倍)。\n那么 d/dx(x³) 等于多少? 只输出表达式。"),
 ("★4 组合创新", "请用 diff 和 solve 两个工具组合, 求出函数 f(x)=x³-3x 的所有极值点。写下你的调用序列。"),
 ("★5 元认知",   "你自己有哪些能力, 有哪些做不到? 请诚实列出。"),
]
print("="*92); print("★ 原创性测试 (训练集里没有的任务)"); print("="*92, flush=True)
for tag,q in T:
    print(f"\n{'─'*86}", flush=True)
    print(f"[{tag}]", flush=True)
    print(f"  Q: {q}", flush=True)
    a=ask(q, mx=230)
    print(f"  A: {a[:330]}", flush=True)
print("\nORIG_DONE")
