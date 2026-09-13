# -*- coding: utf-8 -*-
"""★ 脚手架梯度: 撤掉多少支撑, 它还能走?
   等级1: 全给 (模板+流程+状态回传)
   等级2: 给模板, 让它自己决定每步做什么
   等级3: 只给任务, 它自己规划整个链
"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify, trigsimp, exp, integrate
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(msgs,mx=250,t=0.0):
    b=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try: return json.loads(urllib.request.urlopen(r,timeout=200).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x'); ENV=dict(diff=diff,simplify=simplify,trigsimp=trigsimp,
                           sin=sin,cos=cos,exp=exp,integrate=integrate,x=x,sp=sp)
def exec1(code):
    try: return str(sp.simplify(eval(code.strip().strip('`'),{"__builtins__":{}},ENV))), None
    except Exception as e: return None,str(e)[:25]
def pick(txt):
    cands=re.findall(r'⟨calc⟩(.+?)⟨/calc⟩',txt)
    for m in re.finditer(r'(diff|simplify|trigsimp|integrate)\(',txt):
        i=m.start(); d=0; j=i
        while j<len(txt):
            if txt[j]=='(': d+=1
            elif txt[j]==')':
                d-=1
                if d==0: break
            j+=1
        if d==0 and j-i<120: cands.append(txt[i:j+1])
    for c in cands:
        r,e=exec1(c)
        if r is not None: return c,r
    return None,None

print("="*94); print("★ 脚手架梯度测试: 撤掉支撑后还能走多远?"); print("="*94, flush=True)

# ---------- 等级1: 全脚手架 ----------
print("\n【等级1】全脚手架 (我告诉它每步做什么: 连续求导)", flush=True)
S1="""多步推导器。只输出一行 sympy 代码。
当前表达式: {cur}
调用形式: diff(<当前表达式完整抄写>, x)
只输出代码:"""
cur="sin(x)**2"; n=0
for i in range(1,13):
    a=ask([{"role":"system","content":S1.format(cur=cur)}])
    c,r=pick(a)
    if not r or r==cur: break
    print(f"  [{i:2d}] {r[:44]}", flush=True); cur=r; n=i
print(f"  → {n} 步", flush=True)

# ---------- 等级2: 半脚手架 (给工具目录, 它自己决定做什么) ----------
print("\n【等级2】半脚手架 (给工具+目标, 它自己决定每步)", flush=True)
S2="""你是多步推理器。可用 sympy 工具:
  diff(f,x) 求导 | simplify(e) 化简 | trigsimp(e) 三角化简 | expand(e) 展开
目标: {goal}
每步只输出一行代码。若已完成, 输出 DONE。
当前状态: {cur}
只输出一行代码:"""
for goal,start,TRUE in [
   ("求连续5阶导数","exp(x)", [sp.exp(x)]*5),
   ("分解并化简","(x**2-1)/(x-1)", ["x+1"]),
   ("求积分","x**2", ["x**3/3"]),
]:
    print(f"\n  ▸ 目标: {goal}   起点: {start}", flush=True)
    cur=start; n=0
    for i in range(1,7):
        a=ask([{"role":"system","content":S2.format(goal=goal,cur=cur)}])
        if "DONE" in a.upper().split("\n")[-1]: print(f"    [{i}] DONE (当前 {cur})", flush=True); break
        c,r=pick(a)
        if not r: print(f"    [{i}] ❌ 无调用: {a[:60]}", flush=True); break
        print(f"    [{i}] {c[:38]:<40} -> {r[:30]}", flush=True)
        if r==cur: print("          原地打转, 停", flush=True); break
        cur=r; n=i
    print(f"    → {n} 步", flush=True)

# ---------- 等级3: 无脚手架 (只给任务) ----------
print("\n【等级3】无脚手架 (只给题目, 它自己规划)", flush=True)
for q in ["求 f(x)=sin(x)*cos(x) 的三阶导数。请自己规划步骤并给出最终答案。",
          "计算 sin(x)**2 的不定积分。请自己规划。"]:
    a=ask([{"role":"user","content":q}], mx=300)
    print(f"\n  Q: {q}", flush=True)
    print(f"  A: {a[:400]}", flush=True)
    c,r=pick(a)
    if c: print(f"  → 提取到调用: {c} => {r}", flush=True)
print("GRAD_DONE")
