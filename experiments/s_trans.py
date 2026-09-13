# -*- coding: utf-8 -*-
"""教模型"翻译" (自然语言 -> sympy调用), 而不是"求解" """
import json, urllib.request
import sympy as sp
from sympy import symbols, sin, cos, diff, integrate, simplify, solve, Matrix
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(messages, mx=90, t=0.1):
    body=json.dumps({"messages":messages,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:60]}"

SYS = """你是一个"翻译器"，把中文数学问题翻译成 sympy 调用。不要计算结果，只输出代码。
可用函数：
  diff(表达式, 变量)
  integrate(表达式, 变量)
  integrate(表达式, (变量, 下界, 上界))
  solve(方程, 变量)
  simplify(表达式)
示例：
  问：求 x**3 对 x 的导数     答：diff(x**3, x)
  问：求 sin(x) 的积分        答：integrate(sin(x), x)
  问：求 x**2 在 0 到 1 的定积分  答：integrate(x**2, (x, 0, 1))
  问：解方程 3*x=21           答：solve(3*x-21, x)
  问：求 sin(x)**2 对 x 的导数 答：diff(sin(x)**2, x)
现在开始，只输出一行代码："""

TESTS=[
 ("求 x**4 对 x 的导数",        "diff(x**4, x)"),
 ("求 cos(x) 对 x 的导数",      "diff(cos(x), x)"),
 ("求 x**3 在 1 到 2 的定积分", "integrate(x**3, (x, 1, 2))"),
 ("解方程 5*x=45",              "solve(5*x-45, x)"),
 ("求 sin(theta)**2 对 theta 的导数", "diff(sin(theta)**2, theta)"),
 ("求 tan(theta) 对 theta 的导数",    "diff(tan(theta), theta)"),
 ("求 1/sin(theta)**2 对 theta 的导数","diff(1/sin(theta)**2, theta)"),
]
print("="*84); print("测试: 模型能否学会「翻译」成 sympy 调用"); print("="*84, flush=True)
ok=0
for q,expect in TESTS:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":q}])
    # 抽出代码行
    code=a.strip().split("\n")[-1].strip()
    good = code.replace(" ","")==expect.replace(" ","")
    ok+=good
    print(f"\n  问: {q}\n     期望: {expect}\n     模型: {code[:80]}  {'✅' if good else '❌'}", flush=True)
print(f"\n  翻译准确率: {ok}/{len(TESTS)}", flush=True)

# 关键验证: 模型给出的代码, sympy 能不能算出正确结果?
print("\n"+"="*84); print("★ 端到端: 模型翻译 -> sympy 执行 -> 结果"); print("="*84, flush=True)
th=sp.Symbol('theta', real=True)
ENV={"diff":diff,"integrate":integrate,"solve":solve,"simplify":simplify,
     "sin":sin,"cos":cos,"tan":sp.tan,"x":sp.Symbol('x'),"theta":th}
for q,expect in TESTS[:3]+TESTS[4:]:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":q}])
    code=a.strip().split("\n")[-1].strip()
    try:
        r=sp.simplify(eval(code, {"__builtins__":{}}, ENV))
        print(f"  {q}\n     代码: {code}\n     结果: {r}", flush=True)
    except Exception as e:
        print(f"  {q}\n     代码: {code}\n     ❌ 执行失败: {str(e)[:60]}", flush=True)
print("TRANS_DONE")
