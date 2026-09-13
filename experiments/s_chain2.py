# -*- coding: utf-8 -*-
"""长链测试 v2: 带强 few-shot (这是模型能用工具的前提)"""
import json, urllib.request, re
import sympy as sp
from sympy import symbols, sin, cos, tan, diff, integrate, solve, simplify, exp, log
U="http://127.0.0.1:8093/v1/chat/completions"
def ask(msgs,mx=120,t=0.0):
    b=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try:
        return json.loads(urllib.request.urlopen(r,timeout=180).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"
x=sp.Symbol('x')
ENV=dict(diff=diff,integrate=integrate,solve=solve,simplify=simplify,
         sin=sin,cos=cos,tan=tan,exp=exp,log=log,x=x,sp=sp)
def T(code):
    code=code.strip().split("\n")[-1].strip().strip('`')
    try: return str(sp.simplify(eval(code,{"__builtins__":{}},ENV)))
    except Exception as e: return "ERR:"+str(e)[:25]
def extract(txt):
    m=re.findall(r'⟨calc⟩(.+?)⟨/calc⟩',txt)
    if m: return m[0].strip()
    m=re.findall(r'(?:diff|integrate|solve|simplify)\([^()]*(?:\([^()]*\))?[^()]*\)',txt)
    return m[0] if m else None

SYS="""你是翻译器: 把中文数学任务翻译成 sympy 代码, 只输出一行代码。
可用: diff(f,x) 求导, integrate(f,x) 积分, solve(eq,x) 解方程, simplify(e)
示例:
  问: 求 x**3 对 x 的导数
  diff(x**3, x)
  问: 求 sin(x) 对 x 的导数
  diff(sin(x), x)
  问: 求 cos(x) 对 x 的导数
  diff(cos(x), x)
  问: 求 tan(x) 对 x 的导数
  diff(tan(x), x)
  问: 求 exp(x) 对 x 的导数
  diff(exp(x), x)
  问: 求 log(x) 对 x 的导数
  diff(log(x), x)
只输出代码:"""

print("="*94); print("★ v2: 带 few-shot 的单步能力 (基础前提)"); print("="*94, flush=True)
STEPS=[("x**3",),("sin(x)",),("cos(x)",),("tan(x)",),("exp(x)",),("log(x)",),
       ("x**5",),("sin(x)**2",)]
ok=0
for (f,) in STEPS:
    a=ask([{"role":"system","content":SYS},{"role":"user","content":f"求 {f} 对 x 的导数"}])
    code=a.split("\n")[-1].strip().strip('`')
    r=T(code)
    good=not r.startswith("ERR")
    ok+=good
    print(f"  {f:<14} -> {code:<34} {r:<26} {'✅' if good else '❌'}", flush=True)
print(f"  → 单步 {ok}/{len(STEPS)} = {100*ok/len(STEPS):.0f}%", flush=True)

print("\n"+"="*94); print("★ 长链: 模型【自己编排】多步推导 (每步看结果决定下一步)"); print("="*94, flush=True)
# 任务: 逐步化简到一个目标
PLAN="""你是一个多步推导器。每一步你只能输出【一个】sympy 调用。
可用: diff(f,x), simplify(e), expand(e), factor(e), trigsimp(e)
规则: 如果当前表达式已经最简, 输出 DONE
当前表达式: {cur}
目标: 得到最简形式
只输出一行代码 (或 DONE):"""
cur="sin(x)*cos(x)"
seq=[]
for step in range(1,7):
    a=ask([{"role":"system","content":PLAN.format(cur=cur)}], mx=100)
    code=a.split("\n")[-1].strip()
    if "DONE" in code.upper():
        print(f"  [第{step}步] 模型宣布 DONE, 当前: {cur}", flush=True); break
    r=T(code)
    print(f"  [第{step}步] {code[:38]:<40} -> {r[:34]}", flush=True)
    seq.append((code,r))
    if r.startswith("ERR") or r==cur:
        print(f"           ⚠️ {'工具错误' if r.startswith('ERR') else '结果未变(原地打转)'} → 链终止", flush=True); break
    cur=r
print(f"  → 走完 {len(seq)} 步", flush=True)

print("\n"+"="*94); print("★ 对照: 外部编排 (人给流程, 模型只做单步)"); print("="*94, flush=True)
print("  流程: ①算sin' ②算cos' ③组合 (乘积法则)", flush=True)
s1=T(ask([{"role":"system","content":SYS},{"role":"user","content":"求 sin(x) 对 x 的导数"}]).split("\n")[-1])
s2=T(ask([{"role":"system","content":SYS},{"role":"user","content":"求 cos(x) 对 x 的导数"}]).split("\n")[-1])
print(f"  ①sin'(x) = {s1}", flush=True)
print(f"  ②cos'(x) = {s2}", flush=True)
try:
    combo=sp.simplify(sp.sympify(s1,x=x)*sp.cos(x)+sp.sin(x)*sp.sympify(s2,x=x))
    combo2=sp.trigsimp(combo)
    print(f"  ③乘积法则组合: {combo2}   ✅ (正确应为 cos(2x))", flush=True)
    print(f"     验算: cos(2x) 展开 = {sp.expand_trig(sp.cos(2*x))}", flush=True)
except Exception as e:
    print(f"  ③失败 {str(e)[:50]}", flush=True)
print("CHAIN2_DONE")
