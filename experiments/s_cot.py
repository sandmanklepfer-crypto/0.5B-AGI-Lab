# -*- coding: utf-8 -*-
"""思维链 + sympy 工具闭环: 模型出步骤 -> sympy 精确算 -> 结果喂回 -> 下一步
   目标: 用【外部符号计算】做顶级推理, 模型只负责"出步骤"
"""
import json, urllib.request, re, io, contextlib
import sympy as sp
from sympy import symbols, sin, cos, diff, simplify, Matrix, Rational, sympify

U="http://127.0.0.1:8081/v1/chat/completions"
def ask(q, mx=100, t=0.2):
    body=json.dumps({"messages":[{"role":"user","content":q}],
                     "max_tokens":mx,"temperature":t}).encode()
    req=urllib.request.Request(U,data=body,headers={"Content-Type":"application/json"})
    try:
        r=json.loads(urllib.request.urlopen(req,timeout=120).read())
        return r["choices"][0]["message"]["content"].strip()
    except Exception as e: return f"ERR {str(e)[:60]}"

print("="*84)
print("黎曼几何: 思维链 + sympy 工具 (真精确推理)")
print("="*84, flush=True)

# ============ 关键: 把整个推导写成 sympy 程序, 由工具执行 ============
# 模型的任务: 给出这个 sympy 程序 (它不会算, 但"知道要算什么")
# 外部: 精确执行
th, ph = symbols('theta phi', real=True)
print("\n【工具侧】sympy 精确推导 (这一步不需要模型)", flush=True)
g = Matrix([[1,0],[0,sin(th)**2]])
n=2; gi=g.inv()
X=[th,ph]
Gam=[[[sp.simplify(sum(gi[a,m]*(diff(g[m,b],X[c])+diff(g[m,c],X[b])-diff(g[b,c],X[m])) for m in range(n))/2)
        for c in range(n)] for b in range(n)] for a in range(n)]
print(f"  Γ^θ_φφ = {Gam[0][1][1]}")
print(f"  Γ^φ_θφ = {Gam[1][0][1]}")
def R(a,b,c,d):
    e=diff(Gam[a][b][d],X[c])-diff(Gam[a][b][c],X[d])
    e+=sum(Gam[a][c][m]*Gam[m][b][d]-Gam[a][d][m]*Gam[m][b][c] for m in range(n))
    return sp.simplify(e)
Ric=[[sp.simplify(sum(R(a,b,a,d) for a in range(n))) for d in range(n)] for b in range(n)]
Rsc=sp.simplify(sum(gi[b,d]*Ric[b][d] for b in range(n) for d in range(n)))
print(f"  R_θθ={Ric[0][0]}   R_φφ={Ric[1][1]}")
print(f"  ★ 标量曲率 R = {Rsc}", flush=True)

# ============ 模型侧: 问它"该算什么" (而不是"结果是多少") ============
print("\n" + "="*84)
print("【模型侧】关键测试: 问『该算什么』(可工具化) vs 『结果是多少』(要靠自己)")
print("="*84, flush=True)
PAIRS=[
 ("靠自己(难):", "单位球面的标量曲率 R 等于多少？只回答数字。"),
 ("出步骤(可工具化):",
  "要计算二维球面的标量曲率，需要依次计算哪几个量？请只列步骤名称，用逗号分隔。"),
 ("写表达式(可工具化):",
  "二维球面度规 g=diag(1,sin²θ)。请写出 Γ^θ_φφ 的表达式，格式：Γ^θ_φφ = <表达式>"),
]
for tag,q in PAIRS:
    a=ask(q,90)
    print(f"\n  [{tag}] Q: {q[:72]}\n     A: {a[:150]}", flush=True)

# ============ 闭环: 模型出候选 -> sympy 验证 ============
print("\n" + "="*84)
print("【闭环】模型提候选 -> sympy 精确验证")
print("="*84, flush=True)
q="二维球面 Γ^θ_φφ 的表达式是什么？(用 sin 和 cos 表示)"
a=ask(q,90)
print(f"  模型答: {a[:120]}", flush=True)
# 提取候选表达式并验证
cands=re.findall(r'([-+]?\s*\d*\.?\d*\s*\*?\s*sin\(?θ?\)?\s*\*?\s*cos\(?θ?\)?)', a)
cands=[c for c in cands if c.strip()]
print(f"  提取候选: {cands[:4]}", flush=True)
TRUE=sp.simplify(Gam[0][1][1])
print(f"  真值: Γ^θ_φφ = {TRUE}  = {sp.nsimplify(TRUE)}", flush=True)
best=None
for c in cands[:6]:
    try:
        e=sp.sympify(c.replace('θ','theta').replace('sin','sin').replace('cos','cos'),
                     locals={'theta':th,'sin':sin,'cos':cos})
        d=sp.simplify(e-TRUE)
        print(f"    候选 '{c.strip()}' -> 差 = {d}  {'✅ 正确!' if d==0 else ''}", flush=True)
        if d==0: best=c
    except Exception as ex:
        pass
print(f"\n  ★ 闭环结果: {'✅ 模型给出正确表达式' if best else '⚠️ 模型未给出可验证的精确表达式'}", flush=True)
print("COT_DONE")
