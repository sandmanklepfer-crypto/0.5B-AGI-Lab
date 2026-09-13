# -*- coding: utf-8 -*-
"""决定性实验: 给工具后, 长链能走多深?
   方法A: 模型【自己编排】(每步问它"下一步做什么")
   方法B: 外部编排 (固定流程, 模型只做单步识别)
   对照: 链长 1,2,3,5,8
"""
import json, urllib.request, re, time
import sympy as sp
from sympy import symbols, sin, cos, tan, diff, integrate, solve, simplify, exp, log

U="http://127.0.0.1:8093/v1/chat/completions"   # neg100 (已解锁)
def ask(q,mx=200,t=0.15):
    b=json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":mx,
                  "temperature":t}).encode()
    r=urllib.request.Request(U,data=b,headers={"Content-Type":"application/json"})
    try:
        return json.loads(urllib.request.urlopen(r,timeout=180).read())["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:30]}"

x=sp.Symbol('x')
ENV=dict(diff=diff,integrate=integrate,solve=solve,simplify=simplify,
         sin=sin,cos=cos,tan=tan,exp=exp,log=log,x=x,sp=sp)

def run_tool(code):
    """执行工具, 返回结果字符串"""
    code=code.strip().strip('`')
    try:
        r=sp.simplify(eval(code,{"__builtins__":{}},ENV))
        return str(r)
    except Exception as e:
        return f"ERR:{str(e)[:30]}"

def extract_calls(txt):
    """抽 ⟨calc⟩xx⟨/calc⟩ 或 diff(...) 形式"""
    out=re.findall(r'⟨calc⟩(.+?)⟨/calc⟩',txt)
    if out: return out[0].strip()
    out=re.findall(r'(?:diff|integrate|solve|simplify)\([^)]*\)',txt)
    if out: return out[0]
    return None

print("="*94)
print("★ 长链测试: 给工具后能走多深?")
print("="*94, flush=True)

# ============ 实验1: 单步识别能力 (基础) ============
print("\n【实验1】单步识别: 模型能否正确选择工具并写对参数?", flush=True)
print(f"  {'任务':<38}{'模型的调用':<34}{'执行结果'}")
print("  "+"-"*92, flush=True)
STEPS=[
 ("求 x**3 对 x 的导数", "diff(x**3, x)"),
 ("求 sin(x) 对 x 的导数", "diff(sin(x), x)"),
 ("求 cos(x) 对 x 的导数", "diff(cos(x), x)"),
 ("求 tan(x) 对 x 的导数", "diff(tan(x), x)"),
 ("求 exp(x) 对 x 的导数", "diff(exp(x), x)"),
 ("求 log(x) 对 x 的导数", "diff(log(x), x)"),
]
ok=0
for q,exp in STEPS:
    a=ask(f"把任务翻译成 sympy 代码, 只输出一行代码: {q}")
    call=extract_calls(a) or a.split("\n")[-1][:40]
    res=run_tool(call) if call else "无"
    good = not str(res).startswith("ERR")
    ok+=good
    print(f"  {q:<38}{call[:32]:<34}{res[:32]}", flush=True)
print(f"  → 单步可用率 {ok}/{len(STEPS)}", flush=True)

# ============ 实验2: 自编排长链 (模型决定下一步) ============
print("\n【实验2】★ 自编排长链: 每步让模型看当前结果, 决定下一步调什么", flush=True)
TASK=("目标: 求 f(x)=sin(x)*cos(x) 对 x 的导数。\n"
      "你可以调用工具。规则: 如果是两个函数相乘, 应该用乘积法则。\n"
      "当前表达式: sin(x)*cos(x)\n"
      "请只输出下一步的 sympy 代码。")
history=[]; cur="sin(x)*cos(x)"
print(f"\n  起点: {cur}", flush=True)
for step in range(1,6):
    q=TASK.replace("sin(x)*cos(x)",cur)
    a=ask(q, 120)
    call=extract_calls(a)
    if not call:
        print(f"  [第{step}步] ❌ 模型没给出工具调用: {a[:80]}", flush=True)
        break
    res=run_tool(call)
    print(f"  [第{step}步] 模型→ {call[:40]:<42} 工具→ {res[:40]}", flush=True)
    history.append((call,res))
    if str(res).startswith("ERR"):
        print(f"           ❌ 工具报错, 链断", flush=True); break
    if step>=3: break
    cur=str(res)
    # 防止原地打转
    if len(history)>1 and history[-1][0]==history[-2][0]:
        print(f"           ⚠️ 重复调用同一工具 → 原地打转", flush=True); break
print(f"  → 自编排走了 {len(history)} 步", flush=True)

# ============ 实验3: 外部编排长链 (模型只做单步识别) ============
print("\n【实验3】外部编排: 固定流程, 模型只负责'翻译'每步", flush=True)
FLOW=[
 ("第1步: 识别乘积法则", "求 sin(x)*cos(x) 的导数, 应该用什么法则? 只回答: 乘积法则 或 链式法则 或 商法则"),
 ("第2步: 写出应用形式",  "sin*cos 的导数 = sin'*cos + sin*cos', 请把 sin' 写成 sympy: diff(sin(x),x)"),
 ("第3步: 算 sin'(x)",    "把任务翻译成 sympy 代码, 只输出代码: 求 sin(x) 对 x 的导数"),
 ("第4步: 算 cos'(x)",    "把任务翻译成 sympy 代码, 只输出代码: 求 cos(x) 对 x 的导数"),
]
for tag,q in FLOW:
    a=ask(q,120); call=extract_calls(a)
    res=run_tool(call) if call else "(无工具调用)"
    print(f"  [{tag}]", flush=True)
    print(f"     模型: {a[:90]}", flush=True)
    if call: print(f"     工具: {call} -> {res}", flush=True)
print("CHAIN_DONE")
