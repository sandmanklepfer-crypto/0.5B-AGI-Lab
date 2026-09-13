# -*- coding: utf-8 -*-
"""长链 v3: 充足输出 + 鲁棒提取"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify, trigsimp, exp
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(msgs,mx=250,t=0.0):
    b=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x'); ENV=dict(diff=diff,simplify=simplify,trigsimp=trigsimp,
                           sin=sin,cos=cos,exp=exp,x=x,sp=sp)
def try_exec(code):
    code=code.strip().strip('`')
    try:
        return str(sp.simplify(eval(code,{"__builtins__":{}},ENV))), None
    except Exception as e:
        return None, str(e)[:30]

def best_call(txt):
    """从输出里找第一个能成功执行的调用"""
    cands=[]
    # ① ⟨calc⟩ 形式
    cands += re.findall(r'⟨calc⟩(.+?)⟨/calc⟩', txt)
    # ② 函数调用 (允许多层括号)
    for m in re.finditer(r'(diff|simplify|trigsimp|expand)\(', txt):
        i=m.start(); d=0; j=i
        while j<len(txt):
            if txt[j]=='(': d+=1
            elif txt[j]==')':
                d-=1
                if d==0: break
            j+=1
        if d==0: cands.append(txt[i:j+1])
    # ③ 单行
    for ln in txt.split("\n"):
        ln=ln.strip()
        if ln and not ln.startswith("问") and len(ln)<120: cands.append(ln)
    for c in cands:
        r,e=try_exec(c)
        if r is not None: return c,r
    return None,None

SYS="""多步推导器。每步只输出【一个】sympy 调用, 只输出代码。
可用: diff(f,x) 求导, simplify(e) 化简, trigsimp(e) 三角化简, expand(e) 展开
当前表达式: {cur}
只输出一行代码:"""
print("="*92); print("★ 长链 v3: 从 sin(x)*cos(x) 连续求导 (充足输出+鲁棒提取)"); print("="*92, flush=True)
cur="sin(x)*cos(x)"; steps=0
TRUE=[sp.simplify(sp.diff(sp.sin(x)*sp.cos(x),x,k)) for k in range(1,9)]
for step in range(1,13):
    a=ask([{"role":"system","content":SYS.format(cur=cur)}])
    code,r=best_call(a)
    if r is None:
        print(f"  [{step:2d}] ❌ 无可执行调用 | 原始输出: {a[:90]}", flush=True); break
    ok = (r!=cur)
    # 检查是否等于正确的k阶导
    try:
        got=sp.sympify(r); right = sp.simplify(got-TRUE[step-1])==0
    except Exception: right=False
    print(f"  [{step:2d}] {code[:46]:<48} -> {r[:26]:<28} {'✅正确' if right else '⚠️不同'}", flush=True)
    if not ok: print(f"       结果未变, 停", flush=True); break
    cur=r; steps=step
print(f"\n  → 连续走了 {steps} 步", flush=True)
print(f"  真值: " + " | ".join(f"{i+1}阶={sp.simplify(sp.diff(sp.sin(x)*sp.cos(x),x,i+1))}" for i in range(5)), flush=True)
print("LONG2_DONE")
