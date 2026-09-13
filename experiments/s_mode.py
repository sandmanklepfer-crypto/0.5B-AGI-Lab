# -*- coding: utf-8 -*-
"""★ 决定性 2x2: 同一个状态, 4种问法, 看"模式"是不是关键变量"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(q,mx=150,t=0.0):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x')
def E(c):
    try: return str(sp.simplify(eval(c.strip().strip('`'),{"__builtins__":{}},
        {"diff":diff,"sin":sin,"cos":cos,"x":x})))
    except: return "ERR"
def pick(t):
    for m in re.finditer(r'(diff|simplify)\(',t):
        i=m.start(); d=0; j=i
        while j<len(t):
            if t[j]=='(': d+=1
            elif t[j]==')':
                d-=1
                if d==0: break
            j+=1
        if d==0 and j-i<100: return t[i:j+1]
    return None

CUR="-1024*cos(2*x)"      # 第11阶导, 求第12阶
TRUE="2048*sin(2*x)"
PROMPTS=[
 ("① 直接算(无工具)",   f"已知当前表达式 = {CUR}。请直接计算它的导数, 只输出结果表达式。"),
 ("② 调工具(明确要求)", f"当前表达式 = {CUR}。请调用 diff 工具求它的导数, 只输出一行代码。"),
 ("③ 只说要算(不给工具名)", f"当前表达式 = {CUR}。请给出它的导数。"),
 ("④ 结构化(step=11)",  f"[step=11] 当前 = {CUR}\n请输出第12步: diff(<抄写当前表达式>, x)"),
]
print("="*92); print(f"★ 2x2 对照: 状态固定为 {CUR}  (真值 {TRUE})"); print("="*92, flush=True)
for tag,q in PROMPTS:
    a=ask(q)
    c=pick(a)
    r=E(c) if c else "(无调用)"
    ok = (r==TRUE) or (r.replace(" ","")==TRUE.replace(" ",""))
    print(f"\n  {tag}", flush=True)
    print(f"    原始: {a[:110]}", flush=True)
    print(f"    提取: {c}", flush=True)
    print(f"    结果: {r}   {'✅ 正确' if ok else '❌'}", flush=True)
print("\nMODE_DONE")
