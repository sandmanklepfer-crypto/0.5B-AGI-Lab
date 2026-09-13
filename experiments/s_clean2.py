# -*- coding: utf-8 -*-
"""干净版: 每个任务只做【一个操作】, ENV 补齐"""
import json, urllib.request
import sympy as sp
from sympy import symbols, sin, cos, tan, cot, Matrix, diff, simplify
th=sp.Symbol('theta', real=True)
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(msgs,mx=200,t=0.05):
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:50]}"
SYS="""把中文数学任务翻译成 sympy 代码，只输出一行代码，不要解释、不要算结果。
可用函数：diff(f,x), simplify(e), trigsimp(e), integrate(f,x)
变量名用 theta 或 x。sin/cos/tan/cot 可直接用。
示例：
  问：求 sin(theta) 平方对 theta 的导数
  diff(sin(theta)**2, theta)
  问：化简 2*sin(theta)*cos(theta)
  trigsimp(2*sin(theta)*cos(theta))
  问：求 cot(theta) 对 theta 的导数
  diff(cot(theta), theta)
只输出代码："""
# 每题只做一个操作
T=[
 ("对 sin(theta)**2 求 theta 的导数", "diff(sin(theta)**2, theta)"),
 ("对 cot(theta) 求 theta 的导数",    "diff(cot(theta), theta)"),
 ("化简 2*sin(theta)*cos(theta)",     "trigsimp(2*sin(theta)*cos(theta))"),
 ("化简 sin(theta)*cos(theta)/sin(theta)**2", "simplify(sin(theta)*cos(theta)/sin(theta)**2)"),
 ("对 1/sin(theta)**2 求 theta 的导数","diff(1/sin(theta)**2, theta)"),
 ("化简 sin(theta)**2+cos(theta)**2","simplify(sin(theta)**2+cos(theta)**2)"),
 ("对 x**5 求 x 的导数",              "diff(x**5, x)"),
]
ENV=dict(diff=diff,simplify=simplify,trigsimp=sp.trigsimp,integrate=sp.integrate,
         sin=sin,cos=cos,tan=tan,cot=cot,theta=th,x=sp.Symbol('x'))
print("="*86); print("干净版: 0.5B 翻译 (每题一个操作) + sympy 精确执行"); print("="*86, flush=True)
okc=0; okv=0
for q,exp in T:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":q}])
    code=a.strip().split("\n")[-1].strip().strip('`')
    if code.lower().startswith("python"): code=code[6:].strip()
    try: r=sp.trigsimp(sp.simplify(eval(code,{"__builtins__":{}},ENV))); err=None
    except Exception as e: r=None; err=str(e)[:40]
    same = code.replace(" ","")==exp.replace(" ","")
    okc+=same
    print(f"\n  Q: {q}", flush=True)
    print(f"    模型翻译: {code[:76]}  {'✅与预期一致' if same else '⚠️写法不同'}", flush=True)
    print(f"    sympy结果: {r if r is not None else '执行失败:'+err}", flush=True)
print(f"\n  ★ 翻译匹配: {okc}/{len(T)}", flush=True)

print("\n"+"="*86); print("★ 黎曼几何: 用翻译链推导 (每步 sympy 精确)"); print("="*86, flush=True)
tsk=[
 ("度规: 对角矩阵, 元素 1 和 sin(theta)平方", "Matrix([[1,0],[0,sin(theta)**2]])"),
 ("Γ^θ_φφ: 对 sin(theta)平方 求导, 乘 -1/2", "diff(sin(theta)**2, theta)*(-1/2)"),
 ("Γ^φ_θφ: 对 sin(theta)平方 求导, 除以 sin(theta)平方, 乘 1/2",
  "diff(sin(theta)**2, theta)/sin(theta)**2*(1/2)"),
 ("R^φ_θφθ: 对 cot(theta) 求导", "diff(cot(theta), theta)"),
]
for q,exp in tsk:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":q}])
    code=a.strip().split("\n")[-1].strip().strip('`')
    try: r=sp.trigsimp(sp.simplify(eval(code,{"__builtins__":{}},ENV))); e2=None
    except Exception as e: r=None; e2=str(e)[:40]
    print(f"\n  任务: {q[:66]}", flush=True)
    print(f"    模型翻译: {code[:76]}", flush=True)
    print(f"    ★ sympy 精确结果: {r if r is not None else '失败:'+e2}", flush=True)
print("\n  【对照】真值: Γ^θ_φφ=-sinθcosθ | Γ^φ_θφ=cotθ | R^φ_θφθ=1 | R标量=2", flush=True)
print("\n  【对照】模型直接答标量曲率:", ask([{"role":"user","content":"二维球面标量曲率R等于多少？只回答数字"}])[:50], flush=True)
print("CLEAN_DONE")
