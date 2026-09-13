# -*- coding: utf-8 -*-
"""精确定位: 0-shot / 1-shot / 3-shot 的表现 -> 判断是特化还是泛化"""
import json, urllib.request
import sympy as sp
from sympy import symbols, sin, cos, diff, integrate, solve, simplify, ln, exp, tan
x,th=sp.Symbol('x'),sp.Symbol('theta')
U="http://127.0.0.1:8081/v1/chat/completions"
def ask(msgs,mx=180,t=0.0):
    body=json.dumps({"messages":msgs,"max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:40]}"
ENV=dict(diff=diff,integrate=integrate,solve=solve,simplify=simplify,
         sin=sin,cos=cos,tan=tan,ln=sp.log,exp=sp.exp,log=sp.log,
         x=x,theta=th,symbols=symbols,sp=sp)
def run(shots,label):
    sys=f"把中文数学任务翻译成 sympy 代码，只输出一行代码。{shots}"
    QS=["求 x 的平方的导数","对 sin(x) 积分","解方程 x+3=10","求 ln(x) 的导数",
        "求 tan(x) 的导数","化简 cos(x) 的平方加 sin(x) 的平方"]
    ok=0
    print(f"\n{'='*80}\n### {label}\n{'='*80}", flush=True)
    for q in QS:
        a=ask([{"role":"system","content":sys},{"role":"user","content":q}])
        code=a.strip().split("\n")[-1].strip().strip('`')
        try: r=sp.simplify(eval(code,{"__builtins__":{}},ENV)); err=None
        except Exception as e: r=None; err=str(e)[:35]
        good = r is not None
        ok+=good
        print(f"  {q:<30} -> {code[:50]:<52} {'✅'+str(r)[:22] if good else '❌ '+str(err)}", flush=True)
    print(f"  ★ 可用率 {ok}/{len(QS)}", flush=True)
    return ok

S0=""
S1="""
示例：
  求 x 的三次方的导数
  diff(x**3, x)
"""
S3="""
示例：
  求 x 的三次方的导数
  diff(x**3, x)
  对 e 的 x 次方积分
  integrate(exp(x), x)
  解方程 2*x=8
  solve(2*x-8, x)
"""
a=run(S0,"0-shot (只给任务描述, 无示例)")
b=run(S1,"1-shot (一个示例)")
c=run(S3,"3-shot (三个示例)")
print(f"\n{'='*80}")
print(f"★ 结论: 0-shot {a}/6  ->  1-shot {b}/6  ->  3-shot {c}/6")
print(f"{'='*80}")
print("GEN_DONE")
