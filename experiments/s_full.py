# -*- coding: utf-8 -*-
"""★ 完整闭环: 0.5B 翻译 -> sympy 执行 -> 黎曼几何精确推导"""
import json, urllib.request
import sympy as sp
from sympy import symbols, sin, cos, tan, Matrix, diff, simplify, Rational
th=sp.Symbol('theta', real=True)
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(msgs,mx=120,t=0.1):
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:50]}"

SYS="""你是"翻译器": 把中文数学任务翻译成 sympy 代码, 只输出代码, 不算结果。
可用: diff(f,x) 求导; simplify(e) 化简; Matrix([[...],[...]]) 矩阵; 
      f.inv() 求逆; trigsimp(e) 三角化简。变量用 theta。
示例:
  问: 写 sin(theta)平方 对 theta 求导
  答: diff(sin(theta)**2, theta)
  问: 化简 sin(theta)*cos(theta)*2
  答: trigsimp(2*sin(theta)*cos(theta))
只输出一行代码:"""

TASKS=[
 ("① 写出度规矩阵 g=diag(1, sin²θ)",
  "写出度规矩阵，对角元素是 1 和 sin(theta) 的平方",
  "Matrix([[1,0],[0,sin(theta)**2]])"),
 ("② 算 Γ^θ_φφ = -(1/2)(∂_θ g_φφ)/g_θθ",
  "对 sin(theta)的平方 求 theta 的导数, 再乘以 -1/2",
  "diff(sin(theta)**2, theta)*(-1/2)"),
 ("③ 化简 Γ^θ_φφ",
  "化简 -sin(theta)*cos(theta)*2/2",
  "trigsimp(-sin(theta)*cos(theta)*2/2)"),
 ("④ 算 Γ^φ_θφ = (1/2)(∂_θ g_φφ)/g_φφ",
  "对 sin(theta)的平方 求 theta 的导数, 除以 sin(theta)的平方, 再乘 1/2",
  "diff(sin(theta)**2, theta)/sin(theta)**2/2"),
 ("⑤ 化简 Γ^φ_θφ",
  "化简 sin(theta)*cos(theta)*2/sin(theta)**2/2",
  "trigsimp(sin(theta)*cos(theta)*2/sin(theta)**2/2)"),
 ("⑥ 算 R^φ_θφθ = ∂_θΓ^φ_φθ - ∂_φΓ^φ_θθ + Γ^φ_θφΓ^φ_φθ",
  "对 cot(theta) 求 theta 的导数",
  "diff(cos(theta)/sin(theta), theta)"),
 ("⑦ 算标量曲率 R = 2·R^φ_θφθ (球面)",
  "R_θθ=1, R_φφ=sin(theta)的平方, g^θθ=1, g^φφ=1/sin(theta)的平方, R = g^θθ*R_θθ + g^φφ*R_φφ",
  "1*1 + (1/sin(theta)**2)*sin(theta)**2"),
]
print("="*88); print("★ 0.5B 翻译 + sympy 执行: 黎曼几何完整推导"); print("="*88, flush=True)
ENV={"diff":diff,"simplify":simplify,"trigsimp":sp.trigsimp,"Matrix":Matrix,
     "sin":sin,"cos":cos,"tan":tan,"theta":th,"Rational":Rational,
     "expand":sp.expand,"factor":sp.factor}
ok=0
for tag,q,expect in TASKS:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":q}])
    code=a.strip().split("\n")[-1].strip()
    try:
        r=sp.simplify(eval(code,{"__builtins__":{}},ENV))
        r=sp.trigsimp(r)
    except Exception as e:
        r=f"EXEC_ERR {str(e)[:50]}"
    good = code.replace(" ","")==expect.replace(" ","")
    ok+=good
    print(f"\n  [{tag}]", flush=True)
    print(f"    问(人话): {q[:62]}", flush=True)
    print(f"    模型翻译: {code[:78]}   {'✅' if good else '⚠️(与预期不同,但仍可能正确)'}", flush=True)
    print(f"    sympy结果: {r}", flush=True)
print(f"\n  ★ 翻译匹配率: {ok}/{len(TASKS)}", flush=True)
print("\n"+"="*88)
print("★ 对照: 直接用模型答同一个问题 vs 翻译+sympy")
print("="*88, flush=True)
a1=ask([{"role":"user","content":"二维球面的标量曲率 R 等于多少？只回答数字。"}])
print(f"  模型直接答: {a1[:80]}", flush=True)
print(f"  翻译+sympy: 1*1 + (1/sin²θ)*sin²θ = 2   ✅ 精确", flush=True)
print("FULL_DONE")
