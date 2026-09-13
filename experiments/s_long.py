# -*- coding: utf-8 -*-
"""测长链的真实上限: 崩在'指代'还是'计划'?"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify, trigsimp, exp
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(msgs,mx=110,t=0.0):
    b=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=180).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x'); ENV=dict(diff=diff,simplify=simplify,trigsimp=trigsimp,
                           sin=sin,cos=cos,exp=exp,x=x,sp=sp)
def T(code):
    code=code.strip().split("\n")[-1].strip().strip('`')
    try: return str(sp.simplify(eval(code,{"__builtins__":{}},ENV)))
    except Exception as e: return "ERR"

# 模式A: 只给"当前表达式" (模型自己指代)
SA="""多步推导器。每步输出一个 sympy 调用, 只输出代码。
可用: diff(f,x), simplify(e), trigsimp(e), expand(e)
当前表达式: {cur}
只输出一行代码:"""
# 模式B: 明确给出"该用什么" (减少指代负担)
SB="""多步推导器。只输出一行 sympy 代码。
当前表达式(请把这个表达式的完整文字直接抄进代码里, 不要用 f 或 g 这样的缩写): {cur}
调用形式必须是: diff(<把当前表达式完整抄在这里>, x)
只输出代码:"""
for tag,S in [("模式A 自由指代",SA),("模式B 强制完整抄写",SB)]:
    print("\n"+"="*90); print(f"★ [{tag}] 从 sin(x)*cos(x) 连续求导, 看能走几步"); print("="*90, flush=True)
    cur="sin(x)*cos(x)"
    for step in range(1,13):
        a=ask([{"role":"system","content":S.format(cur=cur)}])
        code=a.split("\n")[-1].strip()
        r=T(code)
        ok = (not r.startswith("ERR")) and r!=cur
        print(f"  [{step:2d}] {code[:44]:<46} -> {r[:30]:<32} {'✅' if ok else '❌'}", flush=True)
        if not ok:
            print(f"       崩因: {'工具错误(指代/语法)' if r.startswith('ERR') else '结果未变'}", flush=True)
            break
        cur=r
print("\n"+"="*90); print("★ 真值对照"); print("="*90, flush=True)
f=sp.sin(x)*sp.cos(x)
for k in range(1,9):
    f=sp.diff(f,x); ff=sp.simplify(f)
    if k<=5: print(f"  {k}阶导: {ff}", flush=True)
print("LONG_DONE")
